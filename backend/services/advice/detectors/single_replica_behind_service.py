"""Detector: ``single-replica-behind-service``.

Flags Deployment workloads with ``replicas == 1`` (or unset, default 1)
that have a matching Service. A single-replica workload behind a Service
is a single point of failure: any pod restart drops traffic.
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


class SingleReplicaBehindService(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "single-replica-behind-service"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "availability"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        services = _manifests_by_kind(ctx.manifests, "Service")
        for workload in _manifests_by_kind(ctx.manifests, "Deployment"):
            try:
                name = (workload.get("metadata") or {}).get("name")
                if not name:
                    continue
                spec = workload.get("spec") or {}
                replicas = spec.get("replicas")
                # replicas unset => default 1; treat as single replica.
                if isinstance(replicas, int) and replicas != 1:
                    continue
                if replicas is not None and not isinstance(replicas, int):
                    continue
                labels = _template_labels(workload)
                if not labels:
                    continue
                matched_services: List[str] = []
                for svc in services:
                    selector = (svc.get("spec") or {}).get("selector") or {}
                    if _service_selector_matches(selector, labels):
                        svc_name = (svc.get("metadata") or {}).get("name")
                        if svc_name:
                            matched_services.append(str(svc_name))
                if not matched_services:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="Deployment",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="Single-replica Deployment behind a Service (SPOF)",
                        summary=(
                            f"Deployment/{name} has 1 replica but is selected by "
                            f"Service(s) {matched_services}. Any pod restart "
                            f"or eviction causes a traffic outage."
                        ),
                        evidence={
                            "workload_name": name,
                            "replicas": replicas if replicas is not None else 1,
                            "matched_services": matched_services,
                        },
                        recommended_change=(
                            "Increase replicas to >= 2 and configure a "
                            "PodDisruptionBudget so the Service has at least one "
                            "ready endpoint during voluntary disruptions."
                        ),
                        confidence=0.8,
                    )
                )
            except Exception:
                continue
        return findings
