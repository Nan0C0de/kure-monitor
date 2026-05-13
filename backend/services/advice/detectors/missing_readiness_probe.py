"""Detector: ``missing-readiness-probe``.

Flags Deployments / StatefulSets / DaemonSets whose main container
exposes ports and is fronted by a Service, but defines no readinessProbe.
Without one, kube-proxy routes traffic to the pod the moment it starts,
which can cause request errors during boot.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet")


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


def _service_matches(service: Dict[str, Any], labels: Dict[str, str]) -> bool:
    sel = (service.get("spec") or {}).get("selector") or {}
    if not sel:
        return False
    for k, v in sel.items():
        if labels.get(str(k)) != str(v):
            return False
    return True


class MissingReadinessProbe(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "missing-readiness-probe"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "reliability"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        services = _manifests_by_kind(ctx.manifests, "Service")

        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = (workload.get("spec") or {}).get("template", {}).get(
                        "spec"
                    ) or {}
                    containers = pod_spec.get("containers") or []
                    if not containers:
                        continue
                    main = containers[0]
                    ports = main.get("ports") or []
                    if not ports:
                        continue
                    if main.get("readinessProbe"):
                        continue

                    labels = _template_labels(workload)
                    if not labels:
                        continue

                    matching_service: Optional[str] = None
                    for svc in services:
                        if _service_matches(svc, labels):
                            matching_service = (svc.get("metadata") or {}).get("name")
                            break
                    if not matching_service:
                        continue

                    port_numbers = [
                        p.get("containerPort") for p in ports if isinstance(p, dict)
                    ]
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Service-fronted container has no readinessProbe",
                            summary=(
                                f"{kind}/{name} exposes ports but defines no "
                                f"readinessProbe on its main container, while "
                                f"Service/{matching_service} routes traffic to it."
                            ),
                            evidence={
                                "container_name": main.get("name"),
                                "container_ports": port_numbers,
                                "service_name": matching_service,
                            },
                            recommended_change=(
                                "Add a readinessProbe (httpGet, tcpSocket, or exec) "
                                "matching the application's healthcheck endpoint so "
                                "the pod is only added to the Service when ready."
                            ),
                            confidence=0.7,
                        )
                    )
                except Exception:
                    continue
        return findings
