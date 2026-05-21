"""Tests for ``MissingPriorityClass``."""

from __future__ import annotations

import pytest

from services.advice.detectors.missing_priority_class import MissingPriorityClass
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


def _dep(name, labels, priority=None):
    pod_spec = {"containers": [{"name": "c", "image": "nginx"}]}
    if priority is not None:
        pod_spec["priorityClassName"] = priority
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


def _pdb(name, match_labels):
    return {
        "kind": "PodDisruptionBudget",
        "metadata": {"name": name},
        "spec": {"selector": {"matchLabels": match_labels}, "minAvailable": 1},
    }


@pytest.mark.asyncio
async def test_positive_pdb_covered_no_priority():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}),
        ("PodDisruptionBudget", "api-pdb"): _pdb("api-pdb", {"app": "api"}),
    }
    findings = await MissingPriorityClass().detect(_ctx(manifests))
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_negative_has_priority_class():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}, priority="production"),
        ("PodDisruptionBudget", "api-pdb"): _pdb("api-pdb", {"app": "api"}),
    }
    findings = await MissingPriorityClass().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_no_pdb():
    manifests = {("Deployment", "api"): _dep("api", {"app": "api"})}
    findings = await MissingPriorityClass().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_pdb_does_not_cover():
    manifests = {
        ("Deployment", "api"): _dep("api", {"app": "api"}),
        ("PodDisruptionBudget", "other-pdb"): _pdb("other-pdb", {"app": "other"}),
    }
    findings = await MissingPriorityClass().detect(_ctx(manifests))
    assert findings == []
