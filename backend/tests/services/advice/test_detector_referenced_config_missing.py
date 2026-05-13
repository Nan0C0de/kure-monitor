"""Tests for ``ReferencedConfigMissing``."""

from __future__ import annotations

import pytest

from services.advice.detectors.referenced_config_missing import (
    ReferencedConfigMissing,
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


def _dep(name, pod_spec):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"template": {"spec": pod_spec}},
    }


def _cm(name):
    return {"kind": "ConfigMap", "metadata": {"name": name}}


def _secret(name):
    return {"kind": "Secret", "metadata": {"name": name}}


@pytest.mark.asyncio
async def test_positive_envfrom_configmap_missing():
    pod_spec = {
        "containers": [
            {
                "name": "c",
                "envFrom": [{"configMapRef": {"name": "missing-cm"}}],
            }
        ]
    }
    manifests = {("Deployment", "api"): _dep("api", pod_spec)}
    findings = await ReferencedConfigMissing().detect(_ctx(manifests))
    assert len(findings) == 1
    missing = findings[0].evidence["missing_references"]
    assert missing == [{"kind": "ConfigMap", "name": "missing-cm", "source": "envFrom"}]


@pytest.mark.asyncio
async def test_positive_volume_secret_missing():
    pod_spec = {
        "containers": [{"name": "c"}],
        "volumes": [{"name": "v", "secret": {"secretName": "ghost"}}],
    }
    manifests = {("Deployment", "api"): _dep("api", pod_spec)}
    findings = await ReferencedConfigMissing().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].evidence["missing_references"][0]["kind"] == "Secret"
    assert findings[0].evidence["missing_references"][0]["name"] == "ghost"


@pytest.mark.asyncio
async def test_positive_env_valuefrom_secret_missing():
    pod_spec = {
        "containers": [
            {
                "name": "c",
                "env": [
                    {
                        "name": "TOKEN",
                        "valueFrom": {
                            "secretKeyRef": {"name": "missing-sec", "key": "t"}
                        },
                    }
                ],
            }
        ]
    }
    manifests = {("Deployment", "api"): _dep("api", pod_spec)}
    findings = await ReferencedConfigMissing().detect(_ctx(manifests))
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_negative_references_resolved():
    pod_spec = {
        "containers": [
            {
                "name": "c",
                "envFrom": [{"configMapRef": {"name": "cm-a"}}],
                "env": [
                    {
                        "name": "T",
                        "valueFrom": {"secretKeyRef": {"name": "sec-a", "key": "t"}},
                    }
                ],
            }
        ],
        "volumes": [{"name": "v", "configMap": {"name": "cm-b"}}],
    }
    manifests = {
        ("Deployment", "api"): _dep("api", pod_spec),
        ("ConfigMap", "cm-a"): _cm("cm-a"),
        ("ConfigMap", "cm-b"): _cm("cm-b"),
        ("Secret", "sec-a"): _secret("sec-a"),
    }
    assert await ReferencedConfigMissing().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_optional_reference_skipped():
    pod_spec = {
        "containers": [
            {
                "name": "c",
                "envFrom": [
                    {
                        "configMapRef": {
                            "name": "maybe-cm",
                            "optional": True,
                        }
                    }
                ],
            }
        ]
    }
    manifests = {("Deployment", "api"): _dep("api", pod_spec)}
    assert await ReferencedConfigMissing().detect(_ctx(manifests)) == []


@pytest.mark.asyncio
async def test_edge_init_container_references_checked():
    pod_spec = {
        "containers": [{"name": "c"}],
        "initContainers": [
            {
                "name": "init",
                "envFrom": [{"configMapRef": {"name": "ghost-cm"}}],
            }
        ],
    }
    manifests = {("Deployment", "api"): _dep("api", pod_spec)}
    findings = await ReferencedConfigMissing().detect(_ctx(manifests))
    assert len(findings) == 1
    assert findings[0].evidence["missing_references"][0]["name"] == "ghost-cm"
