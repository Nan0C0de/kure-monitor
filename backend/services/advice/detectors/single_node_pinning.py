"""Detector: ``single-node-pinning``.

Flags workloads whose pod template pins to a specific node, either via
``spec.nodeName`` or via a ``kubernetes.io/hostname`` entry in
``spec.nodeSelector``. Such pods cannot be rescheduled if the node goes
away, defeating Kubernetes' availability story.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_WORKLOAD_KINDS = (
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "ReplicaSet",
    "Job",
    "CronJob",
    "Pod",
)


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


def _pod_template_spec(workload: Dict[str, Any]) -> Dict[str, Any]:
    spec = workload.get("spec") or {}
    if not isinstance(spec, dict):
        return {}
    if "jobTemplate" in spec:
        return (
            spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
            or {}
        )
    if "template" in spec:
        return spec.get("template", {}).get("spec") or {}
    # Bare Pod: the spec itself is the pod spec.
    return spec


class SingleNodePinning(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "single-node-pinning"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "scheduling"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    # DaemonSet schedules one pod per node by design, skip.
                    if kind == "DaemonSet":
                        continue
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = _pod_template_spec(workload)
                    if not isinstance(pod_spec, dict):
                        continue
                    node_name = pod_spec.get("nodeName")
                    node_selector = pod_spec.get("nodeSelector") or {}
                    hostname = None
                    if isinstance(node_selector, dict):
                        hostname = node_selector.get("kubernetes.io/hostname")
                    reasons = []
                    if isinstance(node_name, str) and node_name:
                        reasons.append("nodeName")
                    if isinstance(hostname, str) and hostname:
                        reasons.append("nodeSelector[kubernetes.io/hostname]")
                    if not reasons:
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Workload pinned to a single node",
                            summary=(
                                f"{kind}/{name} pins its pods to a specific node "
                                f"({', '.join(reasons)}). If that node is drained or "
                                f"lost the workload cannot be rescheduled."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "node_name": node_name,
                                "hostname_selector": hostname,
                                "reasons": reasons,
                            },
                            recommended_change=(
                                "Remove spec.nodeName and the "
                                "kubernetes.io/hostname nodeSelector. Use a broader "
                                "nodeSelector / nodeAffinity (e.g. a node role label) "
                                "so any matching node can run the pod."
                            ),
                            confidence=0.7,
                        )
                    )
                except Exception:
                    continue
        return findings
