"""Detector: ``statefulset-emptydir-data``.

Flags StatefulSets that mount an emptyDir at a data-shaped path
(``/data``, ``/var/lib/*``, etc.). emptyDir is wiped on pod restart, so
using it for stateful storage defeats the purpose of a StatefulSet.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, List

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_DB_PATH_RE = re.compile(
    r"^/var/lib/(postgresql|postgres|mysql|mariadb|redis|mongodb|elasticsearch|cassandra)",
    re.IGNORECASE,
)


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


def _is_data_path(path: str) -> bool:
    if not isinstance(path, str) or not path:
        return False
    p = path.rstrip("/")
    lower = p.lower()
    if lower == "/data" or lower.startswith("/data/"):
        return True
    if lower.startswith("/var/lib/") or lower == "/var/lib":
        return True
    if _DB_PATH_RE.match(p):
        return True
    return False


class StatefulSetEmptyDirData(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "statefulset-emptydir-data"
    default_severity: ClassVar[Severity] = Severity.HIGH
    category: ClassVar[str] = "data"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for sts in _manifests_by_kind(ctx.manifests, "StatefulSet"):
            try:
                name = (sts.get("metadata") or {}).get("name")
                if not name:
                    continue
                pod_spec = (sts.get("spec") or {}).get("template", {}).get("spec") or {}
                volumes = pod_spec.get("volumes") or []
                empty_dir_names = {
                    v.get("name")
                    for v in volumes
                    if isinstance(v, dict) and "emptyDir" in v and v.get("name")
                }
                if not empty_dir_names:
                    continue

                for container in pod_spec.get("containers") or []:
                    for mount in container.get("volumeMounts") or []:
                        if not isinstance(mount, dict):
                            continue
                        vol_name = mount.get("name")
                        mount_path = mount.get("mountPath")
                        if vol_name not in empty_dir_names:
                            continue
                        if not _is_data_path(mount_path):
                            continue
                        findings.append(
                            make_finding(
                                self,
                                resource_kind="StatefulSet",
                                resource_name=name,
                                namespace=ctx.namespace,
                                title="StatefulSet mounts emptyDir at a data path",
                                summary=(
                                    f"StatefulSet/{name} mounts emptyDir volume "
                                    f"'{vol_name}' at '{mount_path}'. State will be "
                                    f"lost on every pod restart."
                                ),
                                evidence={
                                    "volume_name": vol_name,
                                    "mount_path": mount_path,
                                    "container_name": container.get("name"),
                                },
                                recommended_change=(
                                    "Replace the emptyDir with a PVC via "
                                    "spec.volumeClaimTemplates so each replica gets "
                                    "durable per-pod storage."
                                ),
                                confidence=0.9,
                            )
                        )
            except Exception:
                continue
        return findings
