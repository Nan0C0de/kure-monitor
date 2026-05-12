"""Tests for ``DbConnectionsPerReplica``."""

import pytest

from services.advice.detectors.db_connections_per_replica import (
    DbConnectionsPerReplica,
)
from services.advice.findings import Severity, WorkloadContext


def _ctx(manifests, namespace="ns") -> WorkloadContext:
    return WorkloadContext(
        namespace=namespace,
        workload_kind=None,
        workload_name=None,
        pod_name=None,
        manifests=manifests,
        pods=[],
    )


def _deployment(*, name="api", replicas=5, env=None, env_from=None):
    container = {"name": "main", "image": "api:latest", "env": env or []}
    if env_from is not None:
        container["envFrom"] = env_from
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "replicas": replicas,
            "template": {"spec": {"containers": [container]}},
        },
    }


@pytest.mark.asyncio
async def test_env_var_medium_severity():
    # 25 * 5 = 125 -> MEDIUM (>100, <=300)
    d = _deployment(replicas=5, env=[{"name": "DATABASE_POOL_SIZE", "value": "25"}])
    findings = await DbConnectionsPerReplica().detect(_ctx({("Deployment", "api"): d}))
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == Severity.MEDIUM
    assert f.evidence["pool_size"] == 25
    assert f.evidence["pool_env_var"] == "DATABASE_POOL_SIZE"
    assert f.evidence["replicas"] == 5
    assert f.evidence["hpa_max_replicas"] is None
    assert f.evidence["total_connections_worst_case"] == 125


@pytest.mark.asyncio
async def test_configmap_envfrom_resolution():
    cm = {
        "kind": "ConfigMap",
        "metadata": {"name": "api-config"},
        "data": {"DB_POOL_SIZE": "30", "UNRELATED": "x"},
    }
    d = _deployment(
        replicas=4,
        env_from=[{"configMapRef": {"name": "api-config"}}],
    )
    manifests = {("Deployment", "api"): d, ("ConfigMap", "api-config"): cm}
    findings = await DbConnectionsPerReplica().detect(_ctx(manifests))
    # 30 * 4 = 120 -> MEDIUM
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == Severity.MEDIUM
    assert f.evidence["pool_size"] == 30
    assert f.evidence["pool_env_var"] == "DB_POOL_SIZE"


@pytest.mark.asyncio
async def test_hpa_bumps_to_high():
    d = _deployment(replicas=2, env=[{"name": "DB_POOL_SIZE", "value": "20"}])
    hpa = {
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": "api-hpa"},
        "spec": {
            "scaleTargetRef": {"kind": "Deployment", "name": "api"},
            "minReplicas": 2,
            "maxReplicas": 20,
        },
    }
    manifests = {
        ("Deployment", "api"): d,
        ("HorizontalPodAutoscaler", "api-hpa"): hpa,
    }
    findings = await DbConnectionsPerReplica().detect(_ctx(manifests))
    # 20 * 20 = 400 -> HIGH (>300)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == Severity.HIGH
    assert f.evidence["hpa_max_replicas"] == 20
    assert f.evidence["total_connections_worst_case"] == 400


@pytest.mark.asyncio
async def test_no_db_env_no_finding():
    d = _deployment(env=[{"name": "FOO", "value": "bar"}])
    findings = await DbConnectionsPerReplica().detect(_ctx({("Deployment", "api"): d}))
    assert findings == []


@pytest.mark.asyncio
async def test_unparseable_value_no_finding():
    d = _deployment(env=[{"name": "DB_POOL_SIZE", "value": "not-a-number"}])
    findings = await DbConnectionsPerReplica().detect(_ctx({("Deployment", "api"): d}))
    assert findings == []
