"""Detector: ``netpol-default-deny-no-allow``.

Flags namespaces that have a default-deny NetworkPolicy
(``podSelector: {}`` + ``policyTypes`` containing ``Ingress``) but no
other NetworkPolicy with a non-empty ``ingress`` rule. In that state
*all* ingress traffic is blocked and no policy whitelists anything.
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


def _is_default_deny_ingress(np: Dict[str, Any]) -> bool:
    spec = np.get("spec") or {}
    if not isinstance(spec, dict):
        return False
    pod_selector = spec.get("podSelector")
    if not isinstance(pod_selector, dict):
        return False
    # Empty selector means "all pods".
    if pod_selector.get("matchLabels") or pod_selector.get("matchExpressions"):
        return False
    if (
        pod_selector != {}
        and (
            "matchLabels" not in pod_selector and "matchExpressions" not in pod_selector
        )
        and pod_selector
    ):
        # Some unknown selector content. Skip.
        return False
    policy_types = spec.get("policyTypes") or []
    if not isinstance(policy_types, list):
        return False
    if "Ingress" not in policy_types:
        return False
    # Default-deny means no ingress rules. If rules exist this is an allow policy.
    ingress = spec.get("ingress")
    return not ingress  # None or [] both qualify as deny-all.


def _has_allow_ingress(np: Dict[str, Any]) -> bool:
    spec = np.get("spec") or {}
    if not isinstance(spec, dict):
        return False
    ingress = spec.get("ingress")
    return isinstance(ingress, list) and len(ingress) > 0


class NetpolDefaultDenyNoAllow(PatternDetector):
    """See module docstring."""

    id: ClassVar[str] = "netpol-default-deny-no-allow"
    default_severity: ClassVar[Severity] = Severity.MEDIUM
    category: ClassVar[str] = "networking"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        findings: List[Finding] = []
        netpols = _manifests_by_kind(ctx.manifests, "NetworkPolicy")
        if not netpols:
            return findings
        try:
            deny_policies = [np for np in netpols if _is_default_deny_ingress(np)]
            if not deny_policies:
                return findings
            any_allow = any(_has_allow_ingress(np) for np in netpols)
            if any_allow:
                return findings
            for np in deny_policies:
                name = (np.get("metadata") or {}).get("name") or ""
                findings.append(
                    make_finding(
                        self,
                        resource_kind="NetworkPolicy",
                        resource_name=name,
                        namespace=ctx.namespace,
                        title="Default-deny NetworkPolicy with no allow rules",
                        summary=(
                            f"NetworkPolicy/{name} denies all ingress to the "
                            f"namespace, but no other NetworkPolicy whitelists any "
                            f"traffic. All inbound connections will be dropped."
                        ),
                        evidence={
                            "netpol_name": name,
                            "total_netpols": len(netpols),
                            "deny_netpol_count": len(deny_policies),
                        },
                        recommended_change=(
                            "Add at least one NetworkPolicy with non-empty "
                            "spec.ingress rules to allow expected traffic, or remove "
                            "the default-deny if it was added by accident."
                        ),
                        confidence=0.7,
                    )
                )
        except Exception:
            return findings
        return findings
