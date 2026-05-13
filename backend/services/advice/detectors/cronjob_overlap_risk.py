"""Detector: ``cronjob-overlap-risk``.

Flags CronJobs whose ``concurrencyPolicy`` is unset or set to ``Allow``.
A slow run that overruns the next schedule will spawn a parallel Job
instance, which is rarely intentional.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List

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


class CronJobOverlapRisk(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "cronjob-overlap-risk"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "scheduling"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for cj in _manifests_by_kind(ctx.manifests, "CronJob"):
            try:
                name = (cj.get("metadata") or {}).get("name")
                if not name:
                    continue
                spec = cj.get("spec") or {}
                policy = spec.get("concurrencyPolicy")
                if policy and str(policy) != "Allow":
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="CronJob",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="CronJob allows concurrent runs",
                        summary=(
                            f"CronJob/{name} has concurrencyPolicy="
                            f"{policy or 'Allow (default)'}. An overrunning job will "
                            f"spawn a parallel instance at the next trigger."
                        ),
                        evidence={
                            "cronjob_name": name,
                            "concurrency_policy": policy or "Allow",
                            "schedule": spec.get("schedule"),
                        },
                        recommended_change=(
                            "Set spec.concurrencyPolicy to Forbid (most common) or "
                            "Replace, unless overlapping runs are explicitly desired."
                        ),
                        confidence=0.7,
                    )
                )
            except Exception:
                continue
        return findings
