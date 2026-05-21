"""Detector: ``cpu-limit-throttling-risk``.

Flags any container with a CPU limit set. CPU limits enforce CFS quota,
which is known to cause sub-period throttling on bursty / latency-
sensitive workloads even when the average CPU usage is well below the
limit. The general guidance is "set CPU requests, do not set CPU limits".

This is an advisory finding -- some teams deliberately set CPU limits for
multi-tenant fairness. Confidence is intentionally low.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_WORKLOAD_KINDS = (
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "ReplicaSet",
    "Job",
    "CronJob",
)


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


def _pod_template_spec(workload: Dict[str, Any]) -> Dict[str, Any]:
    spec = workload.get("spec") or {}
    if not isinstance(spec, dict):
        return {}
    if "jobTemplate" in spec:
        return (
            spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
            or {}
        )
    return spec.get("template", {}).get("spec") or {}


class CpuLimitThrottlingRisk(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "cpu-limit-throttling-risk"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "resources"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = _pod_template_spec(workload)
                    offenders: List[Dict[str, Any]] = []
                    for container in pod_spec.get("containers") or []:
                        if not isinstance(container, dict):
                            continue
                        limits = (container.get("resources") or {}).get("limits") or {}
                        cpu_limit = limits.get("cpu")
                        if cpu_limit:
                            offenders.append(
                                {
                                    "container_name": container.get("name"),
                                    "cpu_limit": str(cpu_limit),
                                }
                            )
                    if not offenders:
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Container has a CPU limit (CFS throttling risk)",
                            summary=(
                                f"{kind}/{name} sets CPU limits on "
                                f"{len(offenders)} container(s). CFS-quota throttling "
                                f"can spike tail latency even at low average CPU."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "offenders": offenders,
                            },
                            recommended_change=(
                                "Consider removing CPU limits and relying on CPU "
                                "requests + node-level cgroup fairness, unless you "
                                "have a specific multi-tenant fairness requirement."
                            ),
                            confidence=0.6,
                        )
                    )
                except Exception:
                    continue
        return findings
