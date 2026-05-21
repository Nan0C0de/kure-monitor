"""Tests for ``MissingTopologySpreadConstraints``."""

from __future__ import annotations

import pytest

from services.advice.detectors.missing_topology_spread_constraints import (
    MissingTopologySpreadConstraints,
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


def _dep(name, replicas, spread=None):
    pod_spec = {"containers": [{"name": "c", "image": "nginx"}]}
    if spread is not None:
        pod_spec["topologySpreadConstraints"] = spread
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"replicas": replicas, "template": {"spec": pod_spec}},
    }


@pytest.mark.asyncio
async def test_positive_multi_replica_no_spread():
    findings = await MissingTopologySpreadConstraints().detect(
        _ctx({("Deployment", "api"): _dep("api", 3)})
    )
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_negative_has_spread():
    spread = [
        {
            "maxSkew": 1,
            "topologyKey": "topology.kubernetes.io/zone",
            "whenUnsatisfiable": "ScheduleAnyway",
            "labelSelector": {"matchLabels": {"app": "api"}},
        }
    ]
    findings = await MissingTopologySpreadConstraints().detect(
        _ctx({("Deployment", "api"): _dep("api", 3, spread=spread)})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_single_replica():
    findings = await MissingTopologySpreadConstraints().detect(
        _ctx({("Deployment", "api"): _dep("api", 1)})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_empty_spread_list_still_flagged():
    findings = await MissingTopologySpreadConstraints().detect(
        _ctx({("Deployment", "api"): _dep("api", 3, spread=[])})
    )
    assert len(findings) == 1
