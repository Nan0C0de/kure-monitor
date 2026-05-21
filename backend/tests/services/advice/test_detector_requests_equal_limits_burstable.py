"""Tests for ``RequestsEqualLimitsBurstable``."""

from __future__ import annotations

import pytest

from services.advice.detectors.requests_equal_limits_burstable import (
    RequestsEqualLimitsBurstable,
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


def _wk(kind, name, requests, limits):
    return {
        "kind": kind,
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "c",
                            "image": "nginx",
                            "resources": {"requests": requests, "limits": limits},
                        }
                    ]
                }
            }
        },
    }


@pytest.mark.asyncio
async def test_positive_cpu_equal():
    findings = await RequestsEqualLimitsBurstable().detect(
        _ctx(
            {
                ("Deployment", "api"): _wk(
                    "Deployment", "api", {"cpu": "500m"}, {"cpu": "500m"}
                )
            }
        )
    )
    assert len(findings) == 1
    assert findings[0].evidence["offenders"][0]["cpu_request"] == "500m"


@pytest.mark.asyncio
async def test_negative_cpu_unequal():
    findings = await RequestsEqualLimitsBurstable().detect(
        _ctx(
            {
                ("Deployment", "api"): _wk(
                    "Deployment", "api", {"cpu": "100m"}, {"cpu": "500m"}
                )
            }
        )
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_statefulset_skipped():
    findings = await RequestsEqualLimitsBurstable().detect(
        _ctx(
            {
                ("StatefulSet", "db"): _wk(
                    "StatefulSet", "db", {"cpu": "500m"}, {"cpu": "500m"}
                )
            }
        )
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_no_limit_set():
    findings = await RequestsEqualLimitsBurstable().detect(
        _ctx({("Deployment", "api"): _wk("Deployment", "api", {"cpu": "100m"}, {})})
    )
    assert findings == []
