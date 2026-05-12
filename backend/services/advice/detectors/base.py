"""Abstract base class for AI Advice pattern detectors.

Concrete detectors live alongside this module (one file per detector)
and are registered in :mod:`services.advice.detectors.__init__`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, List

from ..findings import Finding, Severity, WorkloadContext


class PatternDetector(ABC):
    """Base class for architectural-mismatch detectors.

    Subclasses set the three class-level attributes (``id``,
    ``default_severity``, ``category``) and implement :meth:`detect`.

    :meth:`detect` MUST only return findings whose resource falls within
    ``ctx``'s scope -- the orchestrating engine does not filter the
    results. ``detect`` is async because future detectors may need to
    call :class:`services.topology_service.TopologyService` (which is
    async); detectors that don't perform I/O can simply ``return [...]``.
    """

    #: Stable slug used as the finding's ``detector_id``. Must be unique
    #: across all registered detectors. Example:
    #: ``"deployment-should-be-daemonset"``.
    id: ClassVar[str]

    #: Default severity for findings emitted by this detector.
    default_severity: ClassVar[Severity]

    #: Free-form category string -- e.g. ``"workload-pattern"``,
    #: ``"scaling"``, ``"scheduling"``, ``"networking"``.
    category: ClassVar[str]

    #: ``True`` if this detector consults :class:`HubbleClient` flow data.
    #: Surfaced to the admin UI so users know which detectors are dark
    #: when no Hubble Relay is configured. Defaults to ``False`` on the
    #: base class; Layer-2 detectors set this to ``True``.
    requires_hubble: ClassVar[bool] = False

    @abstractmethod
    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        """Analyze ``ctx`` and return zero or more findings."""
        ...
