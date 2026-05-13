"""Tests for ``PortsButNoService``."""

from __future__ import annotations

import pytest

from services.advice.detectors.ports_but_no_service import PortsButNoService
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


def _dep_with_ports(name, labels, ports):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [
                        {
                            "name": "main",
                            "ports": [{"containerPort": p} for p in ports],
                        }
                    ]
                },
            }
        },
    }


def _svc(name, selector):
    return {
        "kind": "Service",
        "metadata": {"name": name},
        "spec": {"selector": selector},
    }


@pytest.mark.asyncio
async def test_positive_ports_no_service():
    manifests = {
        ("Deployment", "api"): _dep_with_ports("api", {"app": "api"}, [8080]),
    }
    findings = await PortsButNoService().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].detector_id == "ports-but-no-service"
    assert findings[0].evidence["container_ports"] == [8080]


@pytest.mark.asyncio
async def test_negative_service_matches():
    manifests = {
        ("Deployment", "api"): _dep_with_ports("api", {"app": "api"}, [8080]),
        ("Service", "api-svc"): _svc("api-svc", {"app": "api"}),
    }
    assert await PortsButNoService().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_negative_no_ports_declared():
    manifests = {
        ("Deployment", "api"): _dep_with_ports("api", {"app": "api"}, []),
    }
    assert await PortsButNoService().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_partial_selector_match():
    # Service requires both keys; workload only has one.
    manifests = {
        ("Deployment", "api"): _dep_with_ports("api", {"app": "api"}, [80]),
        ("Service", "api-svc"): _svc("api-svc", {"app": "api", "tier": "edge"}),
    }
    findings = await PortsButNoService().detect(_ctx(manifests))
    assert len(findings) == 1
