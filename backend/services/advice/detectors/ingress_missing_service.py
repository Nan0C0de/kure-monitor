"""Detector: ``ingress-missing-service``.

Flags Ingress rules whose backend Service does not exist in the
namespace. Supports both networking.k8s.io/v1 (``backend.service.name``)
and the legacy extensions/v1beta1 form (``backend.serviceName``).
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Iterable, List, Optional, Set, Tuple

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


def _backend_service_name(backend: Any) -> Optional[str]:
    if not isinstance(backend, dict):
        return None
    # v1 form
    svc = backend.get("service")
    if isinstance(svc, dict):
        name = svc.get("name")
        if isinstance(name, str) and name:
            return name
    # legacy form
    legacy = backend.get("serviceName")
    if isinstance(legacy, str) and legacy:
        return legacy
    return None


def _iter_backends(ingress_spec: Dict[str, Any]) -> Iterable[Tuple[str, Any]]:
    """Yield (location, backend) for every backend slot in the Ingress."""
    default_backend = ingress_spec.get("defaultBackend")
    if isinstance(default_backend, dict):
        yield ("defaultBackend", default_backend)
    for rule in ingress_spec.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        http = rule.get("http") or {}
        paths = http.get("paths") if isinstance(http, dict) else None
        for path in paths or []:
            if not isinstance(path, dict):
                continue
            backend = path.get("backend")
            if isinstance(backend, dict):
                yield (f"rule[{rule.get('host', '*')}].path", backend)


class IngressMissingService(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "ingress-missing-service"
    default_severity: ClassVar[Severity] = Severity.HIGH
    category: ClassVar[str] = "networking"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        service_names: Set[str] = set()
        for svc in _manifests_by_kind(ctx.manifests, "Service"):
            try:
                n = (svc.get("metadata") or {}).get("name")
                if isinstance(n, str) and n:
                    service_names.add(n)
            except Exception:
                continue

        for ing in _manifests_by_kind(ctx.manifests, "Ingress"):
            try:
                name = (ing.get("metadata") or {}).get("name")
                if not name:
                    continue
                spec = ing.get("spec") or {}
                missing: List[Dict[str, str]] = []
                for location, backend in _iter_backends(spec):
                    svc_name = _backend_service_name(backend)
                    if not svc_name:
                        continue
                    if svc_name in service_names:
                        continue
                    missing.append({"location": location, "service_name": svc_name})
                if not missing:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="Ingress",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="Ingress references a missing Service",
                        summary=(
                            f"Ingress/{name} references "
                            f"{len(missing)} Service backend(s) that do not exist in "
                            f"namespace '{ctx.namespace}'."
                        ),
                        evidence={
                            "ingress_name": name,
                            "missing_backends": missing,
                        },
                        recommended_change=(
                            "Create the missing Services, fix the backend service "
                            "names, or remove the stale Ingress rules."
                        ),
                        confidence=0.9,
                    )
                )
            except Exception:
                continue
        return findings
