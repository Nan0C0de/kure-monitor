"""Tests for ``MissingRequestsLimits``."""

from __future__ import annotations

import pytest

from services.advice.detectors.missing_requests_limits import MissingRequestsLimits
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


def _dep(name, resources):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {"name": "c", "image": "nginx:1", "resources": resources}
                    ]
                }
            }
        },
    }


@pytest.mark.asyncio
async def test_positive_no_resources_at_all():
    findings = await MissingRequestsLimits().detect(
        _ctx({("Deployment", "api"): _dep("api", {})})
    )
    assert len(findings) == 1
    off = findings[0].evidence["offenders"][0]
    assert set(off["missing_requests"]) == {"cpu", "memory"}
    assert set(off["missing_limits"]) == {"cpu", "memory"}


@pytest.mark.asyncio
async def test_positive_only_requests_set():
    findings = await MissingRequestsLimits().detect(
        _ctx(
            {
                ("Deployment", "api"): _dep(
                    "api", {"requests": {"cpu": "100m", "memory": "64Mi"}}
                )
            }
        )
    )
    assert len(findings) == 1
    off = findings[0].evidence["offenders"][0]
    assert off["missing_requests"] == []
    assert set(off["missing_limits"]) == {"cpu", "memory"}


@pytest.mark.asyncio
async def test_negative_complete_resources():
    findings = await MissingRequestsLimits().detect(
        _ctx(
            {
                ("Deployment", "api"): _dep(
                    "api",
                    {
                        "requests": {"cpu": "100m", "memory": "64Mi"},
                        "limits": {"cpu": "500m", "memory": "256Mi"},
                    },
                )
            }
        )
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_init_containers_ignored():
    # Init containers are not inspected.
    workload = {
        "kind": "Deployment",
        "metadata": {"name": "api"},
        "spec": {
            "template": {
                "spec": {
                    "initContainers": [{"name": "init", "image": "busybox"}],
                    "containers": [
                        {
                            "name": "c",
                            "image": "nginx",
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "64Mi"},
                                "limits": {"cpu": "500m", "memory": "256Mi"},
                            },
                        }
                    ],
                }
            }
        },
    }
    findings = await MissingRequestsLimits().detect(
        _ctx({("Deployment", "api"): workload})
    )
    assert findings == []
