"""Detector: ``missing-topology-spread-constraints``.

Flags Deployment/StatefulSet workloads with ``replicas > 1`` that do not
declare ``topologySpreadConstraints``. Spread constraints give finer
control than anti-affinity for ensuring even distribution across zones,
nodes, or other topology domains.
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


class MissingTopologySpreadConstraints(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "missing-topology-spread-constraints"
    default_severity: ClassVar[Severity] = Severity.LOW
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
                    spread = pod_spec.get("topologySpreadConstraints")
                    if isinstance(spread, list) and spread:
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Multi-replica workload has no topologySpreadConstraints",
                            summary=(
                                f"{kind}/{name} runs {replicas} replicas without "
                                f"topologySpreadConstraints. Distribution across "
                                f"zones/nodes is left to the scheduler's defaults."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "replicas": replicas,
                            },
                            recommended_change=(
                                "Add topologySpreadConstraints (e.g. maxSkew: 1 "
                                "with topologyKey 'topology.kubernetes.io/zone' "
                                "and 'kubernetes.io/hostname') to ensure even "
                                "spread across failure domains."
                            ),
                            confidence=0.7,
                        )
                    )
                except Exception:
                    continue
        return findings
