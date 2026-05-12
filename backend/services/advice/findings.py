"""Internal Finding data structures for the AI Advice subsystem.

These are detector-emitted, in-process objects. They are converted to
:class:`models.models.AdviceFinding` when they cross HTTP / WebSocket
boundaries (see :meth:`Finding.to_wire`).

Design notes
------------
* Findings are immutable (frozen dataclasses). The only mutation path is
  attaching an LLM-generated explanation via :meth:`Finding.with_explanation`,
  which returns a *new* instance using :func:`dataclasses.replace`.
* The ``evidence`` dict is the single source of truth that the LLM
  explainer is allowed to use. Anything not in ``evidence`` MUST NOT
  appear in the explanation (this is enforced at the prompt level).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    # Avoid a runtime import cycle: detectors/base.py imports from this module.
    from .detectors.base import PatternDetector
    from .hubble import HubbleClient


class Severity(str, Enum):
    """Finding severity. Subclasses ``str`` so it JSON-serializes cleanly
    under both Pydantic v1 and v2 without custom encoders."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class WorkloadContext:
    """Input scope handed to a :class:`PatternDetector`.

    ``manifests`` and ``pods`` are populated by ``AdviceEngine`` from
    ``TopologyService`` in a follow-up slice; this class is intentionally
    a passive carrier and contains no fetching logic.
    """

    namespace: str
    workload_kind: Optional[str]  # ``None`` means "scan whole namespace"
    workload_name: Optional[str]
    pod_name: Optional[str]
    # Keyed by ``(kind, name)`` tuples; values are parsed manifest dicts.
    manifests: Dict[Any, Any] = field(default_factory=dict)
    pods: List[Dict[str, Any]] = field(default_factory=list)
    # Optional Hubble client for Layer-2 (network-flow) detectors. ``None``
    # means the engine wasn't wired with one; detectors must treat that as
    # "not available" and skip silently.
    hubble: Optional["HubbleClient"] = None


@dataclass(frozen=True)
class Finding:
    """A single architectural-mismatch finding emitted by a detector.

    All fields except :attr:`explanation` are detector-supplied. The
    :attr:`explanation` field is filled in later by
    :class:`services.advice.explainer.LLMExplainer` and is the *only*
    place where LLM-generated text appears.
    """

    detector_id: str
    severity: Severity
    category: str
    title: str
    summary: str
    resource_kind: str
    resource_name: str
    namespace: str
    evidence: Dict[str, Any]
    recommended_change: str
    confidence: float
    explanation: Optional[str] = None

    def with_explanation(self, text: str) -> "Finding":
        """Return a new Finding with :attr:`explanation` populated.

        The original instance is unchanged (Finding is frozen).
        """
        return replace(self, explanation=text)

    def to_wire(self) -> "AdviceFinding":
        """Convert this internal Finding into its Pydantic wire model.

        Imported lazily to avoid pulling Pydantic into modules that only
        need the dataclass.
        """
        from models.models import AdviceFinding

        return AdviceFinding(
            detector_id=self.detector_id,
            severity=self.severity.value,
            category=self.category,
            title=self.title,
            summary=self.summary,
            resource_kind=self.resource_kind,
            resource_name=self.resource_name,
            namespace=self.namespace,
            evidence=self.evidence,
            recommended_change=self.recommended_change,
            confidence=self.confidence,
            explanation=self.explanation,
        )


def make_finding(
    detector: "PatternDetector",
    *,
    resource_kind: str,
    resource_name: str,
    namespace: str,
    title: str,
    summary: str,
    evidence: Dict[str, Any],
    recommended_change: str,
    confidence: float,
    severity: Optional[Severity] = None,
) -> Finding:
    """Helper for detectors so they don't repeat the ``detector_id`` /
    ``category`` / ``default_severity`` boilerplate on every emission.

    When ``severity`` is omitted it falls back to ``detector.default_severity``.
    """
    return Finding(
        detector_id=detector.id,
        severity=severity if severity is not None else detector.default_severity,
        category=detector.category,
        title=title,
        summary=summary,
        resource_kind=resource_kind,
        resource_name=resource_name,
        namespace=namespace,
        evidence=evidence,
        recommended_change=recommended_change,
        confidence=confidence,
    )
