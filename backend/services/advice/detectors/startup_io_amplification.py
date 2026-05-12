"""Detector: ``startup-io-amplification``.

Flags workloads where every replica re-runs the same one-time startup
work -- database migrations, model/artifact downloads, ``git clone``
into an emptyDir, etc. On a multi-replica workload this means N copies
of the same work and N copies of the resulting failure if the upstream
is rate-limiting or briefly unavailable.

The heuristic is intentionally loose; this is a LOW-severity advisory.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional, Tuple

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_SUSPECT_SUBSTRINGS = (
    "migrate",
    "db:migrate",
    "flyway",
    "liquibase",
    "alembic",
    "download",
    "wget",
    "curl",
    "aws s3 cp",
    "aws s3 sync",
    "gsutil cp",
    "git clone",
)


def _manifests_of_kinds(
    manifests: Dict[Any, Any], kinds: Tuple[str, ...]
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, manifest in manifests.items():
        if (
            isinstance(key, tuple)
            and len(key) == 2
            and key[0] in kinds
            and isinstance(manifest, dict)
        ):
            out.append(manifest)
    return out


def _hpa_max_replicas_for(
    manifests: Dict[Any, Any], workload_kind: str, workload_name: str
) -> Optional[int]:
    for key, manifest in manifests.items():
        if not (
            isinstance(key, tuple)
            and len(key) == 2
            and key[0] == "HorizontalPodAutoscaler"
        ):
            continue
        if not isinstance(manifest, dict):
            continue
        target = (manifest.get("spec") or {}).get("scaleTargetRef") or {}
        if target.get("kind") == workload_kind and target.get("name") == workload_name:
            mx = (manifest.get("spec") or {}).get("maxReplicas")
            if isinstance(mx, int):
                return mx
    return None


def _suspect_command_strings(container: Dict[str, Any]) -> List[str]:
    """Return container command/args strings that look like one-time startup
    I/O work. The strings are returned verbatim so they can appear in the
    finding's evidence."""
    matched: List[str] = []
    parts: List[str] = []
    for raw in (container.get("command") or []) + (container.get("args") or []):
        if isinstance(raw, str):
            parts.append(raw)
    joined = " ".join(parts).lower()
    for substr in _SUSPECT_SUBSTRINGS:
        if substr in joined:
            # Record the matched substring (the source-of-truth value the
            # detector reacted to).
            matched.append(substr)
    return matched


class StartupIoAmplification(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "startup-io-amplification"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "startup"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        workloads = _manifests_of_kinds(ctx.manifests, ("Deployment", "StatefulSet"))
        for wl in workloads:
            f = self._inspect_workload(wl, ctx)
            if f is not None:
                findings.append(f)
        return findings

    def _inspect_workload(
        self, workload: Dict[str, Any], ctx: WorkloadContext
    ) -> Optional[Finding]:
        kind = workload.get("kind") or "Deployment"
        name = (workload.get("metadata") or {}).get("name")
        if not name:
            return None

        replicas = workload.get("spec", {}).get("replicas")
        if not isinstance(replicas, int):
            replicas = 1
        hpa_max = _hpa_max_replicas_for(ctx.manifests, kind, name)
        effective = max(replicas, hpa_max) if hpa_max is not None else replicas
        if effective < 3:
            return None

        pod_spec = workload.get("spec", {}).get("template", {}).get("spec", {})
        init_containers = pod_spec.get("initContainers") or []
        init_container_names = [
            (ic.get("name") or "") for ic in init_containers if isinstance(ic, dict)
        ]

        containers = pod_spec.get("containers") or []
        suspect_commands: List[str] = []
        for c in containers:
            if not isinstance(c, dict):
                continue
            suspect_commands.extend(_suspect_command_strings(c))

        if not init_containers and not suspect_commands:
            return None

        return make_finding(
            self,
            severity=Severity.LOW,
            resource_kind=kind,
            resource_name=name,
            namespace=ctx.namespace,
            title="Startup I/O work is repeated by every replica",
            summary=(
                f"{kind}/{name} runs at up to {effective} replicas and each one "
                f"appears to perform one-time startup I/O (initContainers or "
                f"download/migration commands)."
            ),
            evidence={
                "replicas": replicas,
                "hpa_max_replicas": hpa_max,
                "init_container_names": init_container_names,
                "suspect_commands": suspect_commands,
            },
            recommended_change=(
                "Move one-time work (migrations, model downloads) into a "
                "Kubernetes Job that runs once per release; or use an "
                "initContainer with leader-election; or bake the artifact "
                "into the image."
            ),
            confidence=0.6,
        )
