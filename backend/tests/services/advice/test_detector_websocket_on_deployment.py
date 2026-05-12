"""Tests for ``WebSocketOnDeployment``."""

from __future__ import annotations

import pytest

from services.advice.detectors.websocket_on_deployment import WebSocketOnDeployment
from services.advice.findings import WorkloadContext
from services.advice.hubble import StubHubbleClient

from ._hubble_fakes import FakeHubble, make_flow


def _deployment(name="api"):
    return {
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {"template": {"spec": {"containers": [{"name": "app"}]}}},
    }


def _statefulset(name="api"):
    return {
        "kind": "StatefulSet",
        "metadata": {"name": name},
        "spec": {"template": {"spec": {"containers": [{"name": "app"}]}}},
    }


def _ctx(*, hubble, manifests):
    return WorkloadContext(
        namespace="ns",
        workload_kind=None,
        workload_name=None,
        pod_name=None,
        manifests=manifests,
        pods=[],
        hubble=hubble,
    )


@pytest.mark.asyncio
async def test_positive_websocket_flow():
    manifests = {("Deployment", "api"): _deployment("api")}
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod="client-0",
            destination_namespace="ns",
            destination_workload="api",
            l7_protocol="websocket",
        )
    ]
    findings = await WebSocketOnDeployment().detect(
        _ctx(hubble=FakeHubble(flows), manifests=manifests)
    )
    assert len(findings) == 1
    assert findings[0].resource_kind == "Deployment"
    assert findings[0].resource_name == "api"
    assert findings[0].evidence["l7_upgrade_count"] == 1


@pytest.mark.asyncio
async def test_positive_long_lived_connection():
    manifests = {("Deployment", "api"): _deployment("api")}
    flows = [
        make_flow(
            source_namespace="ns",
            source_pod="client-0",
            destination_namespace="ns",
            destination_workload="api",
            duration_seconds=900.0,  # 15 min > 300s
        )
    ]
    findings = await WebSocketOnDeployment().detect(
        _ctx(hubble=FakeHubble(flows), manifests=manifests)
    )
    assert len(findings) == 1
    assert findings[0].evidence["long_lived_connection_count"] == 1


@pytest.mark.asyncio
async def test_negative_only_statefulset_present():
    manifests = {("StatefulSet", "api"): _statefulset("api")}
    flows = [
        make_flow(
            source_namespace="ns",
            destination_namespace="ns",
            destination_workload="api",
            l7_protocol="websocket",
        )
    ]
    findings = await WebSocketOnDeployment().detect(
        _ctx(hubble=FakeHubble(flows), manifests=manifests)
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_when_hubble_unavailable():
    manifests = {("Deployment", "api"): _deployment("api")}
    flows = [
        make_flow(
            source_namespace="ns",
            destination_namespace="ns",
            destination_workload="api",
            l7_protocol="websocket",
        )
    ]
    findings = await WebSocketOnDeployment().detect(
        _ctx(hubble=FakeHubble(flows, available=False, reason="x"), manifests=manifests)
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_with_stub_client():
    manifests = {("Deployment", "api"): _deployment("api")}
    findings = await WebSocketOnDeployment().detect(
        _ctx(hubble=StubHubbleClient(), manifests=manifests)
    )
    assert findings == []


@pytest.mark.asyncio
async def test_negative_short_http_flow():
    manifests = {("Deployment", "api"): _deployment("api")}
    flows = [
        make_flow(
            source_namespace="ns",
            destination_namespace="ns",
            destination_workload="api",
            l7_protocol="HTTP",
            duration_seconds=1.0,
        )
    ]
    findings = await WebSocketOnDeployment().detect(
        _ctx(hubble=FakeHubble(flows), manifests=manifests)
    )
    assert findings == []
