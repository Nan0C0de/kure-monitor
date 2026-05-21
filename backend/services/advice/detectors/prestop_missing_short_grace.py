"""Detector: ``prestop-missing-short-grace``.

Flags Deployments behind a Service that combine:
  * no ``lifecycle.preStop`` hook on any container, AND
  * an explicit ``terminationGracePeriodSeconds < 30``.

Pods behind a Service need a grace window between the moment they receive
SIGTERM and the moment the Service controller removes them from Endpoints.
Without a preStop sleep (and with a short grace period), in-flight
requests are dropped on every rolling update.

We only flag when the grace period is *explicitly* short; an unset value
defaults to 30 in Kubernetes and is treated as acceptable here.
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


def _template_labels(workload: Dict[str, Any]) -> Dict[str, str]:
    try:
        labels = (
            workload.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("labels")
            or {}
        )
        return {str(k): str(v) for k, v in labels.items()}
    except Exception:
        return {}


def _service_selector_matches(selector: Dict[str, Any], labels: Dict[str, str]) -> bool:
    if not isinstance(selector, dict) or not selector:
        return False
    for k, v in selector.items():
        if labels.get(str(k)) != str(v):
            return False
    return True


class PreStopMissingShortGrace(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "prestop-missing-short-grace"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "lifecycle"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        services = _manifests_by_kind(ctx.manifests, "Service")
        for workload in _manifests_by_kind(ctx.manifests, "Deployment"):
            try:
                name = (workload.get("metadata") or {}).get("name")
                if not name:
                    continue
                pod_spec = (workload.get("spec") or {}).get("template", {}).get(
                    "spec"
                ) or {}
                grace = pod_spec.get("terminationGracePeriodSeconds")
                if not isinstance(grace, int) or grace >= 30:
                    continue
                # Any container has a preStop?
                has_prestop = False
                for container in pod_spec.get("containers") or []:
                    if not isinstance(container, dict):
                        continue
                    lifecycle = container.get("lifecycle") or {}
                    if isinstance(lifecycle, dict) and lifecycle.get("preStop"):
                        has_prestop = True
                        break
                if has_prestop:
                    continue
                labels = _template_labels(workload)
                if not labels:
                    continue
                matched_service = None
                for svc in services:
                    selector = (svc.get("spec") or {}).get("selector") or {}
                    if _service_selector_matches(selector, labels):
                        matched_service = (svc.get("metadata") or {}).get("name")
                        break
                if not matched_service:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="Deployment",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="Short grace period with no preStop on a Service-backed workload",
                        summary=(
                            f"Deployment/{name} (behind Service/{matched_service}) "
                            f"has terminationGracePeriodSeconds={grace} and no "
                            f"preStop hook. Rolling updates can drop in-flight "
                            f"requests before Endpoints converges."
                        ),
                        evidence={
                            "workload_name": name,
                            "service_name": matched_service,
                            "termination_grace_period_seconds": grace,
                        },
                        recommended_change=(
                            "Add a lifecycle.preStop exec/sleep of ~5s on the "
                            "container and raise terminationGracePeriodSeconds to "
                            "30 or higher so kube-proxy can remove the pod from "
                            "Endpoints before it stops accepting connections."
                        ),
                        confidence=0.7,
                    )
                )
            except Exception:
                continue
        return findings
