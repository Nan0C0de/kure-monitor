"""Tests for ``ServiceTargetPortMismatch``."""

from __future__ import annotations

import pytest

from services.advice.detectors.service_target_port_mismatch import (
    ServiceTargetPortMismatch,
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


def _dep(name, labels, container_ports):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [
                        {"name": "c", "image": "nginx", "ports": container_ports}
                    ]
                },
            }
        },
    }


def _svc(name, selector, ports):
    return {
        "kind": "Service",
        "metadata": {"name": name},
        "spec": {"selector": selector, "ports": ports},
    }


@pytest.mark.asyncio
async def test_positive_numeric_mismatch():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}, [{"containerPort": 8080}]),
        ("Service", "api"): _svc(
            "api", {"app": "api"}, [{"port": 80, "targetPort": 9999}]
        ),
    }
    findings = await ServiceTargetPortMismatch().detect(_ctx(manifests))
    assert len(findings) == 1
    mm = findings[0].evidence["mismatches"][0]
    assert mm["target_port"] == 9999


@pytest.mark.asyncio
async def test_positive_named_port_mismatch():
    manifests = {
        ("Deployment", "api"): _dep(
            "api", {"app": "api"}, [{"name": "http", "containerPort": 8080}]
        ),
        ("Service", "api"): _svc(
            "api", {"app": "api"}, [{"port": 80, "targetPort": "metrics"}]
        ),
    }
    findings = await ServiceTargetPortMismatch().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].evidence["mismatches"][0]["target_port"] == "metrics"


@pytest.mark.asyncio
async def test_negative_numeric_match():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}, [{"containerPort": 8080}]),
        ("Service", "api"): _svc(
            "api", {"app": "api"}, [{"port": 80, "targetPort": 8080}]
        ),
    }
    findings = await ServiceTargetPortMismatch().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_named_match():
    manifests = {
        ("Deployment", "api"): _dep(
            "api", {"app": "api"}, [{"name": "http", "containerPort": 8080}]
        ),
        ("Service", "api"): _svc(
            "api", {"app": "api"}, [{"port": 80, "targetPort": "http"}]
        ),
    }
    findings = await ServiceTargetPortMismatch().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_edge_no_matching_pods_skipped():
    # Sibling detector service-selector-no-match handles this case.
    manifests = {
        ("Service", "api"): _svc(
            "api", {"app": "ghost"}, [{"port": 80, "targetPort": 8080}]
        ),
    }
    findings = await ServiceTargetPortMismatch().detect(_ctx(manifests))
    assert findings == []
