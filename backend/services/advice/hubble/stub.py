"""Stub :class:`HubbleClient` implementation -- ships with the app.

Returns ``HubbleStatus(available=False, ...)`` and empty flow lists.
Detectors that need flow data check :meth:`status` first and silently
skip when this stub is in use.

A real gRPC implementation is intentionally out of scope for this slice.
"""

from __future__ import annotations

from typing import List

from .base import Flow, HubbleClient, HubbleStatus


class StubHubbleClient(HubbleClient):
    """Always-unavailable :class:`HubbleClient` used until a real
    Hubble Relay address is configured.

    The ``reason`` string is surfaced verbatim to the admin UI via the
    ``GET /api/advice/detectors`` endpoint.
    """

    def __init__(
        self,
        reason: str = (
            "HubbleClient stub: configure CILIUM_HUBBLE_RELAY_ADDRESS to enable."
        ),
    ) -> None:
        self._reason = reason

    async def status(self) -> HubbleStatus:
        return HubbleStatus(available=False, reason=self._reason, flow_count=0)

    async def flows_for_namespace(
        self, namespace: str, since_seconds: int = 300
    ) -> List[Flow]:
        return []

    async def flows_for_workload(
        self,
        namespace: str,
        workload_kind: str,
        workload_name: str,
        since_seconds: int = 300,
    ) -> List[Flow]:
        return []
