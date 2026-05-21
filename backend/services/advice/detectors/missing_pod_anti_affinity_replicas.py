"""Detector: ``missing-pod-anti-affinity-replicas``.

Flags Deployment/StatefulSet workloads with ``replicas > 1`` that have no
``podAntiAffinity`` (preferred or required). Without anti-affinity, the
scheduler may stack all replicas onto a single node, defeating the point
of running multiple replicas for availability.
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


def _has_pod_anti_affinity(pod_spec: Dict[str, Any]) -> bool:
    affinity = pod_spec.get("affinity") or {}
    pod_anti = affinity.get("podAntiAffinity") if isinstance(affinity, dict) else None
    if not isinstance(pod_anti, dict):
        return False
    required = pod_anti.get("requiredDuringSchedulingIgnoredDuringExecution") or []
    preferred = pod_anti.get("preferredDuringSchedulingIgnoredDuringExecution") or []
    return bool(required) or bool(preferred)


class MissingPodAntiAffinityReplicas(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "missing-pod-anti-affinity-replicas"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "scheduling"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    spec = workload.get("spec") or {}
                    replicas = spec.get("replicas")
                    if not isinstance(replicas, int) or replicas < 2:
                        continue
                    pod_spec = spec.get("template", {}).get("spec") or {}
                    if _has_pod_anti_affinity(pod_spec):
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Multi-replica workload has no podAntiAffinity",
                            summary=(
                                f"{kind}/{name} runs {replicas} replicas without "
                                f"podAntiAffinity. The scheduler may co-locate all "
                                f"replicas on one node, undermining availability."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "replicas": replicas,
                            },
                            recommended_change=(
                                "Add a preferred podAntiAffinity rule on the pod "
                                "template, keyed by a label that selects this "
                                "workload, with topologyKey 'kubernetes.io/hostname'."
                            ),
                            confidence=0.8,
                        )
                    )
                except Exception:
                    continue
        return findings
