"""Detector: ``service-target-port-mismatch``.

Flags Services whose ``spec.ports[].targetPort`` does not correspond to
any ``containerPort`` (or named port) on a pod template the Service
selects. The Service exists, the Endpoints object is populated, but
traffic lands on a closed port and times out.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Set, Tuple

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


def _pod_labels(pod: Dict[str, Any]) -> Dict[str, str]:
    try:
        labels = (pod.get("metadata") or {}).get("labels") or {}
        return {str(k): str(v) for k, v in labels.items()}
    except Exception:
        return {}


def _selector_matches(selector: Dict[str, Any], labels: Dict[str, str]) -> bool:
    if not isinstance(selector, dict) or not selector:
        return False
    for k, v in selector.items():
        if labels.get(str(k)) != str(v):
            return False
    return True


def _collect_pod_ports(pod_spec: Dict[str, Any]) -> Tuple[Set[int], Set[str]]:
    numeric: Set[int] = set()
    named: Set[str] = set()
    for container in pod_spec.get("containers") or []:
        if not isinstance(container, dict):
            continue
        for port in container.get("ports") or []:
            if not isinstance(port, dict):
                continue
            cp = port.get("containerPort")
            if isinstance(cp, int):
                numeric.add(cp)
            n = port.get("name")
            if isinstance(n, str) and n:
                named.add(n)
    return numeric, named


class ServiceTargetPortMismatch(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "service-target-port-mismatch"
    default_severity: ClassVar[Severity] = Severity.HIGH
    category: ClassVar[str] = "networking"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []

        # (labels, numeric_ports, named_ports) for every selectable pod source.
        selectable: List[Dict[str, Any]] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                labels = _template_labels(workload)
                if not labels:
                    continue
                pod_spec = (workload.get("spec") or {}).get("template", {}).get(
                    "spec"
                ) or {}
                numeric, named = _collect_pod_ports(pod_spec)
                selectable.append(
                    {"labels": labels, "numeric": numeric, "named": named}
                )
        for pod in _manifests_by_kind(ctx.manifests, "Pod"):
            labels = _pod_labels(pod)
            if not labels:
                continue
            numeric, named = _collect_pod_ports(pod.get("spec") or {})
            selectable.append({"labels": labels, "numeric": numeric, "named": named})

        for svc in _manifests_by_kind(ctx.manifests, "Service"):
            try:
                name = (svc.get("metadata") or {}).get("name")
                if not name:
                    continue
                spec = svc.get("spec") or {}
                if spec.get("type") == "ExternalName":
                    continue
                selector = spec.get("selector") or {}
                if not selector:
                    continue
                ports = spec.get("ports") or []
                if not ports:
                    continue
                # Aggregate ports across all matching pod sources.
                merged_numeric: Set[int] = set()
                merged_named: Set[str] = set()
                any_match = False
                for source in selectable:
                    if _selector_matches(selector, source["labels"]):
                        any_match = True
                        merged_numeric |= source["numeric"]
                        merged_named |= source["named"]
                if not any_match:
                    # Different detector (service-selector-no-match) handles this.
                    continue
                mismatches: List[Dict[str, Any]] = []
                for port in ports:
                    if not isinstance(port, dict):
                        continue
                    target = port.get("targetPort")
                    # targetPort is optional; defaults to port.
                    if target is None:
                        target = port.get("port")
                    if isinstance(target, int):
                        if target not in merged_numeric:
                            mismatches.append(
                                {
                                    "service_port": port.get("port"),
                                    "target_port": target,
                                    "container_ports": sorted(merged_numeric),
                                }
                            )
                    elif isinstance(target, str):
                        if target not in merged_named:
                            mismatches.append(
                                {
                                    "service_port": port.get("port"),
                                    "target_port": target,
                                    "named_ports": sorted(merged_named),
                                }
                            )
                if not mismatches:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="Service",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="Service targetPort doesn't match any container port",
                        summary=(
                            f"Service/{name} has {len(mismatches)} port(s) whose "
                            f"targetPort is not exposed by any selected pod. "
                            f"Traffic to these ports will be dropped."
                        ),
                        evidence={
                            "service_name": name,
                            "mismatches": mismatches,
                            "selector": dict(selector),
                        },
                        recommended_change=(
                            "Align Service.spec.ports[].targetPort with a "
                            "containerPort (numeric) or a named port on the "
                            "selected pod template."
                        ),
                        confidence=0.9,
                    )
                )
            except Exception:
                continue
        return findings
