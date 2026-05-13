"""Tests for ``ReplicasOverHpaMax``."""

from __future__ import annotations

import pytest

from services.advice.detectors.replicas_over_hpa_max import ReplicasOverHpaMax
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


def _hpa(name, target_kind, target_name, max_replicas):
    return {
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": name},
        "spec": {
            "scaleTargetRef": {"kind": target_kind, "name": target_name},
            "maxReplicas": max_replicas,
        },
    }


def _dep(name, replicas):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"replicas": replicas},
    }


@pytest.mark.asyncio
async def test_positive_replicas_exceed_max():
    manifests = {
        ("HorizontalPodAutoscaler", "hpa"): _hpa("hpa", "Deployment", "api", 5),
        ("Deployment", "api"): _dep("api", 10),
    }
    findings = await ReplicasOverHpaMax().detect(_ctx(manifests))
    assert len(findings) == 1
    f = findings[0]
    assert f.detector_id == "replicas-over-hpa-max"
    assert f.resource_kind == "Deployment"
    assert f.resource_name == "api"
    assert f.evidence["workload_replicas"] == 10
    assert f.evidence["hpa_max_replicas"] == 5
    assert f.confidence == 0.9


@pytest.mark.asyncio
async def test_negative_replicas_within_max():
    manifests = {
        ("HorizontalPodAutoscaler", "hpa"): _hpa("hpa", "Deployment", "api", 10),
        ("Deployment", "api"): _dep("api", 5),
    }
    assert await ReplicasOverHpaMax().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_negative_replicas_equal_max():
    manifests = {
        ("HorizontalPodAutoscaler", "hpa"): _hpa("hpa", "Deployment", "api", 5),
        ("Deployment", "api"): _dep("api", 5),
    }
    assert await ReplicasOverHpaMax().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_target_missing_skipped():
    manifests = {
        ("HorizontalPodAutoscaler", "hpa"): _hpa("hpa", "Deployment", "ghost", 3),
    }
    assert await ReplicasOverHpaMax().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_replicas_unset_skipped():
    manifests = {
        ("HorizontalPodAutoscaler", "hpa"): _hpa("hpa", "Deployment", "api", 3),
        ("Deployment", "api"): {
            "kind": "Deployment",
            "metadata": {"name": "api"},
            "spec": {},
        },
    }
    assert await ReplicasOverHpaMax().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_robust_against_malformed_hpa():
    manifests = {
        ("HorizontalPodAutoscaler", "h1"): {"kind": "HorizontalPodAutoscaler"},
    }
    assert await ReplicasOverHpaMax().detect(_ctx(manifests)) == []
