"""Tests for the :class:`StubHubbleClient`."""

from __future__ import annotations

import pytest

from services.advice.hubble import (
    Flow,
    HubbleClient,
    HubbleStatus,
    StubHubbleClient,
)


@pytest.mark.asyncio
async def test_stub_status_reports_unavailable():
    client = StubHubbleClient()
    status = await client.status()
    assert isinstance(status, HubbleStatus)
    assert status.available is False
    assert status.flow_count == 0
    assert status.reason is not None and len(status.reason) > 0


@pytest.mark.asyncio
async def test_stub_flows_for_namespace_empty():
    client = StubHubbleClient()
    flows = await client.flows_for_namespace("ns1")
    assert flows == []


@pytest.mark.asyncio
async def test_stub_flows_for_workload_empty():
    client = StubHubbleClient()
    flows = await client.flows_for_workload("ns1", "Deployment", "api")
    assert flows == []


@pytest.mark.asyncio
async def test_custom_reason_is_returned():
    client = StubHubbleClient(reason="hubble disabled for this test")
    status = await client.status()
    assert status.reason == "hubble disabled for this test"


def test_stub_is_a_hubble_client():
    assert issubclass(StubHubbleClient, HubbleClient)


def test_flow_dataclass_is_frozen():
    f = Flow(
        source_namespace="ns",
        source_pod="p",
        source_workload=None,
        destination_namespace="ns",
        destination_pod="q",
        destination_workload=None,
        destination_service=None,
        destination_port=8080,
        protocol="TCP",
        l7_protocol=None,
        verdict="FORWARDED",
        timestamp=0.0,
        bytes_sent=None,
        duration_seconds=None,
    )
    with pytest.raises(Exception):
        f.source_pod = "other"  # type: ignore[misc]
