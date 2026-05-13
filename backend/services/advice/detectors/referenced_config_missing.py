"""Detector: ``referenced-config-missing``.

Flags workloads that reference a ConfigMap or Secret which is absent
from the namespace's manifests. Covers ``envFrom``,
``env.valueFrom.configMapKeyRef``, ``env.valueFrom.secretKeyRef``,
``volumes.configMap``, and ``volumes.secret``. References marked
``optional: true`` are skipped (Kubernetes lets the pod start anyway).
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Set, Tuple

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_WORKLOAD_KINDS = (
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "ReplicaSet",
    "Job",
    "CronJob",
    "Pod",
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


def _pod_template_spec(workload: Dict[str, Any]) -> Dict[str, Any]:
    spec = workload.get("spec") or {}
    if not isinstance(spec, dict):
        return {}
    if "jobTemplate" in spec:
        return (
            spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
            or {}
        )
    if "template" in spec:
        return spec.get("template", {}).get("spec") or {}
    return spec


def _collect_refs(pod_spec: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """Return [(kind, name, source), ...] for referenced CM/Secret resources.

    ``kind`` is ``ConfigMap`` or ``Secret``; ``source`` describes where it
    came from (envFrom, env, volume). Refs flagged ``optional: true``
    are filtered out.
    """
    refs: List[Tuple[str, str, str]] = []
    all_containers: List[Dict[str, Any]] = []
    all_containers.extend(pod_spec.get("containers") or [])
    all_containers.extend(pod_spec.get("initContainers") or [])
    for container in all_containers:
        if not isinstance(container, dict):
            continue
        for entry in container.get("envFrom") or []:
            if not isinstance(entry, dict):
                continue
            cm = entry.get("configMapRef")
            if isinstance(cm, dict) and cm.get("name") and not cm.get("optional"):
                refs.append(("ConfigMap", cm["name"], "envFrom"))
            sec = entry.get("secretRef")
            if isinstance(sec, dict) and sec.get("name") and not sec.get("optional"):
                refs.append(("Secret", sec["name"], "envFrom"))
        for env in container.get("env") or []:
            if not isinstance(env, dict):
                continue
            vf = env.get("valueFrom")
            if not isinstance(vf, dict):
                continue
            cm = vf.get("configMapKeyRef")
            if isinstance(cm, dict) and cm.get("name") and not cm.get("optional"):
                refs.append(("ConfigMap", cm["name"], "env.valueFrom"))
            sec = vf.get("secretKeyRef")
            if isinstance(sec, dict) and sec.get("name") and not sec.get("optional"):
                refs.append(("Secret", sec["name"], "env.valueFrom"))
    for volume in pod_spec.get("volumes") or []:
        if not isinstance(volume, dict):
            continue
        cm = volume.get("configMap")
        if isinstance(cm, dict) and cm.get("name") and not cm.get("optional"):
            refs.append(("ConfigMap", cm["name"], "volume"))
        sec = volume.get("secret")
        if isinstance(sec, dict):
            sec_name = sec.get("secretName")
            if sec_name and not sec.get("optional"):
                refs.append(("Secret", sec_name, "volume"))
    return refs


class ReferencedConfigMissing(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "referenced-config-missing"
    default_severity: ClassVar[Severity] = Severity.HIGH
    category: ClassVar[str] = "config"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = _pod_template_spec(workload)
                    refs = _collect_refs(pod_spec)
                    if not refs:
                        continue
                    seen: Set[Tuple[str, str]] = set()
                    missing: List[Dict[str, str]] = []
                    for ref_kind, ref_name, source in refs:
                        if (ref_kind, ref_name) in seen:
                            continue
                        if (ref_kind, ref_name) in ctx.manifests:
                            continue
                        seen.add((ref_kind, ref_name))
                        missing.append(
                            {
                                "kind": ref_kind,
                                "name": ref_name,
                                "source": source,
                            }
                        )
                    if not missing:
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="Workload references missing ConfigMap or Secret",
                            summary=(
                                f"{kind}/{name} references "
                                f"{len(missing)} ConfigMap/Secret(s) that are absent "
                                f"from namespace '{ctx.namespace}'. The pod will fail "
                                f"to start unless the references are optional."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "missing_references": missing,
                            },
                            recommended_change=(
                                "Create the missing ConfigMap/Secret resources, "
                                "correct the reference names, or mark the references "
                                "``optional: true`` if the workload can tolerate "
                                "their absence."
                            ),
                            confidence=0.9,
                        )
                    )
                except Exception:
                    continue
        return findings
