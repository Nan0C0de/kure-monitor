"""Tests for ``NetpolDefaultDenyNoAllow``."""

from __future__ import annotations

import pytest

from services.advice.detectors.netpol_default_deny_no_allow import (
    NetpolDefaultDenyNoAllow,
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


def _deny(name="default-deny"):
    return {
        "kind": "NetworkPolicy",
        "metadata": {"name": name},
        "spec": {"podSelector": {}, "policyTypes": ["Ingress"]},
    }


def _allow(name="allow", rules=None):
    return {
        "kind": "NetworkPolicy",
        "metadata": {"name": name},
        "spec": {
            "podSelector": {"matchLabels": {"app": "api"}},
            "policyTypes": ["Ingress"],
            "ingress": rules or [{"from": [{"podSelector": {}}]}],
        },
    }


@pytest.mark.asyncio
async def test_positive_only_default_deny():
    manifests = {("NetworkPolicy", "default-deny"): _deny()}
    findings = await NetpolDefaultDenyNoAllow().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].detector_id == "netpol-default-deny-no-allow"


@pytest.mark.asyncio
async def test_negative_default_deny_with_allow():
    manifests = {
        ("NetworkPolicy", "default-deny"): _deny(),
        ("NetworkPolicy", "allow-api"): _allow("allow-api"),
    }
    assert await NetpolDefaultDenyNoAllow().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_negative_no_default_deny():
    manifests = {
        ("NetworkPolicy", "allow-api"): _allow("allow-api"),
    }
    assert await NetpolDefaultDenyNoAllow().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_negative_no_netpols_at_all():
    assert await NetpolDefaultDenyNoAllow().detect(_ctx({})) == []


@pytest.mark.asyncio
async def test_edge_egress_only_policy_not_default_deny():
    # podSelector {} but policyTypes only Egress -> doesn't deny ingress.
    manifests = {
        ("NetworkPolicy", "egress-deny"): {
            "kind": "NetworkPolicy",
            "metadata": {"name": "egress-deny"},
            "spec": {"podSelector": {}, "policyTypes": ["Egress"]},
        }
    }
    assert await NetpolDefaultDenyNoAllow().detect(_ctx(manifests)) == []
