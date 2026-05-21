"""Tests for ``PreStopMissingShortGrace``."""

from __future__ import annotations

import pytest

from services.advice.detectors.prestop_missing_short_grace import (
    PreStopMissingShortGrace,
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


def _dep(name, labels, grace=None, prestop=False):
    container = {"name": "c", "image": "nginx"}
    if prestop:
        container["lifecycle"] = {"preStop": {"exec": {"command": ["sleep", "5"]}}}
    pod_spec = {"containers": [container]}
    if grace is not None:
        pod_spec["terminationGracePeriodSeconds"] = grace
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": pod_spec,
            }
        },
    }


def _svc(name, selector):
    return {
        "kind": "Service",
        "metadata": {"name": name},
        "spec": {"selector": selector, "ports": [{"port": 80}]},
    }


@pytest.mark.asyncio
async def test_positive_short_grace_no_prestop_behind_service():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}, grace=5),
        ("Service", "api"): _svc("api", {"app": "api"}),
    }
    findings = await PreStopMissingShortGrace().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].evidence["termination_grace_period_seconds"] == 5


@pytest.mark.asyncio
async def test_negative_has_prestop():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}, grace=5, prestop=True),
        ("Service", "api"): _svc("api", {"app": "api"}),
    }
    findings = await PreStopMissingShortGrace().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_grace_unset():
    # Unset grace defaults to 30 in K8s; we only flag explicit < 30.
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}, grace=None),
        ("Service", "api"): _svc("api", {"app": "api"}),
    }
    findings = await PreStopMissingShortGrace().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_no_service():
    manifests = {("Deployment", "api"): _dep("api", {"app": "api"}, grace=5)}
    findings = await PreStopMissingShortGrace().detect(_ctx(manifests))
    assert findings == []
