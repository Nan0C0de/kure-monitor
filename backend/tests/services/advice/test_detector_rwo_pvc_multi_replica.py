"""Tests for ``RwoPvcMultiReplica``."""

from __future__ import annotations

import pytest

from services.advice.detectors.rwo_pvc_multi_replica import RwoPvcMultiReplica
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


def _dep(name, replicas, claim_name):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "replicas": replicas,
            "template": {
                "spec": {
                    "containers": [{"name": "c", "image": "nginx"}],
                    "volumes": [
                        {
                            "name": "data",
                            "persistentVolumeClaim": {"claimName": claim_name},
                        }
                    ],
                }
            },
        },
    }


def _pvc(name, access_modes):
    return {
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": name},
        "spec": {"accessModes": access_modes},
    }


@pytest.mark.asyncio
async def test_positive_rwo_with_replicas():
    manifests = {
        ("Deployment", "api"): _dep("api", 3, "data"),
        ("PersistentVolumeClaim", "data"): _pvc("data", ["ReadWriteOnce"]),
    }
    findings = await RwoPvcMultiReplica().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].evidence["rwo_claims"] == ["data"]


@pytest.mark.asyncio
async def test_negative_rwx_with_replicas():
    manifests = {
        ("Deployment", "api"): _dep("api", 3, "data"),
        ("PersistentVolumeClaim", "data"): _pvc(
            "data", ["ReadWriteOnce", "ReadWriteMany"]
        ),
    }
    findings = await RwoPvcMultiReplica().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_single_replica():
    manifests = {
        ("Deployment", "api"): _dep("api", 1, "data"),
        ("PersistentVolumeClaim", "data"): _pvc("data", ["ReadWriteOnce"]),
    }
    findings = await RwoPvcMultiReplica().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_edge_pvc_not_in_ctx_silent():
    # PVC not in manifests -> can't verify -> skip silently, no finding.
    manifests = {("Deployment", "api"): _dep("api", 3, "unknown-pvc")}
    findings = await RwoPvcMultiReplica().detect(_ctx(manifests))
    assert findings == []
