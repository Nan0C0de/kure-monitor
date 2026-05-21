"""Detector: ``pvc-no-storage-class``.

Flags PersistentVolumeClaims that have neither ``storageClassName`` nor
``volumeName`` set. Such PVCs rely entirely on the cluster's default
StorageClass; if the default is missing or has changed, the PVC stays
``Pending`` forever and the workload won't start.

Confidence is intentionally moderate -- many clusters do have a
sensible default and this pattern is harmless there.
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


class PvcNoStorageClass(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "pvc-no-storage-class"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "storage"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for pvc in _manifests_by_kind(ctx.manifests, "PersistentVolumeClaim"):
            try:
                name = (pvc.get("metadata") or {}).get("name")
                if not name:
                    continue
                spec = pvc.get("spec") or {}
                storage_class = spec.get("storageClassName")
                volume_name = spec.get("volumeName")
                if storage_class or volume_name:
                    continue
                findings.append(
                    make_finding(
                        self,
                        resource_kind="PersistentVolumeClaim",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="PVC has no storageClassName and no volumeName",
                        summary=(
                            f"PersistentVolumeClaim/{name} declares no "
                            f"storageClassName and no volumeName. It depends on "
                            f"the cluster default StorageClass; if there isn't "
                            f"one, the PVC will stay Pending."
                        ),
                        evidence={
                            "pvc_name": name,
                        },
                        recommended_change=(
                            "Set spec.storageClassName explicitly so the PVC "
                            "does not silently depend on the cluster default."
                        ),
                        confidence=0.6,
                    )
                )
            except Exception:
                continue
        return findings
