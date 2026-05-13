"""Tests for ``ServiceSelectorNoMatch``."""

from __future__ import annotations

import pytest

from services.advice.detectors.service_selector_no_match import (
    ServiceSelectorNoMatch,
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


def _svc(name, selector, **spec_extra):
    spec = {"selector": selector}
    spec.update(spec_extra)
    return {"kind": "Service", "metadata": {"name": name}, "spec": spec}


def _dep(name, labels):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": {"containers": [{"name": "c", "image": "x"}]},
            }
        },
    }


@pytest.mark.asyncio
async def test_positive_no_matching_pods():
    manifests = {
        ("Service", "svc"): _svc("svc", {"app": "ghost"}),
        ("Deployment", "api"): _dep("api", {"app": "api"}),
    }
    findings = await ServiceSelectorNoMatch().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].detector_id == "service-selector-no-match"
    assert findings[0].resource_name == "svc"


@pytest.mark.asyncio
async def test_negative_matches_deployment():
    manifests = {
        ("Service", "svc"): _svc("svc", {"app": "api"}),
        ("Deployment", "api"): _dep("api", {"app": "api"}),
    }
    assert await ServiceSelectorNoMatch().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_negative_matches_bare_pod():
    manifests = {
        ("Service", "svc"): _svc("svc", {"app": "api"}),
        ("Pod", "p1"): {
            "kind": "Pod",
            "metadata": {"name": "p1", "labels": {"app": "api"}},
            "spec": {},
        },
    }
    assert await ServiceSelectorNoMatch().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_headless_publishnotreadyaddresses_skipped():
    manifests = {
        ("Service", "svc"): _svc(
            "svc",
            {"app": "ghost"},
            clusterIP="None",
            publishNotReadyAddresses=True,
        ),
    }
    assert await ServiceSelectorNoMatch().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_externalname_skipped():
    manifests = {
        ("Service", "svc"): {
            "kind": "Service",
            "metadata": {"name": "svc"},
            "spec": {"type": "ExternalName", "externalName": "foo.example.com"},
        }
    }
    assert await ServiceSelectorNoMatch().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_no_selector_skipped():
    # Selector-less Service: endpoints managed manually.
    manifests = {
        ("Service", "svc"): _svc("svc", {}),
    }
    assert await ServiceSelectorNoMatch().detect(_ctx(manifests)) == []
