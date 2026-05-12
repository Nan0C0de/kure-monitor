"""Tests for ``EphemeralProcesses``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.advice.detectors.ephemeral_processes import EphemeralProcesses
from services.advice.findings import WorkloadContext


def _pod(name, *, rs_name, restart=0, age_seconds=120):
    created = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {
        "kind": "Pod",
        "metadata": {
            "name": name,
            "creationTimestamp": created.isoformat().replace("+00:00", "Z"),
            "ownerReferences": [{"kind": "ReplicaSet", "name": rs_name}],
        },
        "status": {"containerStatuses": [{"restartCount": restart}]},
    }


def _replicaset(name, deployment):
    return {
        "kind": "ReplicaSet",
        "metadata": {
            "name": name,
            "ownerReferences": [{"kind": "Deployment", "name": deployment}],
        },
    }


def _ctx(*, manifests, pods):
    return WorkloadContext(
        namespace="ns",
        workload_kind=None,
        workload_name=None,
        pod_name=None,
        manifests=manifests,
        pods=pods,
        hubble=None,
    )


@pytest.mark.asyncio
async def test_positive_multiple_young_crashing_pods():
    pods = [
        _pod("api-0", rs_name="api-rs", restart=5, age_seconds=60),
        _pod("api-1", rs_name="api-rs", restart=3, age_seconds=90),
    ]
    manifests = {("ReplicaSet", "api-rs"): _replicaset("api-rs", "api")}
    findings = await EphemeralProcesses().detect(_ctx(manifests=manifests, pods=pods))
    assert len(findings) == 1
    f = findings[0]
    assert f.resource_kind == "Deployment"
    assert f.resource_name == "api"
    assert f.evidence["owned_pod_count"] == 2
    assert f.evidence["max_restart_count"] == 5


@pytest.mark.asyncio
async def test_negative_single_pod_only():
    pods = [_pod("api-0", rs_name="api-rs", restart=5, age_seconds=60)]
    manifests = {("ReplicaSet", "api-rs"): _replicaset("api-rs", "api")}
    findings = await EphemeralProcesses().detect(_ctx(manifests=manifests, pods=pods))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_long_lived_pods():
    pods = [
        _pod("api-0", rs_name="api-rs", restart=5, age_seconds=7200),  # 2h
        _pod("api-1", rs_name="api-rs", restart=4, age_seconds=7200),
    ]
    manifests = {("ReplicaSet", "api-rs"): _replicaset("api-rs", "api")}
    findings = await EphemeralProcesses().detect(_ctx(manifests=manifests, pods=pods))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_low_restart_count():
    pods = [
        _pod("api-0", rs_name="api-rs", restart=1, age_seconds=60),
        _pod("api-1", rs_name="api-rs", restart=0, age_seconds=90),
    ]
    manifests = {("ReplicaSet", "api-rs"): _replicaset("api-rs", "api")}
    findings = await EphemeralProcesses().detect(_ctx(manifests=manifests, pods=pods))
    assert findings == []


@pytest.mark.asyncio
async def test_does_not_require_hubble():
    # Ensure the detector marks itself as not requiring Hubble.
    assert EphemeralProcesses.requires_hubble is False
