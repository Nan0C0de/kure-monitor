"""Detector: ``fan-out-pattern``.

Flags a single source pod that opens flows to an unusually large number
of distinct destinations within a short observation window. This is
often a worker doing per-destination work (e.g. fanning fetches out to
many backends) and is a sharding/DaemonSet candidate.

Hubble-gated: returns no findings when :class:`HubbleClient` is
unavailable.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

#: A source pod with more than this many distinct destinations fires.
FAN_OUT_THRESHOLD: int = 50

#: Default observation window passed to :class:`HubbleClient`.
TIME_WINDOW_SECONDS: int = 300


def _resolve_workload_for_pod(
    pod_name: str, manifests: Dict[Any, Any]
) -> Optional[Tuple[str, str]]:
    """Return ``(workload_kind, workload_name)`` for the pod's owning
    workload, walking ReplicaSet -> Deployment if needed.

    Returns ``None`` if no owner can be resolved -- callers should fall
    back to the pod itself.
    """
    pod = manifests.get(("Pod", pod_name))
    if not isinstance(pod, dict):
        return None
    md = pod.get("metadata") or {}
    for ref in md.get("ownerReferences") or []:
        kind = ref.get("kind")
        name = ref.get("name")
        if not kind or not name:
            continue
        if kind == "ReplicaSet":
            rs = manifests.get(("ReplicaSet", name))
            if isinstance(rs, dict):
                for rs_ref in (rs.get("metadata") or {}).get("ownerReferences") or []:
                    if rs_ref.get("kind") == "Deployment" and rs_ref.get("name"):
                        return ("Deployment", rs_ref["name"])
            # Couldn't walk further -- the RS is itself the owner.
            return (kind, name)
        return (kind, name)
    return None


def _destination_key(flow: Any) -> Optional[str]:
    """Return a stable string identifying the destination side of a flow.

    Prefers the destination workload; falls back to the destination pod.
    Returns ``None`` if neither is present (the flow is then ignored).
    """
    if getattr(flow, "destination_workload", None):
        return f"workload/{flow.destination_namespace}/{flow.destination_workload}"
    if getattr(flow, "destination_pod", None):
        return f"pod/{flow.destination_namespace}/{flow.destination_pod}"
    return None


class FanOutPattern(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "fan-out-pattern"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "networking"
    requires_hubble: ClassVar[bool] = True

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        if ctx.hubble is None:
            return []
        status = await ctx.hubble.status()
        if not status.available:
            return []

        # Scope: workload-scoped scan -> workload flows; otherwise namespace.
        if ctx.workload_kind and ctx.workload_name:
            flows = await ctx.hubble.flows_for_workload(
                ctx.namespace,
                ctx.workload_kind,
                ctx.workload_name,
                since_seconds=TIME_WINDOW_SECONDS,
            )
        else:
            flows = await ctx.hubble.flows_for_namespace(
                ctx.namespace, since_seconds=TIME_WINDOW_SECONDS
            )

        # source_pod -> set of destination keys
        per_source: Dict[str, Set[str]] = defaultdict(set)
        # Keep the most-recent destination strings for the evidence sample.
        per_source_examples: Dict[str, List[str]] = defaultdict(list)
        for f in flows:
            src = getattr(f, "source_pod", None)
            if not src:
                continue
            dest = _destination_key(f)
            if not dest:
                continue
            if dest in per_source[src]:
                continue
            per_source[src].add(dest)
            if len(per_source_examples[src]) < 5:
                per_source_examples[src].append(dest)

        findings: List[Finding] = []
        for source_pod, dest_set in per_source.items():
            count = len(dest_set)
            if count <= FAN_OUT_THRESHOLD:
                continue

            owner = _resolve_workload_for_pod(source_pod, ctx.manifests)
            if owner is not None:
                resource_kind, resource_name = owner
            else:
                resource_kind, resource_name = ("Pod", source_pod)

            findings.append(
                make_finding(
                    self,
                    resource_kind=resource_kind,
                    resource_name=resource_name,
                    namespace=ctx.namespace,
                    title="Pod fans out to many distinct destinations",
                    summary=(
                        f"Pod {source_pod} opened flows to {count} distinct "
                        f"destinations in {TIME_WINDOW_SECONDS}s."
                    ),
                    evidence={
                        "source_pod": source_pod,
                        "distinct_destinations": count,
                        "time_window_seconds": TIME_WINDOW_SECONDS,
                        "top_destinations": list(per_source_examples[source_pod]),
                    },
                    recommended_change=(
                        "If this pod is a gateway, ignore. If it's a worker doing "
                        "per-destination work, consider sharding the destinations "
                        "across multiple pods (or per-node via a DaemonSet)."
                    ),
                    confidence=0.6,
                )
            )

        return findings
