"""Detector: ``hpa-target-mismatch``.

Flags HorizontalPodAutoscalers whose ``scaleTargetRef`` doesn't resolve
to any manifest in the namespace. The HPA is silently inert.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector


def _manifests_by_kind(manifests: Dict[Any, Any], kind: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, m in manifests.items():
        if (
            isinstance(key, tuple)
            and len(key) == 2
            and key[0] == kind
            and isinstance(m, dict)
        ):
            out.append(m)
    return out


class HpaTargetMismatch(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "hpa-target-mismatch"
    default_severity: ClassVar[Severity] = Severity.HIGH
    category: ClassVar[str] = "scaling"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for hpa in _manifests_by_kind(ctx.manifests, "HorizontalPodAutoscaler"):
            try:
                spec = hpa.get("spec") or {}
                target = spec.get("scaleTargetRef") or {}
                target_kind = target.get("kind")
                target_name = target.get("name")
                hpa_name = (hpa.get("metadata") or {}).get("name") or ""
                if not target_kind or not target_name:
                    continue
                if (target_kind, target_name) in ctx.manifests:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="HorizontalPodAutoscaler",
                        resource_name=hpa_name,
                        namespace=ctx.namespace,
                        title="HPA target does not exist",
                        summary=(
                            f"HPA/{hpa_name} targets {target_kind}/{target_name} but "
                            f"no such workload exists in namespace '{ctx.namespace}'."
                        ),
                        evidence={
                            "hpa_name": hpa_name,
                            "target_kind": target_kind,
                            "target_name": target_name,
                        },
                        recommended_change=(
                            "Fix scaleTargetRef.name/kind to point at the real "
                            "workload, or delete the HPA if it is no longer needed."
                        ),
                        confidence=0.9,
                    )
                )
            except Exception:
                continue
        return findings
