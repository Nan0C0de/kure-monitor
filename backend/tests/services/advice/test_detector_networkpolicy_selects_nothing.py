"""Tests for ``NetworkPolicySelectsNothing``."""

from __future__ import annotations

import pytest

from services.advice.detectors.networkpolicy_selects_nothing import (
    NetworkPolicySelectsNothing,
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


def _dep(name, labels):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": {"containers": [{"name": "c", "image": "nginx"}]},
            }
        },
    }


def _netpol(name, match_labels):
    return {
        "kind": "NetworkPolicy",
        "metadata": {"name": name},
        "spec": {"podSelector": {"matchLabels": match_labels}},
    }


@pytest.mark.asyncio
async def test_positive_selector_matches_nothing():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}),
        ("NetworkPolicy", "stale"): _netpol("stale", {"app": "ghost"}),
    }
    findings = await NetworkPolicySelectsNothing().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].evidence["pod_selector"] == {"app": "ghost"}


@pytest.mark.asyncio
async def test_negative_selector_matches_workload():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}),
        ("NetworkPolicy", "good"): _netpol("good", {"app": "api"}),
    }
    findings = await NetworkPolicySelectsNothing().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_edge_empty_selector_skipped():
    # podSelector: {} means "all pods" -- never flagged.
    manifests = {
        ("NetworkPolicy", "default-deny"): {
            "kind": "NetworkPolicy",
            "metadata": {"name": "default-deny"},
            "spec": {"podSelector": {}},
        }
    }
    findings = await NetworkPolicySelectsNothing().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_edge_matches_bare_pod():
    manifests = {
        ("Pod", "loose"): {
            "kind": "Pod",
            "metadata": {"name": "loose", "labels": {"app": "api"}},
            "spec": {"containers": [{"name": "c"}]},
        },
        ("NetworkPolicy", "p"): _netpol("p", {"app": "api"}),
    }
    findings = await NetworkPolicySelectsNothing().detect(_ctx(manifests))
    assert findings == []
