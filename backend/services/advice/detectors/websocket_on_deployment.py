"""Detector: ``websocket-on-deployment``.

Flags ``Deployment`` workloads that observably carry WebSocket or other
long-lived connections. Deployments are the wrong primitive for this
shape: rolling updates kill long connections, and scale-in picks pods
arbitrarily. StatefulSets (or a sticky LB) are usually the fix.

Hubble-gated: returns no findings when :class:`HubbleClient` is
unavailable.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

#: A flow longer than this is considered "long-lived" for the purposes
#: of this detector.
LONG_LIVED_THRESHOLD_SECONDS: int = 300

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


def _flow_touches_workload(flow: Any, workload_name: str) -> bool:
    """True if either endpoint's workload matches ``workload_name``.

    We compare on name only -- the kind is implied by the iteration over
    Deployment manifests in the caller.
    """
    return (
        getattr(flow, "source_workload", None) == workload_name
        or getattr(flow, "destination_workload", None) == workload_name
    )


class WebSocketOnDeployment(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "websocket-on-deployment"
    default_severity: ClassVar[Severity] = Severity.HIGH
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

        # Pull all namespace flows once; iterate per deployment.
        flows = await ctx.hubble.flows_for_namespace(
            ctx.namespace, since_seconds=TIME_WINDOW_SECONDS
        )

        findings: List[Finding] = []
        for dep in deployments:
            name = _name(dep)
            if not name:
                continue
            l7_upgrade = 0
            long_lived = 0
            for flow in flows:
                if not _flow_touches_workload(flow, name):
                    continue
                l7 = getattr(flow, "l7_protocol", None)
                if l7 == "websocket":
                    l7_upgrade += 1
                duration = getattr(flow, "duration_seconds", None)
                if (
                    isinstance(duration, (int, float))
                    and duration > LONG_LIVED_THRESHOLD_SECONDS
                ):
                    long_lived += 1
            if l7_upgrade < 1 and long_lived < 1:
                continue

            findings.append(
                make_finding(
                    self,
                    resource_kind="Deployment",
                    resource_name=name,
                    namespace=ctx.namespace,
                    title="WebSocket / long-lived connections on a Deployment",
                    summary=(
                        f"Deployment/{name} carries long-lived or WebSocket "
                        f"connections; rolling updates and scale-in will drop them."
                    ),
                    evidence={
                        "workload_kind": "Deployment",
                        "workload_name": name,
                        "long_lived_connection_count": long_lived,
                        "l7_upgrade_count": l7_upgrade,
                        "time_window_seconds": TIME_WINDOW_SECONDS,
                    },
                    recommended_change=(
                        "Convert to StatefulSet for stable identity and predictable "
                        "scale-in, enable Service sessionAffinity: ClientIP, or add "
                        "a sticky load balancer in front. If brief drops are "
                        "acceptable, raise terminationGracePeriodSeconds and "
                        "implement graceful WS close."
                    ),
                    confidence=0.7,
                )
            )
        return findings
