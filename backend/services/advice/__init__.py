"""AI Advice subsystem.

The AI Advice feature is the proactive counterpart to the existing
reactive AI Auto-Solution: it analyses RUNNING healthy workloads and
emits architectural-mismatch findings (e.g. "this Deployment should be
a DaemonSet"; "HPA is tuned for stateless work but pod is stateful").

This package currently exports the three foundation pieces:

* :class:`Finding` -- the internal, immutable dataclass that detectors
  emit. Has a :meth:`Finding.to_wire` converter to the Pydantic
  :class:`models.models.AdviceFinding` HTTP shape.
* :class:`PatternDetector` -- ABC subclassed by concrete detectors.
* :class:`LLMExplainer` -- adds plain-English explanations to findings,
  with strict prompt-level guardrails against hallucination.

AdviceEngine orchestration, API routes, persistence and WebSocket
broadcasts will be added in later slices.
"""

from .detectors import ALL_DETECTORS
from .detectors.base import PatternDetector
from .explainer import LLMExplainer
from .findings import Finding, Severity, WorkloadContext, make_finding

__all__ = [
    "ALL_DETECTORS",
    "Finding",
    "LLMExplainer",
    "PatternDetector",
    "Severity",
    "WorkloadContext",
    "make_finding",
]
