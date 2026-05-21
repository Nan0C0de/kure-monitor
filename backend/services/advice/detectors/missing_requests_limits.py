"""Detector: ``missing-requests-limits``.

Flags containers that lack ``resources.requests`` or ``resources.limits``
for CPU or memory. Without requests, the scheduler can't reserve capacity
(BestEffort QoS); without limits, a single container can hog the node.

InitContainers are excluded -- they typically exit quickly and rightsizing
them gives little benefit.
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


class MissingRequestsLimits(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "missing-requests-limits"
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
                        requests = resources.get("requests") or {}
                        limits = resources.get("limits") or {}
                        missing_requests: List[str] = []
                        missing_limits: List[str] = []
                        if not requests.get("cpu"):
                            missing_requests.append("cpu")
                        if not requests.get("memory"):
                            missing_requests.append("memory")
                        if not limits.get("cpu"):
                            missing_limits.append("cpu")
                        if not limits.get("memory"):
                            missing_limits.append("memory")
                        if missing_requests or missing_limits:
                            offenders.append(
                                {
                                    "container_name": container.get("name"),
                                    "missing_requests": missing_requests,
                                    "missing_limits": missing_limits,
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
                            title="Container missing resource requests or limits",
                            summary=(
                                f"{kind}/{name} has {len(offenders)} container(s) "
                                f"missing CPU or memory requests/limits. Without "
                                f"requests the scheduler cannot reserve capacity; "
                                f"without limits the container can starve neighbors."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "offenders": offenders,
                            },
                            recommended_change=(
                                "Set resources.requests and resources.limits for "
                                "both cpu and memory on every container."
                            ),
                            confidence=0.8,
                        )
                    )
                except Exception:
                    continue
        return findings
