"""Detector: ``missing-pdb``.

Flags multi-replica workloads (Deployment / StatefulSet / ReplicaSet)
that are not covered by any PodDisruptionBudget. Voluntary disruptions
(node drains, upgrades) can take all replicas down simultaneously when
no PDB is present.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_WORKLOAD_KINDS = ("Deployment", "StatefulSet", "ReplicaSet")


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
    if not selector:
        return False
    match_labels = selector.get("matchLabels") or {}
    if not match_labels:
        return False
    for k, v in match_labels.items():
        if labels.get(str(k)) != str(v):
            return False
    return True


class MissingPdb(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "missing-pdb"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "reliability"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        pdbs = _manifests_by_kind(ctx.manifests, "PodDisruptionBudget")

        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    spec = workload.get("spec") or {}
                    replicas = spec.get("replicas")
                    if not isinstance(replicas, int) or replicas < 2:
                        continue
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    labels = _template_labels(workload)
                    if not labels:
                        continue

                    covered = False
                    for pdb in pdbs:
                        pdb_selector = (pdb.get("spec") or {}).get("selector") or {}
                        if _selector_matches(pdb_selector, labels):
                            covered = True
                            break
                    if covered:
                        continue

                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Multi-replica workload has no PodDisruptionBudget",
                            summary=(
                                f"{kind}/{name} runs with {replicas} replicas but no "
                                f"PodDisruptionBudget matches its pod labels. A node "
                                f"drain may evict all replicas at once."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "replicas": replicas,
                                "template_labels": labels,
                            },
                            recommended_change=(
                                "Add a PodDisruptionBudget with minAvailable: 1 (or "
                                "maxUnavailable: 1) whose selector matches the "
                                "workload's pod labels."
                            ),
                            confidence=0.9,
                        )
                    )
                except Exception:
                    continue
        return findings
