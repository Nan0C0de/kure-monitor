"""Detector: ``replicas-over-hpa-max``.

Flags Deployments whose ``spec.replicas`` exceeds the ``spec.maxReplicas``
of an HPA that targets them. The HPA will immediately scale down on
sync, so the configured replica count is effectively ignored.
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


class ReplicasOverHpaMax(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "replicas-over-hpa-max"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "scaling"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for hpa in _manifests_by_kind(ctx.manifests, "HorizontalPodAutoscaler"):
            try:
                spec = hpa.get("spec") or {}
                target = spec.get("scaleTargetRef") or {}
                target_kind = target.get("kind")
                target_name = target.get("name")
                max_replicas = spec.get("maxReplicas")
                if not target_kind or not target_name:
                    continue
                if not isinstance(max_replicas, int):
                    continue
                workload = ctx.manifests.get((target_kind, target_name))
                if not isinstance(workload, dict):
                    continue
                wl_spec = workload.get("spec") or {}
                replicas = wl_spec.get("replicas")
                if not isinstance(replicas, int):
                    continue
                if replicas <= max_replicas:
                    continue
                hpa_name = (hpa.get("metadata") or {}).get("name") or ""
                findings.append(
                    make_finding(
                        self,
                        resource_kind=target_kind,
                        resource_name=target_name,
                        namespace=ctx.namespace,
                        title="Workload replicas exceed HPA maxReplicas",
                        summary=(
                            f"{target_kind}/{target_name} declares replicas={replicas} "
                            f"but HPA/{hpa_name} caps it at maxReplicas={max_replicas}. "
                            f"The HPA will scale the workload down to {max_replicas}."
                        ),
                        evidence={
                            "hpa_name": hpa_name,
                            "workload_kind": target_kind,
                            "workload_name": target_name,
                            "workload_replicas": replicas,
                            "hpa_max_replicas": max_replicas,
                        },
                        recommended_change=(
                            "Lower spec.replicas to at most the HPA's maxReplicas, or "
                            "raise the HPA's maxReplicas if the higher count is "
                            "intentional. Better: omit spec.replicas entirely on "
                            "HPA-managed workloads."
                        ),
                        confidence=0.9,
                    )
                )
            except Exception:
                continue
        return findings
