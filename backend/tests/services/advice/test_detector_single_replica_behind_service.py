"""Tests for ``SingleReplicaBehindService``."""

from __future__ import annotations

import pytest

from services.advice.detectors.single_replica_behind_service import (
    SingleReplicaBehindService,
)
from services.advice.findings import WorkloadContext


def _ctx(manifests):
    return WorkloadContext(
        namespace="ns",
        workload_kind=None,
        workload_name=None,
        pod_name=None,
        manifests=manifests,
        pods=[],
    )


def _dep(name, replicas, labels):
    spec = {
        "template": {
            "metadata": {"labels": labels},
            "spec": {"containers": [{"name": "c", "image": "nginx"}]},
        }
    }
    if replicas is not None:
        spec["replicas"] = replicas
    return {"kind": "Deployment", "metadata": {"name": name}, "spec": spec}


def _svc(name, selector):
    return {
        "kind": "Service",
        "metadata": {"name": name},
        "spec": {"selector": selector, "ports": [{"port": 80}]},
    }


@pytest.mark.asyncio
async def test_positive_one_replica_with_service():
    manifests = {
        ("Deployment", "api"): _dep("api", 1, {"app": "api"}),
        ("Service", "api"): _svc("api", {"app": "api"}),
    }
    findings = await SingleReplicaBehindService().detect(_ctx(manifests))
    assert len(findings) == 1
    assert "api" in findings[0].evidence["matched_services"]


@pytest.mark.asyncio
async def test_positive_unset_replicas_with_service():
    manifests = {
        ("Deployment", "api"): _dep("api", None, {"app": "api"}),
        ("Service", "api"): _svc("api", {"app": "api"}),
    }
    findings = await SingleReplicaBehindService().detect(_ctx(manifests))
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_negative_multi_replica():
    manifests = {
        ("Deployment", "api"): _dep("api", 3, {"app": "api"}),
        ("Service", "api"): _svc("api", {"app": "api"}),
    }
    findings = await SingleReplicaBehindService().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_no_matching_service():
    manifests = {
        ("Deployment", "api"): _dep("api", 1, {"app": "api"}),
        ("Service", "other"): _svc("other", {"app": "other"}),
    }
    findings = await SingleReplicaBehindService().detect(_ctx(manifests))
    assert findings == []
