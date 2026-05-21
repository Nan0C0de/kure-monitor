"""Detector: ``networkpolicy-selects-nothing``.

Flags NetworkPolicy resources whose ``podSelector`` matches no pod
template (and no Pod manifest) in the namespace. The policy is dead
configuration -- it has no enforcement effect and is usually a sign of
a typo in the selector or a workload that was renamed/deleted.

Empty ``podSelector`` ({}) means "all pods in the namespace" and is
never flagged.
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
    match_labels = selector.get("matchLabels") or {}
    if not match_labels:
        # Without matchLabels (and ignoring matchExpressions for this MVP),
        # the policy isn't really targeted; treat as "matches all".
        return True
    for k, v in match_labels.items():
        if labels.get(str(k)) != str(v):
            return False
    return True


class NetworkPolicySelectsNothing(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "networkpolicy-selects-nothing"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "networking"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []

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

        for netpol in _manifests_by_kind(ctx.manifests, "NetworkPolicy"):
            try:
                name = (netpol.get("metadata") or {}).get("name")
                if not name:
                    continue
                spec = netpol.get("spec") or {}
                selector = spec.get("podSelector")
                if selector is None or selector == {}:
                    # Empty selector targets all pods in the namespace -- not dead.
                    continue
                if not isinstance(selector, dict):
                    continue
                match_labels = selector.get("matchLabels") or {}
                if not match_labels:
                    # No concrete matchLabels to check; skip.
                    continue
                matched = any(
                    _selector_matches(selector, labels) for labels in label_pools
                )
                if matched:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="NetworkPolicy",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="NetworkPolicy selects no pods",
                        summary=(
                            f"NetworkPolicy/{name} podSelector "
                            f"{dict(match_labels)} matches no workload or Pod in "
                            f"namespace '{ctx.namespace}'. The policy has no "
                            f"enforcement effect."
                        ),
                        evidence={
                            "netpol_name": name,
                            "pod_selector": dict(match_labels),
                        },
                        recommended_change=(
                            "Fix the podSelector labels to match an existing "
                            "workload, or delete the obsolete NetworkPolicy."
                        ),
                        confidence=0.8,
                    )
                )
            except Exception:
                continue
        return findings
