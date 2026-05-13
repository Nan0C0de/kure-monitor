"""Tests for ``MutableImageTag``."""

from __future__ import annotations

import pytest

from services.advice.detectors.mutable_image_tag import MutableImageTag
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


def _dep(name, image):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"template": {"spec": {"containers": [{"name": "c", "image": image}]}}},
    }


@pytest.mark.asyncio
async def test_positive_latest_tag():
    findings = await MutableImageTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx:latest")})
    )
    assert len(findings) == 1
    assert findings[0].evidence["image_tag"] == "latest"
    assert findings[0].evidence["reason"] == "mutable-tag:latest"


@pytest.mark.asyncio
async def test_positive_no_tag():
    findings = await MutableImageTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx")})
    )
    assert len(findings) == 1
    assert findings[0].evidence["reason"] == "no-tag"


@pytest.mark.asyncio
async def test_positive_dev_edge_nightly():
    manifests = {
        ("Deployment", "a"): _dep("a", "repo/img:dev"),
        ("Deployment", "b"): _dep("b", "repo/img:edge"),
        ("Deployment", "c"): _dep("c", "repo/img:nightly"),
    }
    findings = await MutableImageTag().detect(_ctx(manifests))
    assert len(findings) == 3


@pytest.mark.asyncio
async def test_negative_pinned_tag():
    findings = await MutableImageTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx:1.25.3")})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_digest_pinned():
    findings = await MutableImageTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx@sha256:" + "a" * 64)})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_edge_registry_port_not_confused_for_tag():
    # host:5000/nginx -> no tag (mutable).
    findings = await MutableImageTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "registry.local:5000/nginx")})
    )
    assert len(findings) == 1
    assert findings[0].evidence["reason"] == "no-tag"


@pytest.mark.asyncio
async def test_edge_registry_port_with_pinned_tag():
    findings = await MutableImageTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "registry.local:5000/nginx:1.0")})
    )
    assert findings == []
