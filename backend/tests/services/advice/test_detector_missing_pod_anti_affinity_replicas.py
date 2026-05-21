"""Tests for ``MissingPodAntiAffinityReplicas``."""

from __future__ import annotations

import pytest

from services.advice.detectors.missing_pod_anti_affinity_replicas import (
    MissingPodAntiAffinityReplicas,
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


def _dep(name, replicas, affinity=None):
    pod_spec = {"containers": [{"name": "c", "image": "nginx"}]}
    if affinity is not None:
        pod_spec["affinity"] = affinity
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"replicas": replicas, "template": {"spec": pod_spec}},
    }


@pytest.mark.asyncio
async def test_positive_multi_replica_no_affinity():
    findings = await MissingPodAntiAffinityReplicas().detect(
        _ctx({("Deployment", "api"): _dep("api", 3)})
    )
    assert len(findings) == 1
    assert findings[0].evidence["replicas"] == 3


@pytest.mark.asyncio
async def test_negative_single_replica():
    findings = await MissingPodAntiAffinityReplicas().detect(
        _ctx({("Deployment", "api"): _dep("api", 1)})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_has_preferred_anti_affinity():
    affinity = {
        "podAntiAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [
                {
                    "weight": 100,
                    "podAffinityTerm": {
                        "labelSelector": {"matchLabels": {"app": "api"}},
                        "topologyKey": "kubernetes.io/hostname",
                    },
                }
            ]
        }
    }
    findings = await MissingPodAntiAffinityReplicas().detect(
        _ctx({("Deployment", "api"): _dep("api", 3, affinity=affinity)})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_statefulset_flagged():
    findings = await MissingPodAntiAffinityReplicas().detect(
        _ctx(
            {
                ("StatefulSet", "db"): {
                    "kind": "StatefulSet",
                    "metadata": {"name": "db"},
                    "spec": {
                        "replicas": 3,
                        "template": {"spec": {"containers": [{"name": "c"}]}},
                    },
                }
            }
        )
    )
    assert len(findings) == 1
