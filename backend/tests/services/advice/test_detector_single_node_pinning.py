"""Tests for ``SingleNodePinning``."""

from __future__ import annotations

import pytest

from services.advice.detectors.single_node_pinning import SingleNodePinning
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


def _dep(name, pod_spec):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {"spec": pod_spec},
        },
    }


@pytest.mark.asyncio
async def test_positive_node_name_set():
    manifests = {
        ("Deployment", "api"): _dep("api", {"nodeName": "node-1", "containers": []}),
    }
    findings = await SingleNodePinning().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].detector_id == "single-node-pinning"
    assert "nodeName" in findings[0].evidence["reasons"]


@pytest.mark.asyncio
async def test_positive_hostname_selector():
    manifests = {
        ("Deployment", "api"): _dep(
            "api",
            {
                "nodeSelector": {"kubernetes.io/hostname": "node-1"},
                "containers": [],
            },
        ),
    }
    findings = await SingleNodePinning().detect(_ctx(manifests))
    assert len(findings) == 1
    assert "nodeSelector[kubernetes.io/hostname]" in findings[0].evidence["reasons"]


@pytest.mark.asyncio
async def test_negative_no_pinning():
    manifests = {
        ("Deployment", "api"): _dep(
            "api",
            {"nodeSelector": {"role": "worker"}, "containers": []},
        ),
    }
    assert await SingleNodePinning().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_daemonset_skipped():
    manifests = {
        ("DaemonSet", "ds"): {
            "kind": "DaemonSet",
            "metadata": {"name": "ds"},
            "spec": {"template": {"spec": {"nodeName": "node-1", "containers": []}}},
        },
    }
    assert await SingleNodePinning().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_bare_pod_with_nodename():
    manifests = {
        ("Pod", "p1"): {
            "kind": "Pod",
            "metadata": {"name": "p1"},
            "spec": {"nodeName": "node-1", "containers": []},
        },
    }
    findings = await SingleNodePinning().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].resource_kind == "Pod"
