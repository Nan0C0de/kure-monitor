"""Tests for ``StartupIoAmplification``."""

import pytest

from services.advice.detectors.startup_io_amplification import (
    StartupIoAmplification,
)
from services.advice.findings import Severity, WorkloadContext


def _ctx(manifests, namespace="ns") -> WorkloadContext:
    return WorkloadContext(
        namespace=namespace,
        workload_kind=None,
        workload_name=None,
        pod_name=None,
        manifests=manifests,
        pods=[],
    )


def _deployment(
    *,
    name="api",
    replicas=3,
    init_containers=None,
    container_command=None,
    container_args=None,
):
    container = {"name": "main", "image": "api:latest"}
    if container_command is not None:
        container["command"] = container_command
    if container_args is not None:
        container["args"] = container_args
    pod_spec = {"containers": [container]}
    if init_containers is not None:
        pod_spec["initContainers"] = init_containers
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "replicas": replicas,
            "template": {"spec": pod_spec},
        },
    }


@pytest.mark.asyncio
async def test_init_container_with_many_replicas_fires():
    d = _deployment(
        replicas=5,
        init_containers=[{"name": "run-migrations", "image": "migrate:1"}],
    )
    findings = await StartupIoAmplification().detect(_ctx({("Deployment", "api"): d}))
    assert len(findings) == 1
    f = findings[0]
    assert f.detector_id == "startup-io-amplification"
    assert f.severity == Severity.LOW
    assert f.evidence["replicas"] == 5
    assert f.evidence["init_container_names"] == ["run-migrations"]
    assert f.resource_kind == "Deployment"
    assert f.resource_name == "api"


@pytest.mark.asyncio
async def test_two_replicas_does_not_fire():
    d = _deployment(
        replicas=2,
        init_containers=[{"name": "run-migrations", "image": "migrate:1"}],
    )
    findings = await StartupIoAmplification().detect(_ctx({("Deployment", "api"): d}))
    assert findings == []


@pytest.mark.asyncio
async def test_download_command_with_many_replicas_fires():
    d = _deployment(
        replicas=4,
        container_command=["/bin/sh", "-c"],
        container_args=["wget https://example.com/model.bin -O /data/m && ./serve"],
    )
    findings = await StartupIoAmplification().detect(_ctx({("Deployment", "api"): d}))
    assert len(findings) == 1
    f = findings[0]
    matched = f.evidence["suspect_commands"]
    assert "wget" in matched
    assert "download" in matched or "wget" in matched
    assert f.evidence["init_container_names"] == []


@pytest.mark.asyncio
async def test_no_init_no_suspect_command_no_finding():
    d = _deployment(
        replicas=10,
        container_command=["/serve"],
        container_args=["--port", "8080"],
    )
    findings = await StartupIoAmplification().detect(_ctx({("Deployment", "api"): d}))
    assert findings == []


@pytest.mark.asyncio
async def test_hpa_max_replicas_promotes_low_replica_workload():
    d = _deployment(
        replicas=1,
        init_containers=[{"name": "migrate", "image": "m:1"}],
    )
    hpa = {
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": "api-hpa"},
        "spec": {
            "scaleTargetRef": {"kind": "Deployment", "name": "api"},
            "minReplicas": 1,
            "maxReplicas": 6,
        },
    }
    findings = await StartupIoAmplification().detect(
        _ctx(
            {
                ("Deployment", "api"): d,
                ("HorizontalPodAutoscaler", "api-hpa"): hpa,
            }
        )
    )
    assert len(findings) == 1
    assert findings[0].evidence["hpa_max_replicas"] == 6
    assert findings[0].evidence["replicas"] == 1
