"""Tests for ``SidecarNoLimits``."""

from __future__ import annotations

import pytest

from services.advice.detectors.sidecar_no_limits import SidecarNoLimits
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


def _dep(name, containers):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"template": {"spec": {"containers": containers}}},
    }


def _c(name, cpu=None, mem=None):
    limits = {}
    if cpu is not None:
        limits["cpu"] = cpu
    if mem is not None:
        limits["memory"] = mem
    out = {"name": name}
    if limits:
        out["resources"] = {"limits": limits}
    return out


@pytest.mark.asyncio
async def test_positive_sidecar_missing_limits():
    manifests = {
        ("Deployment", "api"): _dep(
            "api",
            [
                _c("main", cpu="500m", mem="256Mi"),
                _c("sidecar"),
            ],
        )
    }
    findings = await SidecarNoLimits().detect(_ctx(manifests))
    assert len(findings) == 1
    offenders = findings[0].evidence["offenders"]
    assert len(offenders) == 1
    assert offenders[0]["container_name"] == "sidecar"
    assert set(offenders[0]["missing_limits"]) == {"cpu", "memory"}


@pytest.mark.asyncio
async def test_negative_single_container():
    manifests = {
        ("Deployment", "api"): _dep("api", [_c("main")]),
    }
    assert await SidecarNoLimits().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_negative_all_containers_have_limits():
    manifests = {
        ("Deployment", "api"): _dep(
            "api",
            [
                _c("main", cpu="500m", mem="256Mi"),
                _c("sidecar", cpu="100m", mem="64Mi"),
            ],
        )
    }
    assert await SidecarNoLimits().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_partial_limits_flagged():
    # Sidecar has cpu but no memory limit.
    manifests = {
        ("Deployment", "api"): _dep(
            "api",
            [
                _c("main", cpu="500m", mem="256Mi"),
                _c("sidecar", cpu="100m"),
            ],
        )
    }
    findings = await SidecarNoLimits().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].evidence["offenders"][0]["missing_limits"] == ["memory"]
