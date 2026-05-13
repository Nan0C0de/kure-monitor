"""Detector: ``service-selector-no-match``.

Flags Services whose ``spec.selector`` matches no pod template
(Deployment/StatefulSet/DaemonSet/ReplicaSet/Pod) in the namespace.
Such Services have an empty Endpoints object and silently drop traffic.

Headless Services with ``publishNotReadyAddresses: true`` are skipped --
they are often used as DNS-only registration points.
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


class ServiceSelectorNoMatch(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "service-selector-no-match"
    default_severity: ClassVar[Severity] = Severity.HIGH
    category: ClassVar[str] = "networking"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []

        # Build label pools to compare against.
        label_pools: List[Dict[str, str]] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                labels = _template_labels(workload)
                if labels:
                    label_pools.append(labels)
        for pod in _manifests_by_kind(ctx.manifests, "Pod"):
            labels = _pod_labels(pod)
            if labels:
                label_pools.append(labels)

        for svc in _manifests_by_kind(ctx.manifests, "Service"):
            try:
                name = (svc.get("metadata") or {}).get("name")
                if not name:
                    continue
                spec = svc.get("spec") or {}
                # ExternalName services have no selector by design.
                if spec.get("type") == "ExternalName":
                    continue
                selector = spec.get("selector") or {}
                if not selector:
                    # Selector-less Service: endpoints are managed manually. Skip.
                    continue
                # Skip headless Service that explicitly publishes NotReady addrs.
                if (
                    spec.get("clusterIP") == "None"
                    and spec.get("publishNotReadyAddresses") is True
                ):
                    continue

                matched = any(
                    _selector_matches(selector, labels) for labels in label_pools
                )
                if matched:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="Service",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="Service selector matches no pods",
                        summary=(
                            f"Service/{name} selector {dict(selector)} matches no "
                            f"workload or Pod in namespace '{ctx.namespace}'. "
                            f"Traffic will be dropped at the kube-proxy layer."
                        ),
                        evidence={
                            "service_name": name,
                            "selector": dict(selector),
                        },
                        recommended_change=(
                            "Align the Service selector with the labels on the pod "
                            "template, or delete the Service if it is obsolete."
                        ),
                        confidence=0.9,
                    )
                )
            except Exception:
                continue
        return findings
