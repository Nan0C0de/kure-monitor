"""Detector: ``ingress-host-collision``.

Flags Ingresses in the namespace that share the same ``(host, path)``
tuple. Most Ingress controllers pick one winner non-deterministically
when multiple Ingresses claim the same route, producing surprising
production behavior.

Emits one finding per colliding group (the first Ingress in the group).
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Tuple

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


def _iter_routes(ing: Dict[str, Any]) -> List[Tuple[str, str]]:
    routes: List[Tuple[str, str]] = []
    spec = ing.get("spec") or {}
    for rule in spec.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        host = rule.get("host") or ""
        http = rule.get("http") or {}
        paths = http.get("paths") if isinstance(http, dict) else None
        if not paths:
            routes.append((str(host), "/"))
            continue
        for path in paths:
            if not isinstance(path, dict):
                continue
            p = path.get("path") or "/"
            routes.append((str(host), str(p)))
    return routes


class IngressHostCollision(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "ingress-host-collision"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "networking"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        # route -> list of ingress names that claim it
        route_owners: Dict[Tuple[str, str], List[str]] = {}
        for ing in _manifests_by_kind(ctx.manifests, "Ingress"):
            try:
                name = (ing.get("metadata") or {}).get("name")
                if not name:
                    continue
                for route in _iter_routes(ing):
                    route_owners.setdefault(route, []).append(str(name))
            except Exception:
                continue

        emitted: set = set()
        for route, owners in route_owners.items():
            if len(owners) < 2:
                continue
            first = owners[0]
            key = (first, route)
            if key in emitted:
                continue
            emitted.add(key)
            host, path = route
            findings.append(
                make_finding(
                    self,
                    resource_kind="Ingress",
                    resource_name=first,
                    namespace=ctx.namespace,
                    title="Multiple Ingresses claim the same host/path",
                    summary=(
                        f"Ingress(es) {owners} all declare a rule for "
                        f"host='{host}' path='{path}'. Most Ingress controllers "
                        f"pick a non-deterministic winner."
                    ),
                    evidence={
                        "host": host,
                        "path": path,
                        "colliding_ingresses": owners,
                    },
                    recommended_change=(
                        "Consolidate the duplicate Ingresses into one, or change "
                        "the host/path so each route has a single owner."
                    ),
                    confidence=0.9,
                )
            )
        return findings
