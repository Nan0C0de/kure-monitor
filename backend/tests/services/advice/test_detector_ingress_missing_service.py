"""Tests for ``IngressMissingService``."""

from __future__ import annotations

import pytest

from services.advice.detectors.ingress_missing_service import (
    IngressMissingService,
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


def _ing(name, *, rules=None, default=None):
    spec = {}
    if rules is not None:
        spec["rules"] = rules
    if default is not None:
        spec["defaultBackend"] = default
    return {"kind": "Ingress", "metadata": {"name": name}, "spec": spec}


def _v1_rule(host, path, svc_name, svc_port=80):
    return {
        "host": host,
        "http": {
            "paths": [
                {
                    "path": path,
                    "pathType": "Prefix",
                    "backend": {
                        "service": {"name": svc_name, "port": {"number": svc_port}}
                    },
                }
            ]
        },
    }


def _legacy_rule(host, svc_name):
    return {
        "host": host,
        "http": {"paths": [{"backend": {"serviceName": svc_name, "servicePort": 80}}]},
    }


def _svc(name):
    return {"kind": "Service", "metadata": {"name": name}, "spec": {"selector": {}}}


@pytest.mark.asyncio
async def test_positive_v1_missing_service():
    manifests = {
        ("Ingress", "i"): _ing("i", rules=[_v1_rule("a.com", "/", "ghost")]),
    }
    findings = await IngressMissingService().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].detector_id == "ingress-missing-service"
    assert findings[0].evidence["missing_backends"][0]["service_name"] == "ghost"


@pytest.mark.asyncio
async def test_positive_legacy_missing_service():
    manifests = {
        ("Ingress", "i"): _ing("i", rules=[_legacy_rule("a.com", "ghost")]),
    }
    findings = await IngressMissingService().detect(_ctx(manifests))
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_positive_default_backend_missing():
    manifests = {
        ("Ingress", "i"): _ing(
            "i",
            default={"service": {"name": "ghost", "port": {"number": 80}}},
        ),
    }
    findings = await IngressMissingService().detect(_ctx(manifests))
    assert len(findings) == 1
    locations = [m["location"] for m in findings[0].evidence["missing_backends"]]
    assert "defaultBackend" in locations


@pytest.mark.asyncio
async def test_negative_service_exists():
    manifests = {
        ("Ingress", "i"): _ing("i", rules=[_v1_rule("a.com", "/", "real")]),
        ("Service", "real"): _svc("real"),
    }
    assert await IngressMissingService().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_mixed_some_missing_some_present():
    manifests = {
        ("Ingress", "i"): _ing(
            "i",
            rules=[
                _v1_rule("a.com", "/", "real"),
                _v1_rule("b.com", "/", "ghost"),
            ],
        ),
        ("Service", "real"): _svc("real"),
    }
    findings = await IngressMissingService().detect(_ctx(manifests))
    assert len(findings) == 1
    missing = findings[0].evidence["missing_backends"]
    assert len(missing) == 1
    assert missing[0]["service_name"] == "ghost"
