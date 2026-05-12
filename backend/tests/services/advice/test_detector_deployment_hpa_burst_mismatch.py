"""Tests for ``DeploymentHpaBurstMismatch``."""

import pytest

from services.advice.detectors.deployment_hpa_burst_mismatch import (
    DeploymentHpaBurstMismatch,
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


def _deployment(name="web", replicas=3, volumes=None):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "replicas": replicas,
            "template": {
                "spec": {
                    "containers": [{"name": "main", "image": "nginx"}],
                    "volumes": volumes or [],
                }
            },
        },
    }


def _hpa(
    name="web-hpa",
    target_kind="Deployment",
    target_name="web",
    min_replicas=2,
    max_replicas=10,
    metrics=None,
    stabilization_window=None,
):
    spec = {
        "scaleTargetRef": {"kind": target_kind, "name": target_name},
        "minReplicas": min_replicas,
        "maxReplicas": max_replicas,
        "metrics": metrics or [],
    }
    if stabilization_window is not None:
        spec["behavior"] = {
            "scaleUp": {"stabilizationWindowSeconds": stabilization_window}
        }
    return {"kind": "HorizontalPodAutoscaler", "metadata": {"name": name}, "spec": spec}


def _cpu_metric():
    return {
        "type": "Resource",
        "resource": {
            "name": "cpu",
            "target": {"type": "Utilization", "averageUtilization": 80},
        },
    }


def _pvc(name="data", modes=("ReadWriteOnce",)):
    return {
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": name},
        "spec": {"accessModes": list(modes) if modes is not None else None},
    }


@pytest.mark.asyncio
async def test_collapsed_range_positive():
    manifests = {
        ("Deployment", "web"): _deployment(),
        ("HorizontalPodAutoscaler", "web-hpa"): _hpa(min_replicas=5, max_replicas=5),
    }
    findings = await DeploymentHpaBurstMismatch().detect(_ctx(manifests))
    titles = [f.title for f in findings]
    assert "HPA range is collapsed (min == max)" in titles
    collapsed = next(
        f for f in findings if f.title.startswith("HPA range is collapsed")
    )
    assert collapsed.severity == Severity.HIGH
    assert collapsed.resource_kind == "Deployment"
    assert collapsed.resource_name == "web"


@pytest.mark.asyncio
async def test_rwo_pvc_positive():
    volumes = [{"name": "data", "persistentVolumeClaim": {"claimName": "data"}}]
    manifests = {
        ("Deployment", "web"): _deployment(volumes=volumes),
        ("HorizontalPodAutoscaler", "web-hpa"): _hpa(
            metrics=[_cpu_metric()], stabilization_window=0
        ),
        ("PersistentVolumeClaim", "data"): _pvc(modes=("ReadWriteOnce",)),
    }
    findings = await DeploymentHpaBurstMismatch().detect(_ctx(manifests))
    titles = [f.title for f in findings]
    assert "HPA on a Deployment with RWO PVC" in titles


@pytest.mark.asyncio
async def test_rwo_pvc_when_access_modes_missing():
    """RWO is the Kubernetes default when accessModes is omitted."""
    volumes = [{"name": "data", "persistentVolumeClaim": {"claimName": "data"}}]
    pvc = {
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": "data"},
        "spec": {},  # no accessModes
    }
    manifests = {
        ("Deployment", "web"): _deployment(volumes=volumes),
        ("HorizontalPodAutoscaler", "web-hpa"): _hpa(
            metrics=[_cpu_metric()], stabilization_window=0
        ),
        ("PersistentVolumeClaim", "data"): pvc,
    }
    findings = await DeploymentHpaBurstMismatch().detect(_ctx(manifests))
    assert any(f.title == "HPA on a Deployment with RWO PVC" for f in findings)


@pytest.mark.asyncio
async def test_cpu_only_slow_scaleup_positive():
    manifests = {
        ("Deployment", "web"): _deployment(),
        ("HorizontalPodAutoscaler", "web-hpa"): _hpa(
            metrics=[_cpu_metric()], stabilization_window=300
        ),
    }
    findings = await DeploymentHpaBurstMismatch().detect(_ctx(manifests))
    titles = [f.title for f in findings]
    assert "CPU-only HPA with slow scale-up for bursty traffic" in titles


@pytest.mark.asyncio
async def test_well_configured_hpa_negative():
    """HPA with custom request-rate metric and short scale-up window."""
    metrics = [{"type": "Pods", "pods": {"metric": {"name": "requests_per_second"}}}]
    manifests = {
        ("Deployment", "web"): _deployment(),
        ("HorizontalPodAutoscaler", "web-hpa"): _hpa(
            metrics=metrics, stabilization_window=0
        ),
    }
    findings = await DeploymentHpaBurstMismatch().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_no_matching_target_negative():
    """HPA referencing a workload not in manifests should not emit."""
    manifests = {
        ("HorizontalPodAutoscaler", "orphan"): _hpa(
            target_name="missing", min_replicas=1, max_replicas=1
        ),
    }
    findings = await DeploymentHpaBurstMismatch().detect(_ctx(manifests))
    assert findings == []
