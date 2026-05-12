"""Shared fakes for Hubble-using detector tests."""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional

from services.advice.hubble import Flow, HubbleClient, HubbleStatus


class FakeHubble(HubbleClient):
    """In-memory :class:`HubbleClient` that returns a canned flow list."""

    def __init__(
        self,
        flows: Optional[List[Flow]] = None,
        available: bool = True,
        reason: Optional[str] = None,
    ) -> None:
        self._flows: List[Flow] = list(flows or [])
        self._available = available
        self._reason = reason

    async def status(self) -> HubbleStatus:
        return HubbleStatus(
            available=self._available,
            reason=self._reason,
            flow_count=len(self._flows),
        )

    async def flows_for_namespace(
        self, namespace: str, since_seconds: int = 300
    ) -> List[Flow]:
        return [
            f
            for f in self._flows
            if f.source_namespace == namespace or f.destination_namespace == namespace
        ]

    async def flows_for_workload(
        self,
        namespace: str,
        workload_kind: str,
        workload_name: str,
        since_seconds: int = 300,
    ) -> List[Flow]:
        return [
            f
            for f in self._flows
            if (f.source_namespace == namespace and f.source_workload == workload_name)
            or (
                f.destination_namespace == namespace
                and f.destination_workload == workload_name
            )
        ]


def make_flow(
    *,
    source_namespace: str = "ns",
    source_pod: Optional[str] = "src",
    source_workload: Optional[str] = None,
    destination_namespace: str = "ns",
    destination_pod: Optional[str] = "dst",
    destination_workload: Optional[str] = None,
    destination_service: Optional[str] = None,
    destination_port: Optional[int] = 8080,
    protocol: Optional[str] = "TCP",
    l7_protocol: Optional[str] = None,
    verdict: str = "FORWARDED",
    timestamp: float = 0.0,
    bytes_sent: Optional[int] = None,
    duration_seconds: Optional[float] = None,
) -> Flow:
    return Flow(
        source_namespace=source_namespace,
        source_pod=source_pod,
        source_workload=source_workload,
        destination_namespace=destination_namespace,
        destination_pod=destination_pod,
        destination_workload=destination_workload,
        destination_service=destination_service,
        destination_port=destination_port,
        protocol=protocol,
        l7_protocol=l7_protocol,
        verdict=verdict,
        timestamp=timestamp,
        bytes_sent=bytes_sent,
        duration_seconds=duration_seconds,
    )
