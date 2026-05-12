"""Tests for ``FanOutPattern``."""

from __future__ import annotations

import pytest

from services.advice.detectors.fan_out_pattern import FAN_OUT_THRESHOLD, FanOutPattern
from services.advice.findings import WorkloadContext
from services.advice.hubble import StubHubbleClient

from ._hubble_fakes import FakeHubble, make_flow


def _ctx(*, hubble, pods=None, manifests=None):
    return WorkloadContext(
        namespace="ns",
        workload_kind=None,
        workload_name=None,
        pod_name=None,
        manifests=manifests or {},
        pods=pods or [],
        hubble=hubble,
    )


@pytest.mark.asyncio
async def test_positive_when_source_exceeds_threshold():
    # 1 source talking to threshold+10 distinct workloads.
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod="worker-0",
            destination_namespace="ns",
            destination_pod=f"dst-{i}",
            destination_workload=f"backend-{i}",
        )
        for i in range(FAN_OUT_THRESHOLD + 10)
    ]
    hubble = FakeHubble(flows)
    findings = await FanOutPattern().detect(_ctx(hubble=hubble))
    assert len(findings) == 1
    f = findings[0]
    assert f.detector_id == "fan-out-pattern"
    assert f.evidence["distinct_destinations"] == FAN_OUT_THRESHOLD + 10
    assert f.evidence["source_pod"] == "worker-0"
    assert len(f.evidence["top_destinations"]) == 5


@pytest.mark.asyncio
async def test_negative_under_threshold():
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod="worker-0",
            destination_namespace="ns",
            destination_pod=f"dst-{i}",
            destination_workload=f"backend-{i}",
        )
        for i in range(10)
    ]
    hubble = FakeHubble(flows)
    findings = await FanOutPattern().detect(_ctx(hubble=hubble))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_when_hubble_unavailable():
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod="worker-0",
            destination_namespace="ns",
            destination_pod=f"dst-{i}",
            destination_workload=f"backend-{i}",
        )
        for i in range(FAN_OUT_THRESHOLD + 10)
    ]
    # FakeHubble with available=False mimics the stub semantics.
    hubble = FakeHubble(flows, available=False, reason="no")
    findings = await FanOutPattern().detect(_ctx(hubble=hubble))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_with_stub_client():
    findings = await FanOutPattern().detect(_ctx(hubble=StubHubbleClient()))
    assert findings == []


@pytest.mark.asyncio
async def test_resource_resolves_to_owning_deployment():
    manifests = {
        ("Pod", "worker-0"): {
            "kind": "Pod",
            "metadata": {
                "name": "worker-0",
                "ownerReferences": [{"kind": "ReplicaSet", "name": "worker-abc"}],
            },
        },
        ("ReplicaSet", "worker-abc"): {
            "kind": "ReplicaSet",
            "metadata": {
                "name": "worker-abc",
                "ownerReferences": [{"kind": "Deployment", "name": "worker"}],
            },
        },
    }
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod="worker-0",
            destination_namespace="ns",
            destination_pod=f"dst-{i}",
            destination_workload=f"backend-{i}",
        )
        for i in range(FAN_OUT_THRESHOLD + 5)
    ]
    findings = await FanOutPattern().detect(
        _ctx(hubble=FakeHubble(flows), manifests=manifests)
    )
    assert len(findings) == 1
    assert findings[0].resource_kind == "Deployment"
    assert findings[0].resource_name == "worker"
