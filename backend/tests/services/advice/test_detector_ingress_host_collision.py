"""Tests for ``IngressHostCollision``."""

from __future__ import annotations

import pytest

from services.advice.detectors.ingress_host_collision import IngressHostCollision
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


def _ing(name, host, path):
    return {
        "kind": "Ingress",
        "metadata": {"name": name},
        "spec": {
            "rules": [
                {
                    "host": host,
                    "http": {
                        "paths": [
                            {
                                "path": path,
                                "backend": {
                                    "service": {"name": "svc", "port": {"number": 80}}
                                },
                            }
                        ]
                    },
                }
            ]
        },
    }


@pytest.mark.asyncio
async def test_positive_two_ingresses_same_route():
    manifests = {
        ("Ingress", "a"): _ing("a", "example.com", "/"),
        ("Ingress", "b"): _ing("b", "example.com", "/"),
    }
    findings = await IngressHostCollision().detect(_ctx(manifests))
    assert len(findings) == 1
    assert set(findings[0].evidence["colliding_ingresses"]) == {"a", "b"}


@pytest.mark.asyncio
async def test_negative_distinct_paths():
    manifests = {
        ("Ingress", "a"): _ing("a", "example.com", "/api"),
        ("Ingress", "b"): _ing("b", "example.com", "/admin"),
    }
    findings = await IngressHostCollision().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_negative_distinct_hosts():
    manifests = {
        ("Ingress", "a"): _ing("a", "a.example.com", "/"),
        ("Ingress", "b"): _ing("b", "b.example.com", "/"),
    }
    findings = await IngressHostCollision().detect(_ctx(manifests))
    assert findings == []


@pytest.mark.asyncio
async def test_edge_three_way_collision_single_finding():
    manifests = {
        ("Ingress", "a"): _ing("a", "example.com", "/"),
        ("Ingress", "b"): _ing("b", "example.com", "/"),
        ("Ingress", "c"): _ing("c", "example.com", "/"),
    }
    findings = await IngressHostCollision().detect(_ctx(manifests))
    assert len(findings) == 1
    assert len(findings[0].evidence["colliding_ingresses"]) == 3
