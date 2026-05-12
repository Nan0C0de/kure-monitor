"""HubbleClient abstraction for Layer-2 network-flow detectors.

This module defines the interface; concrete implementations live in
sibling modules (``stub.py`` ships with the application; a real gRPC
client may be added in a follow-up). Detectors that need flow data
call :meth:`HubbleClient.status` first and silently skip if Hubble is
not available -- they MUST NOT raise.

The :class:`Flow` dataclass is intentionally a small, denormalised view
of a Cilium Hubble flow record. It contains only what the current
detectors need (workload/pod identity, L4/L7 protocol, verdict,
duration). Adding fields here is fine; renaming existing ones is a
breaking change for detectors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Flow:
    """A single observed network flow.

    Most fields are ``Optional`` because not every flow source can
    populate them (e.g. an external IP has no pod/workload identity).
    """

    source_namespace: str
    source_pod: Optional[str]
    source_workload: Optional[str]
    destination_namespace: str
    destination_pod: Optional[str]
    destination_workload: Optional[str]
    destination_service: Optional[str]
    destination_port: Optional[int]
    protocol: Optional[str]  # "TCP" / "UDP"
    l7_protocol: Optional[str]  # "HTTP" / "HTTP2" / "websocket" / None
    verdict: str
    timestamp: float
    bytes_sent: Optional[int]
    duration_seconds: Optional[float]


@dataclass(frozen=True)
class HubbleStatus:
    """Reported by :meth:`HubbleClient.status` so detectors can decide
    whether to proceed and so the admin UI can surface an explanation."""

    available: bool
    reason: Optional[str]
    flow_count: int = 0


class HubbleClient(ABC):
    """Abstract async client for Cilium Hubble.

    Concrete implementations must be safe to construct cheaply (no
    network I/O in ``__init__``); all I/O happens in the awaitable
    methods.
    """

    @abstractmethod
    async def status(self) -> HubbleStatus:
        """Return current availability + flow count."""
        ...

    @abstractmethod
    async def flows_for_namespace(
        self, namespace: str, since_seconds: int = 300
    ) -> List[Flow]:
        """Return all flows where source OR destination is in ``namespace``."""
        ...

    @abstractmethod
    async def flows_for_workload(
        self,
        namespace: str,
        workload_kind: str,
        workload_name: str,
        since_seconds: int = 300,
    ) -> List[Flow]:
        """Return flows touching the given workload (either direction)."""
        ...
