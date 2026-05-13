"""Detector: ``mutable-image-tag``.

Flags container images that use mutable tags (``latest``, no tag,
``dev``, ``edge``, ``nightly``). Mutable tags break reproducibility and
make rollbacks unreliable.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, List, Optional, Tuple

# Matches ``@<algo>:<hex>`` digest references, e.g. ``@sha256:abcd...``.
_DIGEST_RE = re.compile(r"@[A-Za-z0-9_+.-]+:[A-Fa-f0-9]+")

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

_MUTABLE_TAGS = {"latest", "dev", "edge", "nightly"}


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
    """Return (repo, tag-or-None) for ``image``.

    Strips a digest if present. Treats the last ``:`` after the final
    ``/`` as the tag separator (so ``host:5000/repo`` doesn't fool us).
    """
    if not isinstance(image, str) or not image:
        return ("", None)
    # Strip digest.
    if "@" in image:
        image = image.split("@", 1)[0]
    # Find the last '/' to isolate the name part.
    slash = image.rfind("/")
    name_part = image[slash + 1 :] if slash >= 0 else image
    host_part = image[: slash + 1] if slash >= 0 else ""
    if ":" in name_part:
        repo_name, tag = name_part.rsplit(":", 1)
        return (host_part + repo_name, tag)
    return (image, None)


class MutableImageTag(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "mutable-image-tag"
    default_severity: ClassVar[Severity] = Severity.LOW
    category: ClassVar[str] = "supply-chain"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        for kind in _WORKLOAD_KINDS:
            for workload in _manifests_by_kind(ctx.manifests, kind):
                try:
                    name = (workload.get("metadata") or {}).get("name")
                    if not name:
                        continue
                    pod_spec = _pod_template_spec(workload)
                    if not isinstance(pod_spec, dict):
                        continue
                    for container in pod_spec.get("containers") or []:
                        image = container.get("image")
                        # A digest pin (``@sha256:...`` or any ``@<algo>:<hex>``)
                        # is the most immutable reference possible — never flag.
                        if isinstance(image, str) and _DIGEST_RE.search(image):
                            continue
                        repo, tag = _parse_image_tag(image or "")
                        if not repo:
                            continue
                        if tag is None:
                            reason = "no-tag"
                        elif tag.lower() in _MUTABLE_TAGS:
                            reason = f"mutable-tag:{tag.lower()}"
                        else:
                            continue
                        findings.append(
                            make_finding(
                                self,
                                resource_kind=kind,
                                resource_name=name,
                                namespace=ctx.namespace,
                                title="Container uses a mutable image tag",
                                summary=(
                                    f"{kind}/{name} container "
                                    f"'{container.get('name')}' uses image "
                                    f"'{image}' ({reason}). Rollbacks and replays "
                                    f"will not be deterministic."
                                ),
                                evidence={
                                    "container_name": container.get("name"),
                                    "image": image,
                                    "image_repo": repo,
                                    "image_tag": tag,
                                    "reason": reason,
                                },
                                recommended_change=(
                                    "Pin the image to an immutable tag or a digest "
                                    "(``repo@sha256:...``) so deployments are "
                                    "reproducible."
                                ),
                                confidence=0.5,
                            )
                        )
                except Exception:
                    continue
        return findings
