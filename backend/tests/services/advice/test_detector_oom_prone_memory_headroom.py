"""Tests for ``OomProneMemoryHeadroom``."""

from __future__ import annotations

import pytest

from services.advice.detectors.oom_prone_memory_headroom import OomProneMemoryHeadroom
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


def _dep(name, requests, limits):
    return {
        "kind": "Deployment",
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
async def test_positive_memory_equal():
    findings = await OomProneMemoryHeadroom().detect(
        _ctx(
            {
                ("Deployment", "api"): _dep(
                    "api", {"memory": "256Mi"}, {"memory": "256Mi"}
                )
            }
        )
    )
    assert len(findings) == 1
    assert findings[0].evidence["offenders"][0]["memory_request"] == "256Mi"


@pytest.mark.asyncio
async def test_negative_memory_headroom():
    findings = await OomProneMemoryHeadroom().detect(
        _ctx(
            {
                ("Deployment", "api"): _dep(
                    "api", {"memory": "128Mi"}, {"memory": "256Mi"}
                )
            }
        )
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_no_limits():
    findings = await OomProneMemoryHeadroom().detect(
        _ctx({("Deployment", "api"): _dep("api", {"memory": "128Mi"}, {})})
    )
    assert findings == []
