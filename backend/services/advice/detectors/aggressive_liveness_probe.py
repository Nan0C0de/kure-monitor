"""Detector: ``aggressive-liveness-probe``.

Flags livenessProbes configured tightly enough that a transient slowdown
will restart the container. Aggressive liveness probes turn small
latency blips into crash loops.
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
    # CronJob nests jobTemplate.spec.template
    if "jobTemplate" in spec:
        return (
            spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
            or {}
        )
    return spec.get("template", {}).get("spec") or {}


class AggressiveLivenessProbe(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "aggressive-liveness-probe"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "reliability"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = _pod_template_spec(workload)
                    for container in pod_spec.get("containers") or []:
                        probe = container.get("livenessProbe")
                        if not isinstance(probe, dict):
                            continue
                        initial = probe.get("initialDelaySeconds")
                        timeout = probe.get("timeoutSeconds")
                        failure = probe.get("failureThreshold")
                        reasons = []
                        if isinstance(initial, int) and initial < 10:
                            reasons.append("initialDelaySeconds<10")
                        if isinstance(timeout, int) and timeout <= 1:
                            reasons.append("timeoutSeconds<=1")
                        if isinstance(failure, int) and failure <= 1:
                            reasons.append("failureThreshold<=1")
                        if not reasons:
                            continue
                        findings.append(
                            make_finding(
                                self,
                                resource_kind=kind,
                                resource_name=name,
                                namespace=ctx.namespace,
                                title="Aggressive livenessProbe thresholds",
                                summary=(
                                    f"{kind}/{name} container "
                                    f"'{container.get('name')}' has a livenessProbe "
                                    f"that is too strict ({', '.join(reasons)})."
                                ),
                                evidence={
                                    "container_name": container.get("name"),
                                    "initialDelaySeconds": initial,
                                    "timeoutSeconds": timeout,
                                    "failureThreshold": failure,
                                    "reasons": reasons,
                                },
                                recommended_change=(
                                    "Relax livenessProbe thresholds (initialDelay >= 10s, "
                                    "timeout >= 3s, failureThreshold >= 3). For slow-start "
                                    "apps use a startupProbe so liveness only kicks in "
                                    "once the process is up."
                                ),
                                confidence=0.5,
                            )
                        )
                except Exception:
                    continue
        return findings
