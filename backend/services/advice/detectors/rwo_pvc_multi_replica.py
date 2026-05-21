"""Detector: ``rwo-pvc-multi-replica``.

Flags Deployments with ``replicas > 1`` that mount a ReadWriteOnce
PersistentVolumeClaim. RWO volumes can only be attached to one node at a
time, so additional replicas will be stuck in ContainerCreating waiting
for an attach that will never succeed. StatefulSets are skipped because
they use per-replica volumeClaimTemplates rather than a shared PVC.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List

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


class RwoPvcMultiReplica(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "rwo-pvc-multi-replica"
    default_severity: ClassVar[Severity] = Severity.HIGH
    category: ClassVar[str] = "storage"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []

        # Build map of pvc-name -> set(accessModes).
        pvc_modes: Dict[str, List[str]] = {}
        for pvc in _manifests_by_kind(ctx.manifests, "PersistentVolumeClaim"):
            try:
                name = (pvc.get("metadata") or {}).get("name")
                if not name:
                    continue
                modes = (pvc.get("spec") or {}).get("accessModes") or []
                pvc_modes[str(name)] = [str(m) for m in modes]
            except Exception:
                continue

        for workload in _manifests_by_kind(ctx.manifests, "Deployment"):
            try:
                name = (workload.get("metadata") or {}).get("name")
                if not name:
                    continue
                spec = workload.get("spec") or {}
                replicas = spec.get("replicas")
                if not isinstance(replicas, int) or replicas < 2:
                    continue
                pod_spec = spec.get("template", {}).get("spec") or {}
                rwo_claims: List[str] = []
                for vol in pod_spec.get("volumes") or []:
                    if not isinstance(vol, dict):
                        continue
                    pvc_ref = vol.get("persistentVolumeClaim") or {}
                    if not isinstance(pvc_ref, dict):
                        continue
                    claim_name = pvc_ref.get("claimName")
                    if not claim_name:
                        continue
                    modes = pvc_modes.get(str(claim_name))
                    if modes is None:
                        # PVC not in scope; can't verify -- skip silently.
                        continue
                    if "ReadWriteOnce" in modes and "ReadWriteMany" not in modes:
                        rwo_claims.append(str(claim_name))
                if not rwo_claims:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="Deployment",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="Deployment with replicas > 1 mounts a ReadWriteOnce PVC",
                        summary=(
                            f"Deployment/{name} runs {replicas} replicas but "
                            f"mounts ReadWriteOnce PVC(s) {rwo_claims}. Only one "
                            f"replica can attach the volume; the others will be "
                            f"stuck waiting for attach."
                        ),
                        evidence={
                            "workload_name": name,
                            "replicas": replicas,
                            "rwo_claims": rwo_claims,
                        },
                        recommended_change=(
                            "Use a ReadWriteMany StorageClass for shared state, "
                            "convert the workload to a StatefulSet with "
                            "per-replica volumeClaimTemplates, or scale the "
                            "Deployment back to 1 replica."
                        ),
                        confidence=0.9,
                    )
                )
            except Exception:
                continue
        return findings
