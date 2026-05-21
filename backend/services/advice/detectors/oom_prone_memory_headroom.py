"""Detector: ``oom-prone-memory-headroom``.

Flags containers where memory ``limit`` equals memory ``request``. With
no headroom between request and limit, any transient memory spike pushes
the container over its limit and the kernel OOM-kills it. Memory is
non-compressible: there is no equivalent of CPU throttling.
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


class OomProneMemoryHeadroom(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "oom-prone-memory-headroom"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
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
                        resources = container.get("resources") or {}
                        req = (resources.get("requests") or {}).get("memory")
                        lim = (resources.get("limits") or {}).get("memory")
                        if not req or not lim:
                            continue
                        if str(req) == str(lim):
                            offenders.append(
                                {
                                    "container_name": container.get("name"),
                                    "memory_request": str(req),
                                    "memory_limit": str(lim),
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
                            title="Memory limit equals request (no OOM headroom)",
                            summary=(
                                f"{kind}/{name} has {len(offenders)} container(s) "
                                f"with memory limit == request. Any spike will trip "
                                f"the OOM killer."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "offenders": offenders,
                            },
                            recommended_change=(
                                "Raise memory limit above the request (typically "
                                "1.5-2x) to give the container OOM headroom."
                            ),
                            confidence=0.8,
                        )
                    )
                except Exception:
                    continue
        return findings
