"""Tests for ``AllToAllReplicas``."""

from __future__ import annotations

import pytest

from services.advice.detectors.all_to_all_replicas import AllToAllReplicas
from services.advice.findings import WorkloadContext
from services.advice.hubble import StubHubbleClient

from ._hubble_fakes import FakeHubble, make_flow


def _deployment(name="cache"):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"template": {"spec": {"containers": [{"name": "app"}]}}},
    }


def _replicaset(name, deployment_name):
    return {
        "kind": "ReplicaSet",
        "metadata": {
            "name": name,
            "ownerReferences": [{"kind": "Deployment", "name": deployment_name}],
        },
    }


def _pod(name, rs_name):
    return {
        "kind": "Pod",
        "metadata": {
            "name": name,
            "ownerReferences": [{"kind": "ReplicaSet", "name": rs_name}],
        },
    }


def _ctx(*, hubble, manifests, pods):
    return WorkloadContext(
        namespace="ns",
        workload_kind=None,
        workload_name=None,
        pod_name=None,
        manifests=manifests,
        pods=pods,
        hubble=hubble,
    )


def _build_manifests_and_pods(num_pods: int = 3):
    pods = [_pod(f"cache-{i}", "cache-abc") for i in range(num_pods)]
    manifests = {
        ("Deployment", "cache"): _deployment("cache"),
        ("ReplicaSet", "cache-abc"): _replicaset("cache-abc", "cache"),
    }
    for p in pods:
        manifests[("Pod", p["metadata"]["name"])] = p
    return manifests, pods


@pytest.mark.asyncio
async def test_positive_many_inter_replica_flows():
    manifests, pods = _build_manifests_and_pods(num_pods=3)
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod="cache-0",
            destination_namespace="ns",
            destination_pod="cache-1",
        ),
        make_flow(
            source_namespace="ns",
            source_pod="cache-1",
            destination_namespace="ns",
            destination_pod="cache-0",
        ),
        make_flow(
            source_namespace="ns",
            source_pod="cache-0",
            destination_namespace="ns",
            destination_pod="cache-2",
        ),
        make_flow(
            source_namespace="ns",
            source_pod="cache-2",
            destination_namespace="ns",
            destination_pod="cache-0",
        ),
        make_flow(
            source_namespace="ns",
            source_pod="cache-1",
            destination_namespace="ns",
            destination_pod="cache-2",
        ),
    ]
    findings = await AllToAllReplicas().detect(
        _ctx(hubble=FakeHubble(flows), manifests=manifests, pods=pods)
    )
    assert len(findings) == 1
    assert findings[0].resource_kind == "Deployment"
    assert findings[0].resource_name == "cache"
    assert findings[0].evidence["flow_count"] == 5


@pytest.mark.asyncio
async def test_negative_only_one_pair():
    manifests, pods = _build_manifests_and_pods(num_pods=3)
    # Many flows but always the same pair -> distinct_peer_pairs=1.
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod="cache-0",
            destination_namespace="ns",
            destination_pod="cache-1",
        )
        for _ in range(10)
    ]
    findings = await AllToAllReplicas().detect(
        _ctx(hubble=FakeHubble(flows), manifests=manifests, pods=pods)
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_when_hubble_unavailable():
    manifests, pods = _build_manifests_and_pods(num_pods=3)
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod=f"cache-{i}",
            destination_namespace="ns",
            destination_pod=f"cache-{(i + 1) % 3}",
        )
        for i in range(6)
    ]
    findings = await AllToAllReplicas().detect(
        _ctx(
            hubble=FakeHubble(flows, available=False, reason="x"),
            manifests=manifests,
            pods=pods,
        )
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_with_stub_client():
    manifests, pods = _build_manifests_and_pods(num_pods=3)
    findings = await AllToAllReplicas().detect(
        _ctx(hubble=StubHubbleClient(), manifests=manifests, pods=pods)
    )
    assert findings == []
