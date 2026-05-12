"""Detector: ``ephemeral-processes``.

Flags workloads whose pods restart often AND are very young -- a
signature of crash loops, aggressive scale-in, or node eviction.

This detector does NOT use Hubble; it inspects pod restart counts and
``creationTimestamp`` from the namespace manifests directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

RESTART_THRESHOLD: int = 3
MAX_AVG_AGE_SECONDS: int = 1800  # 30 minutes
MIN_OWNED_PODS: int = 2


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


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a tz-aware datetime, or ``None``.

    Accepts ``datetime`` instances directly (the Kubernetes client may
    already have parsed them). ``Z`` suffix is normalised to ``+00:00``
    for ``datetime.fromisoformat``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _max_restart_count(pod: Dict[str, Any]) -> int:
    status = pod.get("status") or {}
    container_statuses = status.get("containerStatuses") or []
    best = 0
    for cs in container_statuses:
        try:
            rc = int(cs.get("restartCount") or 0)
        except (TypeError, ValueError):
            rc = 0
        if rc > best:
            best = rc
    return best


def _pod_age_seconds(pod: Dict[str, Any], now: datetime) -> Optional[float]:
    md = pod.get("metadata") or {}
    created = _parse_iso(md.get("creationTimestamp"))
    if created is None:
        return None
    delta = now - created
    return max(0.0, delta.total_seconds())


def _resolve_workload(
    pod: Dict[str, Any], manifests: Dict[Any, Any]
) -> Optional[tuple]:
    """Return ``(workload_kind, workload_name)`` for the pod, walking RS->Deployment."""
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
            return (kind, name)
        if kind in ("StatefulSet", "DaemonSet"):
            return (kind, name)
        # Pod owned directly by anything else -- e.g. Job. We skip; Jobs
        # are expected to be short-lived.
    return None


class EphemeralProcesses(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "ephemeral-processes"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "reliability"
    requires_hubble: ClassVar[bool] = False

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        now = datetime.now(timezone.utc)

        # Group pods by their resolved workload.
        by_workload: Dict[tuple, List[Dict[str, Any]]] = {}
        for pod in ctx.pods:
            owner = _resolve_workload(pod, ctx.manifests)
            if owner is None:
                continue
            by_workload.setdefault(owner, []).append(pod)

        findings: List[Finding] = []
        for (workload_kind, workload_name), pods in by_workload.items():
            owned_count = len(pods)
            if owned_count < MIN_OWNED_PODS:
                continue

            max_restart = 0
            ages: List[float] = []
            for p in pods:
                rc = _max_restart_count(p)
                if rc > max_restart:
                    max_restart = rc
                age = _pod_age_seconds(p, now)
                if age is not None:
                    ages.append(age)

            if not ages:
                # Couldn't determine age for any pod -- skip rather than
                # firing on incomplete data.
                continue
            avg_age = sum(ages) / len(ages)

            if max_restart < RESTART_THRESHOLD:
                continue
            if avg_age >= MAX_AVG_AGE_SECONDS:
                continue

            findings.append(
                make_finding(
                    self,
                    resource_kind=workload_kind,
                    resource_name=workload_name,
                    namespace=ctx.namespace,
                    title="Pods restart frequently or live very short lives",
                    summary=(
                        f"{workload_kind}/{workload_name}: {owned_count} pods, "
                        f"max restart count {max_restart}, average pod age "
                        f"{int(avg_age)}s."
                    ),
                    evidence={
                        "workload_kind": workload_kind,
                        "workload_name": workload_name,
                        "owned_pod_count": owned_count,
                        "max_restart_count": max_restart,
                        "avg_pod_age_seconds": int(avg_age),
                        "recent_restart_count": max_restart,
                    },
                    recommended_change=(
                        "Diagnose root cause via pod events (OOMKilled, exit codes, "
                        "image pull errors). If aggressive HPA scale-in is the "
                        "cause, raise scaleDown.stabilizationWindowSeconds. If pods "
                        "are evicted by node pressure, add a PodDisruptionBudget."
                    ),
                    confidence=0.6,
                )
            )
        return findings
