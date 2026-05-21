"""Detector: ``job-restart-policy-mismatch``.

Flags Jobs and CronJobs whose pod template ``restartPolicy`` is anything
other than ``Never`` or ``OnFailure``. The Kubernetes API normally
rejects ``Always`` here, but webhook-mutated or drift-corrupted manifests
can end up with the wrong value. A missing restartPolicy is also flagged
because the default ``Always`` is invalid for Jobs.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_ALLOWED = {"Never", "OnFailure"}


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


def _job_pod_spec(workload: Dict[str, Any], kind: str) -> Dict[str, Any]:
    spec = workload.get("spec") or {}
    if kind == "CronJob":
        return (
            spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
            or {}
        )
    return spec.get("template", {}).get("spec") or {}


class JobRestartPolicyMismatch(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "job-restart-policy-mismatch"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "lifecycle"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in ("Job", "CronJob"):
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = _job_pod_spec(workload, kind)
                    rp = pod_spec.get("restartPolicy")
                    if rp in _ALLOWED:
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Job/CronJob has an invalid pod restartPolicy",
                            summary=(
                                f"{kind}/{name} pod template restartPolicy is "
                                f"{rp!r}. Jobs must use 'Never' or 'OnFailure'."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "restart_policy": rp,
                            },
                            recommended_change=(
                                "Set spec.template.spec.restartPolicy to 'Never' "
                                "(for one-shot tasks) or 'OnFailure' (for "
                                "retry-on-error tasks)."
                            ),
                            confidence=0.9,
                        )
                    )
                except Exception:
                    continue
        return findings
