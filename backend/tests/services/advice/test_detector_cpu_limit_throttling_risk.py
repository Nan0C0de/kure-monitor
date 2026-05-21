"""Tests for ``CpuLimitThrottlingRisk``."""

from __future__ import annotations

import pytest

from services.advice.detectors.cpu_limit_throttling_risk import CpuLimitThrottlingRisk
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


def _dep(name, limits):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {"name": "c", "image": "nginx", "resources": {"limits": limits}}
                    ]
                }
            }
        },
    }


@pytest.mark.asyncio
async def test_positive_cpu_limit_set():
    findings = await CpuLimitThrottlingRisk().detect(
        _ctx({("Deployment", "api"): _dep("api", {"cpu": "500m"})})
    )
    assert len(findings) == 1
    assert findings[0].evidence["offenders"][0]["cpu_limit"] == "500m"
    assert findings[0].confidence == 0.6


@pytest.mark.asyncio
async def test_negative_no_cpu_limit():
    findings = await CpuLimitThrottlingRisk().detect(
        _ctx({("Deployment", "api"): _dep("api", {"memory": "256Mi"})})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_empty_limits():
    findings = await CpuLimitThrottlingRisk().detect(
        _ctx({("Deployment", "api"): _dep("api", {})})
    )
    assert findings == []
