"""Detector: ``all-to-all-replicas``.

Flags Deployments whose replicas talk to each other peer-to-peer. That
pattern (gossip, in-memory clustering, sharded caches with peer
discovery) usually wants stable identity and DNS -- a StatefulSet with a
headless Service -- not a Deployment.

Hubble-gated: returns no findings when :class:`HubbleClient` is
unavailable.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

PEER_FLOW_THRESHOLD: int = 5
DISTINCT_PAIR_THRESHOLD: int = 2
TIME_WINDOW_SECONDS: int = 300


def _deployments(manifests: Dict[Any, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, manifest in manifests.items():
        if (
            isinstance(key, tuple)
            and len(key) == 2
            and key[0] == "Deployment"
            and isinstance(manifest, dict)
        ):
            out.append(manifest)
    return out


def _name(manifest: Dict[str, Any]) -> Optional[str]:
    md = manifest.get("metadata") if isinstance(manifest, dict) else None
    if isinstance(md, dict):
        return md.get("name")
    return None


def _has_owner(pod: Dict[str, Any], kind: str, name: str) -> bool:
    md = pod.get("metadata") or {}
    for ref in md.get("ownerReferences") or []:
        if ref.get("kind") == kind and ref.get("name") == name:
            return True
    return False


def _owned_pod_names(
    deployment_name: str, manifests: Dict[Any, Any], pods: List[Dict[str, Any]]
) -> Set[str]:
    """Return the set of pod names owned by the named Deployment.

    Walks Pod -> ReplicaSet -> Deployment, mirroring
    :meth:`AdviceEngine._filter_workload_scope` so the two views agree.
    """
    rs_names: Set[str] = set()
    for key, manifest in manifests.items():
        if not (isinstance(key, tuple) and key[0] == "ReplicaSet"):
            continue
        if not isinstance(manifest, dict):
            continue
        if _has_owner(manifest, "Deployment", deployment_name):
            rs_name = _name(manifest)
            if rs_name:
                rs_names.add(rs_name)

    out: Set[str] = set()
    for pod in pods:
        if _has_owner(pod, "Deployment", deployment_name):
            n = _name(pod)
            if n:
                out.add(n)
            continue
        for rs_name in rs_names:
            if _has_owner(pod, "ReplicaSet", rs_name):
                n = _name(pod)
                if n:
                    out.add(n)
                break
    return out


class AllToAllReplicas(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "all-to-all-replicas"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "workload-pattern"
    requires_hubble: ClassVar[bool] = True

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        if ctx.hubble is None:
            return []
        status = await ctx.hubble.status()
        if not status.available:
            return []

        deployments = _deployments(ctx.manifests)
        if not deployments:
            return []

        flows = await ctx.hubble.flows_for_namespace(
            ctx.namespace, since_seconds=TIME_WINDOW_SECONDS
        )

        findings: List[Finding] = []
        for dep in deployments:
            name = _name(dep)
            if not name:
                continue
            owned = _owned_pod_names(name, ctx.manifests, ctx.pods)
            if len(owned) < 2:
                continue

            flow_count = 0
            pairs: Set[Tuple[str, str]] = set()
            for f in flows:
                src = getattr(f, "source_pod", None)
                dst = getattr(f, "destination_pod", None)
                if not src or not dst or src == dst:
                    continue
                if src in owned and dst in owned:
                    flow_count += 1
                    pairs.add((src, dst))

            if flow_count < PEER_FLOW_THRESHOLD:
                continue
            if len(pairs) < DISTINCT_PAIR_THRESHOLD:
                continue

            findings.append(
                make_finding(
                    self,
                    resource_kind="Deployment",
                    resource_name=name,
                    namespace=ctx.namespace,
                    title="Replicas of a Deployment communicate peer-to-peer",
                    summary=(
                        f"Deployment/{name} has {len(pairs)} distinct peer pairs "
                        f"and {flow_count} inter-replica flows in "
                        f"{TIME_WINDOW_SECONDS}s."
                    ),
                    evidence={
                        "workload_name": name,
                        "peer_pod_count": len(owned),
                        "distinct_peer_pairs": len(pairs),
                        "flow_count": flow_count,
                        "time_window_seconds": TIME_WINDOW_SECONDS,
                    },
                    recommended_change=(
                        "Convert to StatefulSet + headless Service so peers can "
                        "discover each other by stable DNS (pod-0.svc, pod-1.svc, "
                        "...). Consider whether the data the peers exchange "
                        "justifies the operational complexity, or move state to an "
                        "external store."
                    ),
                    confidence=0.7,
                )
            )
        return findings
