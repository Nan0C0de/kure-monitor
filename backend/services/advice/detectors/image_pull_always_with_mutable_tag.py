"""Detector: ``image-pull-always-with-mutable-tag``.

Flags containers that combine ``imagePullPolicy: Always`` with a mutable
tag (``latest``, ``main``, ``stable``, or no tag at all). This pair
causes the kubelet to hit the registry on every pod start, slowing
restarts and producing non-deterministic rollouts -- two pods of the
same Deployment may pull subtly different images depending on when they
were scheduled.

This complements ``mutable-image-tag``: that detector flags the tag in
isolation; this one flags the pull-policy interaction.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from ..findings import Finding, Severity, WorkloadContext, make_finding
from .base import PatternDetector

_DIGEST_RE = re.compile(r"@[A-Za-z0-9_+.-]+:[A-Fa-f0-9]+")
_MUTABLE_TAGS = {"latest", "main", "master", "stable", "dev", "edge", "nightly"}

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


def _parse_image_tag(image: str) -> Tuple[str, Optional[str]]:
    if not isinstance(image, str) or not image:
        return ("", None)
    if "@" in image:
        image = image.split("@", 1)[0]
    slash = image.rfind("/")
    name_part = image[slash + 1 :] if slash >= 0 else image
    host_part = image[: slash + 1] if slash >= 0 else ""
    if ":" in name_part:
        repo_name, tag = name_part.rsplit(":", 1)
        return (host_part + repo_name, tag)
    return (image, None)


class ImagePullAlwaysWithMutableTag(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "image-pull-always-with-mutable-tag"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "image"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = _pod_template_spec(workload)
                    offenders: List[Dict[str, Any]] = []
                    for container in pod_spec.get("containers") or []:
                        if not isinstance(container, dict):
                            continue
                        policy = container.get("imagePullPolicy")
                        if policy != "Always":
                            continue
                        image = container.get("image")
                        if isinstance(image, str) and _DIGEST_RE.search(image):
                            continue
                        _, tag = _parse_image_tag(image or "")
                        if tag is None:
                            reason = "no-tag"
                        elif tag.lower() in _MUTABLE_TAGS:
                            reason = f"mutable-tag:{tag.lower()}"
                        else:
                            continue
                        offenders.append(
                            {
                                "container_name": container.get("name"),
                                "image": image,
                                "reason": reason,
                            }
                        )
                    if not offenders:
                        continue
                    findings.append(
                        make_finding(
                            self,
                            resource_kind=kind,
                            resource_name=name,
                            namespace=ctx.namespace,
                            title="imagePullPolicy: Always with a mutable tag",
                            summary=(
                                f"{kind}/{name} has {len(offenders)} container(s) "
                                f"pulling a mutable tag on every start. Pods of the "
                                f"same workload may end up running different image "
                                f"digests."
                            ),
                            evidence={
                                "workload_kind": kind,
                                "workload_name": name,
                                "offenders": offenders,
                            },
                            recommended_change=(
                                "Pin the image to a digest "
                                "(``repo@sha256:...``) and drop "
                                "imagePullPolicy: Always (or use IfNotPresent)."
                            ),
                            confidence=0.7,
                        )
                    )
                except Exception:
                    continue
        return findings
