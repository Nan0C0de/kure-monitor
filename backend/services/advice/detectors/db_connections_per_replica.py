"""Detector: ``db-connections-per-replica``.

Estimates the worst-case number of database connections a workload may
open across all of its replicas by inspecting common
DB-pool-size environment variables. If
``pool_size * effective_replicas`` exceeds a threshold the detector
fires; ``effective_replicas`` accounts for an associated HPA's
``maxReplicas`` when one is present.

The list of recognised env var names is intentionally non-exhaustive --
it covers the most common Spring / SQLAlchemy / Hikari / Postgres /
MySQL knobs.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional, Tuple

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_POOL_ENV_KEYS = (
    "DATABASE_POOL_SIZE",
    "DB_POOL_SIZE",
    "DB_MAX_CONNECTIONS",
    "DATABASE_MAX_CONNECTIONS",
    "POSTGRES_POOL_SIZE",
    "MYSQL_POOL_SIZE",
    "PGPOOL_SIZE",
    "SQLALCHEMY_POOL_SIZE",
    "HIKARI_MAXIMUM_POOL_SIZE",
    "SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE",
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
    """Return the maxReplicas of an HPA targeting (kind, name), if any."""
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


def _parse_int(val: Any) -> Optional[int]:
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            return int(val.strip())
        except (TypeError, ValueError):
            return None
    return None


def _find_configmap_value(
    manifests: Dict[Any, Any], cm_name: str, key: str
) -> Optional[str]:
    """Look up ``key`` in a ConfigMap's ``data`` block."""
    cm = manifests.get(("ConfigMap", cm_name))
    if not isinstance(cm, dict):
        return None
    data = cm.get("data") or {}
    val = data.get(key)
    if isinstance(val, str):
        return val
    return None


def _container_pool_size(
    container: Dict[str, Any], manifests: Dict[Any, Any]
) -> Optional[Tuple[int, str]]:
    """Return ``(pool_size, env_var_name)`` if a recognised pool env is
    found on this container (inline ``env`` or via ``envFrom`` -> ConfigMap).
    The maximum value across keys wins.

    ``Secret`` envFroms are skipped (values aren't safe to log).
    """
    best: Optional[Tuple[int, str]] = None

    # Inline env
    for entry in container.get("env") or []:
        name = entry.get("name")
        if name not in _POOL_ENV_KEYS:
            continue
        raw_value = entry.get("value")
        # If the env entry uses valueFrom -> configMapKeyRef we attempt to
        # resolve it; otherwise we skip (no value to inspect).
        if raw_value is None:
            value_from = entry.get("valueFrom") or {}
            cm_ref = value_from.get("configMapKeyRef") or {}
            cm_name = cm_ref.get("name")
            cm_key = cm_ref.get("key")
            if cm_name and cm_key:
                raw_value = _find_configmap_value(manifests, cm_name, cm_key)
        parsed = _parse_int(raw_value)
        if parsed is None:
            continue
        if best is None or parsed > best[0]:
            best = (parsed, name)

    # envFrom -> configMapRef
    for env_from in container.get("envFrom") or []:
        cm_ref = env_from.get("configMapRef") or {}
        cm_name = cm_ref.get("name")
        if not cm_name:
            continue
        cm = manifests.get(("ConfigMap", cm_name))
        if not isinstance(cm, dict):
            continue
        data = cm.get("data") or {}
        for key, raw_value in data.items():
            if key not in _POOL_ENV_KEYS:
                continue
            parsed = _parse_int(raw_value)
            if parsed is None:
                continue
            if best is None or parsed > best[0]:
                best = (parsed, key)

    return best


class DbConnectionsPerReplica(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "db-connections-per-replica"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "scaling"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        workloads = _manifests_of_kinds(ctx.manifests, ("Deployment", "StatefulSet"))
        for wl in workloads:
            f = self._inspect_workload(wl, ctx)
            if f is not None:
                findings.append(f)
        return findings

    # -- helpers --

    def _inspect_workload(
        self, workload: Dict[str, Any], ctx: WorkloadContext
    ) -> Optional[Finding]:
        kind = workload.get("kind") or "Deployment"
        name = (workload.get("metadata") or {}).get("name")
        if not name:
            return None
        pod_spec = workload.get("spec", {}).get("template", {}).get("spec", {})
        containers = pod_spec.get("containers") or []
        best: Optional[Tuple[int, str]] = None
        for container in containers:
            result = _container_pool_size(container, ctx.manifests)
            if result is None:
                continue
            if best is None or result[0] > best[0]:
                best = result
        if best is None:
            return None
        pool_size, pool_env_var = best

        replicas = workload.get("spec", {}).get("replicas")
        if not isinstance(replicas, int):
            replicas = 1

        hpa_max = _hpa_max_replicas_for(ctx.manifests, kind, name)
        effective = max(replicas, hpa_max) if hpa_max is not None else replicas
        total = pool_size * effective

        if total > 300:
            severity = Severity.HIGH
        elif total > 100:
            severity = Severity.MEDIUM
        else:
            return None

        return make_finding(
            self,
            severity=severity,
            resource_kind=kind,
            resource_name=name,
            namespace=ctx.namespace,
            title="DB connection pool may exhaust the database",
            summary=(
                f"{kind}/{name} configures a per-pod DB pool of {pool_size} "
                f"({pool_env_var}); at {effective} replicas the worst-case "
                f"connection count is {total}."
            ),
            evidence={
                "pool_size": pool_size,
                "pool_env_var": pool_env_var,
                "replicas": replicas,
                "hpa_max_replicas": hpa_max,
                "total_connections_worst_case": total,
            },
            recommended_change=(
                "Either lower the per-pod pool size, introduce a connection "
                "pooler (PgBouncer/ProxySQL), or cap HPA maxReplicas relative "
                "to your DB's connection limit."
            ),
            confidence=0.7,
        )
