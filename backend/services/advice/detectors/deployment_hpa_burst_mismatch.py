"""Detector: ``deployment-hpa-burst-mismatch``.

Flags Horizontal Pod Autoscalers whose configuration is mismatched with
the workload they target. Three sub-patterns are covered:

* ``min == max``: the HPA can't actually scale.
* HPA pointing at a Deployment that mounts a ReadWriteOnce PVC -- the
  PVC will pin replicas to one node, making horizontal scale-out impossible.
* CPU-only HPA with a slow ``scaleUp.stabilizationWindowSeconds`` -- a
  reactive-only signal for bursty (request-rate driven) traffic.

Findings are reported against the *target Deployment*, not the HPA
itself, so that dismissals follow the workload as users would expect.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Iterable, List, Optional, Tuple

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector


def _normalise_manifests_by_kind(
    manifests: Dict[Any, Any], kind: str
) -> List[Dict[str, Any]]:
    """Return a list of dict manifests of the given kind from a context's
    ``manifests`` mapping. The mapping is keyed by ``(kind, name)`` tuples;
    values are plain dicts."""
    out: List[Dict[str, Any]] = []
    for key, manifest in manifests.items():
        if isinstance(key, tuple) and len(key) == 2 and key[0] == kind:
            if isinstance(manifest, dict):
                out.append(manifest)
    return out


def _find_manifest(
    manifests: Dict[Any, Any], kind: str, name: str
) -> Optional[Dict[str, Any]]:
    """Look up a manifest by (kind, name)."""
    m = manifests.get((kind, name))
    if isinstance(m, dict):
        return m
    return None


def _pvc_names_from_workload(workload: Dict[str, Any]) -> List[str]:
    """Return the list of PVC claim names referenced by the workload's pod
    template volumes."""
    out: List[str] = []
    pod_spec = workload.get("spec", {}).get("template", {}).get("spec", {})
    for vol in pod_spec.get("volumes") or []:
        pvc = vol.get("persistentVolumeClaim") or {}
        name = pvc.get("claimName")
        if name:
            out.append(name)
    return out


def _is_rwo(pvc: Dict[str, Any]) -> bool:
    """RWO is the Kubernetes default when accessModes is omitted."""
    modes = (pvc.get("spec") or {}).get("accessModes")
    if modes is None:
        return True
    return "ReadWriteOnce" in modes


def _metric_kinds(metrics: Iterable[Dict[str, Any]]) -> List[str]:
    """Return the list of HPA metric ``type`` values."""
    return [m.get("type", "") for m in metrics or []]


def _only_cpu_resource_metrics(metrics: List[Dict[str, Any]]) -> bool:
    """True when every metric is a Resource metric for CPU."""
    if not metrics:
        return False
    for m in metrics:
        if m.get("type") != "Resource":
            return False
        resource = m.get("resource") or {}
        if resource.get("name") != "cpu":
            return False
    return True


class DeploymentHpaBurstMismatch(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "deployment-hpa-burst-mismatch"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "scaling"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        hpas = _normalise_manifests_by_kind(ctx.manifests, "HorizontalPodAutoscaler")
        for hpa in hpas:
            findings.extend(self._inspect_hpa(hpa, ctx))
        return findings

    # -- helpers --

    def _inspect_hpa(self, hpa: Dict[str, Any], ctx: WorkloadContext) -> List[Finding]:
        spec = hpa.get("spec") or {}
        target = spec.get("scaleTargetRef") or {}
        target_kind = target.get("kind")
        target_name = target.get("name")
        if not target_kind or not target_name:
            return []

        # We only report findings against workloads we have a manifest for;
        # otherwise the finding's resource_kind/name wouldn't be dismissible.
        workload = _find_manifest(ctx.manifests, target_kind, target_name)
        if workload is None:
            return []

        min_replicas = spec.get("minReplicas")
        max_replicas = spec.get("maxReplicas")
        namespace = ctx.namespace
        out: List[Finding] = []

        # 1) collapsed range
        if (
            isinstance(min_replicas, int)
            and isinstance(max_replicas, int)
            and min_replicas == max_replicas
        ):
            out.append(
                make_finding(
                    self,
                    severity=Severity.HIGH,
                    resource_kind=target_kind,
                    resource_name=target_name,
                    namespace=namespace,
                    title="HPA range is collapsed (min == max)",
                    summary=(
                        f"HPA '{hpa.get('metadata', {}).get('name')}' targets "
                        f"{target_kind}/{target_name} with minReplicas == "
                        f"maxReplicas == {min_replicas}; it cannot scale."
                    ),
                    evidence={
                        "min_replicas": min_replicas,
                        "max_replicas": max_replicas,
                        "target_kind": target_kind,
                        "target_name": target_name,
                    },
                    recommended_change=(
                        "Either set maxReplicas > minReplicas, or remove the HPA "
                        "entirely."
                    ),
                    confidence=0.9,
                )
            )

        # 2) HPA on Deployment with RWO PVC
        if target_kind == "Deployment":
            pvc_names = _pvc_names_from_workload(workload)
            rwo_pvc_names: List[str] = []
            access_modes: List[List[str]] = []
            for pvc_name in pvc_names:
                pvc = _find_manifest(ctx.manifests, "PersistentVolumeClaim", pvc_name)
                if pvc is None:
                    continue
                if _is_rwo(pvc):
                    rwo_pvc_names.append(pvc_name)
                    modes = (pvc.get("spec") or {}).get("accessModes") or [
                        "ReadWriteOnce"
                    ]
                    access_modes.append(list(modes))
            if rwo_pvc_names:
                out.append(
                    make_finding(
                        self,
                        severity=Severity.HIGH,
                        resource_kind=target_kind,
                        resource_name=target_name,
                        namespace=namespace,
                        title="HPA on a Deployment with RWO PVC",
                        summary=(
                            f"Deployment '{target_name}' is scaled by an HPA but "
                            f"mounts a ReadWriteOnce PVC, which pins the workload "
                            f"to one node."
                        ),
                        evidence={
                            "target_name": target_name,
                            "pvc_names": rwo_pvc_names,
                            "access_modes": access_modes,
                        },
                        recommended_change=(
                            "Switch the workload to a StatefulSet, use a RWX volume "
                            "(NFS/EFS/Azure Files), or remove the HPA."
                        ),
                        confidence=0.9,
                    )
                )

        # 3) CPU-only HPA with slow scale-up window
        metrics = spec.get("metrics") or []
        behavior = spec.get("behavior") or {}
        scale_up = behavior.get("scaleUp") or {}
        stab_window = scale_up.get("stabilizationWindowSeconds")
        slow_scale_up = stab_window is None or stab_window >= 60
        if _only_cpu_resource_metrics(metrics) and slow_scale_up:
            out.append(
                make_finding(
                    self,
                    severity=Severity.MEDIUM,
                    resource_kind=target_kind,
                    resource_name=target_name,
                    namespace=namespace,
                    title="CPU-only HPA with slow scale-up for bursty traffic",
                    summary=(
                        f"HPA targeting {target_kind}/{target_name} uses CPU only "
                        f"and waits >= 60s before scaling up; bursty workloads "
                        f"will see latency spikes."
                    ),
                    evidence={
                        "metrics_kinds": _metric_kinds(metrics),
                        "stabilization_window_seconds": stab_window,
                    },
                    recommended_change=(
                        "Add a request-rate / queue-depth custom metric, or shorten "
                        "scaleUp.stabilizationWindowSeconds (e.g. to 0-15s)."
                    ),
                    confidence=0.6,
                )
            )

        return out
