"""Detector: ``requests-equal-limits-burstable``.

Flags Deployment containers where CPU ``requests`` equals CPU ``limits``.
Equal requests/limits give the pod Guaranteed QoS but eliminate any burst
headroom -- the container is throttled the instant it tries to exceed its
steady-state allocation, even if the node has idle CPU.

StatefulSets are intentionally skipped: many stateful services (databases,
queues) prefer predictable QoS over burst capacity.
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


class RequestsEqualLimitsBurstable(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "requests-equal-limits-burstable"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "resources"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for workload in _manifests_by_kind(ctx.manifests, "Deployment"):
            try:
                name = (workload.get("metadata") or {}).get("name")
                if not name:
                    continue
                pod_spec = (workload.get("spec") or {}).get("template", {}).get(
                    "spec"
                ) or {}
                offenders: List[Dict[str, Any]] = []
                for container in pod_spec.get("containers") or []:
                    if not isinstance(container, dict):
                        continue
                    resources = container.get("resources") or {}
                    requests = resources.get("requests") or {}
                    limits = resources.get("limits") or {}
                    cpu_req = requests.get("cpu")
                    cpu_lim = limits.get("cpu")
                    if not cpu_req or not cpu_lim:
                        continue
                    if str(cpu_req) == str(cpu_lim):
                        offenders.append(
                            {
                                "container_name": container.get("name"),
                                "cpu_request": str(cpu_req),
                                "cpu_limit": str(cpu_lim),
                            }
                        )
                if not offenders:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="Deployment",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="CPU requests equal limits (no burst headroom)",
                        summary=(
                            f"Deployment/{name} has {len(offenders)} container(s) "
                            f"with CPU requests == limits. The pod is Guaranteed QoS "
                            f"but cannot burst into idle node capacity."
                        ),
                        evidence={
                            "workload_name": name,
                            "offenders": offenders,
                        },
                        recommended_change=(
                            "Lower CPU requests below the limit (e.g. request 25-50% "
                            "of the limit) so the workload retains burst headroom."
                        ),
                        confidence=0.6,
                    )
                )
            except Exception:
                continue
        return findings
