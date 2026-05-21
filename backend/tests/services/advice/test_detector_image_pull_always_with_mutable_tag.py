"""Tests for ``ImagePullAlwaysWithMutableTag``."""

from __future__ import annotations

import pytest

from services.advice.detectors.image_pull_always_with_mutable_tag import (
    ImagePullAlwaysWithMutableTag,
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


def _dep(name, image, pull_policy):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {"name": "c", "image": image, "imagePullPolicy": pull_policy}
                    ]
                }
            }
        },
    }


@pytest.mark.asyncio
async def test_positive_latest_with_always():
    findings = await ImagePullAlwaysWithMutableTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx:latest", "Always")})
    )
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_positive_no_tag_with_always():
    findings = await ImagePullAlwaysWithMutableTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx", "Always")})
    )
    assert len(findings) == 1
    assert findings[0].evidence["offenders"][0]["reason"] == "no-tag"


@pytest.mark.asyncio
async def test_negative_always_with_pinned_tag():
    findings = await ImagePullAlwaysWithMutableTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx:1.25.3", "Always")})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_mutable_tag_with_ifnotpresent():
    findings = await ImagePullAlwaysWithMutableTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx:latest", "IfNotPresent")})
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_always_with_digest():
    findings = await ImagePullAlwaysWithMutableTag().detect(
        _ctx({("Deployment", "api"): _dep("api", "nginx@sha256:" + "a" * 64, "Always")})
    )
    assert findings == []
