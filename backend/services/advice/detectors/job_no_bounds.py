"""Detector: ``job-no-bounds``.

Flags Jobs (and CronJob.jobTemplate.spec) that have no
``activeDeadlineSeconds`` AND have ``backoffLimit`` unset or >= 6. Such
Jobs can retry forever and pin pod-quota indefinitely.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Tuple

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector


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


def _job_specs(manifests: Dict[Any, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Return [(owner_kind, owner_name, job_spec), ...]."""
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    for job in _manifests_by_kind(manifests, "Job"):
        name = (job.get("metadata") or {}).get("name") or ""
        spec = job.get("spec") or {}
        if isinstance(spec, dict):
            out.append(("Job", name, spec))
    for cj in _manifests_by_kind(manifests, "CronJob"):
        name = (cj.get("metadata") or {}).get("name") or ""
        spec = (cj.get("spec") or {}).get("jobTemplate", {}).get("spec") or {}
        if isinstance(spec, dict):
            out.append(("CronJob", name, spec))
    return out


class JobNoBounds(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "job-no-bounds"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "reliability"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for owner_kind, owner_name, spec in _job_specs(ctx.manifests):
            try:
                if not owner_name:
                    continue
                deadline = spec.get("activeDeadlineSeconds")
                backoff = spec.get("backoffLimit")
                # If a deadline is set, the job is bounded regardless of backoff.
                if isinstance(deadline, int) and deadline > 0:
                    continue
                # backoffLimit defaults to 6 in k8s when unset.
                effective_backoff = backoff if isinstance(backoff, int) else 6
                if effective_backoff < 6:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind=owner_kind,
                        resource_name=owner_name,
                        namespace=ctx.namespace,
                        title="Job has no time bound and a high retry limit",
                        summary=(
                            f"{owner_kind}/{owner_name} has no "
                            f"activeDeadlineSeconds and backoffLimit="
                            f"{backoff if backoff is not None else 'unset (default 6)'}. "
                            f"A wedged run will keep retrying for a long time."
                        ),
                        evidence={
                            "owner_kind": owner_kind,
                            "owner_name": owner_name,
                            "active_deadline_seconds": deadline,
                            "backoff_limit": backoff,
                        },
                        recommended_change=(
                            "Set spec.activeDeadlineSeconds to a sensible upper bound "
                            "and lower spec.backoffLimit (e.g. 2 or 3). For CronJobs "
                            "this lives under spec.jobTemplate.spec."
                        ),
                        confidence=0.5,
                    )
                )
            except Exception:
                continue
        return findings
