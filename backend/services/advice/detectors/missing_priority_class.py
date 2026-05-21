"""Detector: ``missing-priority-class``.

Flags workloads (Deployment/StatefulSet) that are covered by a
PodDisruptionBudget -- a strong signal the team considers them critical
-- but whose pod template does not set ``priorityClassName``. Without a
PriorityClass, these pods can be preempted by any equally- or
higher-priority workload during node pressure.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_WORKLOAD_KINDS = ("Deployment", "StatefulSet")


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


def _template_labels(workload: Dict[str, Any]) -> Dict[str, str]:
    try:
        labels = (
            workload.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("labels")
            or {}
        )
        return {str(k): str(v) for k, v in labels.items()}
    except Exception:
        return {}


def _selector_matches(selector: Dict[str, Any], labels: Dict[str, str]) -> bool:
    if not isinstance(selector, dict) or not selector:
        return False
    match_labels = selector.get("matchLabels") or {}
    if not match_labels:
        return False
    for k, v in match_labels.items():
        if labels.get(str(k)) != str(v):
            return False
    return True


class MissingPriorityClass(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "missing-priority-class"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "scheduling"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        pdbs = _manifests_by_kind(ctx.manifests, "PodDisruptionBudget")
        if not pdbs:
            return findings

        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    labels = _template_labels(workload)
                    if not labels:
                        continue
                    covered = any(
                        _selector_matches(
                            (pdb.get("spec") or {}).get("selector") or {}, labels
                        )
                        for pdb in pdbs
                    )
                    if not covered:
                        continue
                    pod_spec = (workload.get("spec") or {}).get("template", {}).get(
                        "spec"
                    ) or {}
                    if pod_spec.get("priorityClassName"):
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="PDB-covered workload has no priorityClassName",
                            summary=(
                                f"{kind}/{name} is covered by a PDB (treated as "
                                f"critical) but has no priorityClassName. Under node "
                                f"pressure it can be preempted before less-critical "
                                f"workloads."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "template_labels": labels,
                            },
                            recommended_change=(
                                "Set priorityClassName on the pod template (e.g. a "
                                "cluster-wide 'production' PriorityClass) so the "
                                "scheduler treats this workload as more important "
                                "than best-effort jobs."
                            ),
                            confidence=0.7,
                        )
                    )
                except Exception:
                    continue
        return findings
