"""Detector: ``ports-but-no-service``.

Flags workloads that expose containerPorts but have no Service whose
selector matches their pod-template labels. The ports are unreachable
from outside the pod.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet")


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


class PortsButNoService(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "ports-but-no-service"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "networking"

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
                    container_ports: List[int] = []
                    for container in pod_spec.get("containers") or []:
                        for port in container.get("ports") or []:
                            if isinstance(port, dict):
                                cp = port.get("containerPort")
                                if isinstance(cp, int):
                                    container_ports.append(cp)
                    if not container_ports:
                        continue
                    labels = _template_labels(workload)
                    if not labels:
                        continue
                    matched = False
                    for svc in services:
                        selector = (svc.get("spec") or {}).get("selector") or {}
                        if _service_selector_matches(selector, labels):
                            matched = True
                            break
                    if matched:
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Workload exposes ports but has no Service",
                            summary=(
                                f"{kind}/{name} declares containerPorts "
                                f"{container_ports} but no Service in namespace "
                                f"'{ctx.namespace}' selects its pods. The ports are "
                                f"only reachable inside the pod network."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "container_ports": container_ports,
                                "template_labels": labels,
                            },
                            recommended_change=(
                                "Add a Service whose selector matches the pod-template "
                                "labels, or remove the unused containerPorts."
                            ),
                            confidence=0.5,
                        )
                    )
                except Exception:
                    continue
        return findings
