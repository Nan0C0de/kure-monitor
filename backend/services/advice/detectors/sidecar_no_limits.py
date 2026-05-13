"""Detector: ``sidecar-no-limits``.

Flags pod templates with 2+ containers where at least one container is
missing ``resources.limits.cpu`` or ``resources.limits.memory``. An
unbounded sidecar can starve the primary container on the same node.
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


class SidecarNoLimits(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "sidecar-no-limits"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "capacity"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = _pod_template_spec(workload)
                    containers = pod_spec.get("containers") or []
                    if len(containers) < 2:
                        continue
                    offenders = []
                    for container in containers:
                        if not isinstance(container, dict):
                            continue
                        limits = (container.get("resources") or {}).get("limits") or {}
                        missing = []
                        if not limits.get("cpu"):
                            missing.append("cpu")
                        if not limits.get("memory"):
                            missing.append("memory")
                        if missing:
                            offenders.append(
                                {
                                    "container_name": container.get("name"),
                                    "missing_limits": missing,
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
                            title="Multi-container pod has containers without resource limits",
                            summary=(
                                f"{kind}/{name} has {len(containers)} containers; "
                                f"{len(offenders)} are missing CPU or memory limits. "
                                f"An unbounded container can starve its siblings."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "container_count": len(containers),
                                "offenders": offenders,
                            },
                            recommended_change=(
                                "Set resources.limits.cpu and resources.limits.memory "
                                "on every container in the pod template, not just the "
                                "primary one."
                            ),
                            confidence=0.7,
                        )
                    )
                except Exception:
                    continue
        return findings
