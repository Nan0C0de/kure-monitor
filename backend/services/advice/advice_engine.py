"""AdviceEngine -- orchestrates the AI Advice scan flow.

Given a scope (namespace / workload / pod), the engine:

1. Builds a :class:`WorkloadContext` by fetching the namespace's
   manifests from :class:`services.topology_service.TopologyService` and
   converting them into plain dicts keyed by ``(kind, name)``.
2. Wipes stale, non-dismissed findings for the scope.
3. Runs every registered :class:`PatternDetector` once.
4. Decorates each finding via :class:`LLMExplainer` (sequential, to
   protect provider rate limits).
5. Persists each finding via the database mixin.

The engine is the only component that crosses these boundaries; the
individual pieces (detectors, explainer, persistence) are pure and
testable in isolation.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from llm_providers.base import LLMProvider

from .detector_settings import DetectorSettingsService
from .detectors import ALL_DETECTORS
from .explainer import LLMExplainer
from .findings import Finding, Severity, WorkloadContext
from .hubble import HubbleClient, StubHubbleClient

logger = logging.getLogger(__name__)


# Mapping from TopologyService context bucket -> Kubernetes kind.
# The buckets are populated by ``TopologyService._fetch_namespace_context``.
_BUCKET_TO_KIND: Tuple[Tuple[str, str], ...] = (
    ("pods", "Pod"),
    ("replicasets", "ReplicaSet"),
    ("services", "Service"),
    ("ingresses", "Ingress"),
    ("hpas", "HorizontalPodAutoscaler"),
    ("netpols", "NetworkPolicy"),
    ("jobs", "Job"),
    ("pvcs", "PersistentVolumeClaim"),
    ("configmaps", "ConfigMap"),
)


def _sanitize(obj: Any) -> Any:
    """Convert a kubernetes client object into a plain dict.

    Falls back to ``obj`` itself when it's already a dict (e.g. tests).
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    try:
        from kubernetes import client  # type: ignore

        return client.ApiClient().sanitize_for_serialization(obj)
    except Exception:
        # Best-effort: return as-is if the kubernetes client isn't usable.
        return obj


def _name_of(manifest: Dict[str, Any]) -> Optional[str]:
    md = manifest.get("metadata") if isinstance(manifest, dict) else None
    if isinstance(md, dict):
        return md.get("name")
    return None


def _has_owner(pod: Dict[str, Any], owner_kind: str, owner_name: str) -> bool:
    md = pod.get("metadata") or {}
    for ref in md.get("ownerReferences") or []:
        if ref.get("kind") == owner_kind and ref.get("name") == owner_name:
            return True
    return False


def _pod_template_labels(workload: Dict[str, Any]) -> Dict[str, str]:
    template = (
        workload.get("spec", {}).get("template", {})
        if isinstance(workload, dict)
        else {}
    )
    md = template.get("metadata") or {}
    labels = md.get("labels") or {}
    return labels if isinstance(labels, dict) else {}


def _selector_matches(
    selector: Optional[Dict[str, str]], labels: Optional[Dict[str, str]]
) -> bool:
    if not selector:
        return False
    if not labels:
        return False
    return all(labels.get(k) == v for k, v in selector.items())


class AdviceEngine:
    """Coordinates one advice scan from request to persisted findings."""

    def __init__(
        self,
        db: Any,
        topology_service: Any,
        llm_provider_getter: Callable[[], Optional[LLMProvider]],
        hubble_client: Optional[HubbleClient] = None,
        detector_settings: Optional[DetectorSettingsService] = None,
    ):
        self.db = db
        self.topology_service = topology_service
        self._llm_provider_getter = llm_provider_getter
        # Default to the always-unavailable stub so Layer-2 detectors
        # know to skip silently.
        self.hubble: HubbleClient = hubble_client or StubHubbleClient()
        self.detector_settings: DetectorSettingsService = (
            detector_settings or DetectorSettingsService(db)
        )
        # Instantiate each detector class once -- detectors are stateless.
        self._detectors = [cls() for cls in ALL_DETECTORS]

    async def scan(
        self,
        *,
        namespace: str,
        workload_kind: Optional[str] = None,
        workload_name: Optional[str] = None,
        pod_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Run all detectors over the requested scope.

        Returns a list of persisted finding dicts (the JSON-friendly form
        emitted by :meth:`Finding.to_wire`, plus ``id`` and ``is_new``).
        """
        ctx = await self._build_context(
            namespace=namespace,
            workload_kind=workload_kind,
            workload_name=workload_name,
            pod_name=pod_name,
        )

        # Wipe stale, non-dismissed findings for this scope so resolved
        # issues disappear from the UI. Dismissed findings are preserved.
        resource_kind_for_clear: Optional[str] = None
        resource_name_for_clear: Optional[str] = None
        if pod_name is not None and workload_kind and workload_name:
            resource_kind_for_clear = workload_kind
            resource_name_for_clear = workload_name
        elif workload_name is not None:
            resource_kind_for_clear = workload_kind
            resource_name_for_clear = workload_name
        try:
            await self.db.clear_advice_findings_for_scope(
                namespace=namespace,
                resource_kind=resource_kind_for_clear,
                resource_name=resource_name_for_clear,
            )
        except Exception:
            logger.exception(
                "AdviceEngine: clear_advice_findings_for_scope failed for ns=%s",
                namespace,
            )

        # Apply the persisted enable/disable map BEFORE iterating so a
        # disabled detector neither runs nor logs noise. Missing entries
        # default to enabled.
        try:
            settings_map = await self.detector_settings.get_all()
        except Exception:
            logger.exception(
                "AdviceEngine: detector_settings.get_all failed; running all detectors"
            )
            settings_map = {}
        detectors = [d for d in self._detectors if settings_map.get(d.id, True)]
        skipped = len(self._detectors) - len(detectors)
        if skipped:
            logger.info(
                "AdviceEngine: skipping %d detector(s) disabled via settings", skipped
            )

        # Run every detector. A detector raising must not stop the scan.
        raw_findings: List[Finding] = []
        for detector in detectors:
            try:
                produced = await detector.detect(ctx)
            except Exception:
                logger.exception(
                    "AdviceEngine: detector %s raised; continuing with other detectors",
                    getattr(detector, "id", type(detector).__name__),
                )
                continue
            if produced:
                raw_findings.extend(produced)

        # NOTE: LLM explanations are deferred to view-time (see
        # ``explain_finding`` below + ``POST /api/advice/findings/{id}/explain``).
        # Scans persist findings with ``explanation=None`` and the frontend
        # requests an explanation on demand when the user opens a finding.

        # Persist and collect the wire-shape dicts to return.
        persisted: List[Dict[str, Any]] = []
        for finding in raw_findings:
            wire = finding.to_wire().model_dump()
            try:
                finding_id, is_new = await self.db.save_advice_finding(wire)
            except Exception:
                logger.exception(
                    "AdviceEngine: save_advice_finding failed for %s/%s",
                    finding.detector_id,
                    finding.resource_name,
                )
                continue
            wire["id"] = finding_id
            wire["is_new"] = is_new
            persisted.append(wire)
        return persisted

    # ----------------------------------------------------------------- explain

    async def explain_finding(self, finding_id: int) -> Optional[Dict[str, Any]]:
        """Generate (or return cached) explanation for a single finding.

        Read-modify-write flow:

        1. Load row by ``finding_id``. Returns ``None`` if missing.
        2. If ``explanation`` is already populated and non-empty, return the
           existing row dict (no LLM call -- idempotent).
        3. Otherwise reconstruct a :class:`Finding` from the row, run the
           :class:`LLMExplainer`, and persist the new explanation via
           :meth:`db.update_advice_finding_explanation`.
        4. Return the (possibly updated) wire-shape dict.

        If the explainer returns the finding unchanged (no provider, LLM
        error, or empty content), nothing is persisted and the row is
        returned as-is. The frontend surfaces the "no explanation" state.
        """
        row = await self.db.get_advice_finding_by_id(finding_id)
        if not row:
            return None

        existing = row.get("explanation")
        if existing and existing.strip():
            return row

        try:
            severity = Severity(row.get("severity"))
        except ValueError:
            severity = Severity.LOW

        finding = Finding(
            detector_id=row["detector_id"],
            severity=severity,
            category=row["category"],
            title=row["title"],
            summary=row["summary"],
            resource_kind=row["resource_kind"],
            resource_name=row["resource_name"],
            namespace=row["namespace"],
            evidence=row.get("evidence") or {},
            recommended_change=row.get("recommended_change") or "",
            confidence=float(row.get("confidence") or 0.0),
            explanation=None,
        )

        explainer = LLMExplainer(self._llm_provider_getter())
        try:
            explained = await explainer.explain(finding)
        except Exception:
            logger.exception(
                "AdviceEngine: explainer crashed for finding id=%s", finding_id
            )
            return row

        if not explained.explanation:
            # Explainer was a no-op (no provider, LLM error, empty content).
            return row

        try:
            await self.db.update_advice_finding_explanation(
                finding_id, explained.explanation
            )
        except Exception:
            logger.exception(
                "AdviceEngine: update_advice_finding_explanation failed for id=%s",
                finding_id,
            )
            # Fall through and return the row with the in-memory explanation
            # so the caller still sees the freshly generated text.
            row["explanation"] = explained.explanation
            return row

        row["explanation"] = explained.explanation
        return row

    # ------------------------------------------------------------------ context

    async def _build_context(
        self,
        *,
        namespace: str,
        workload_kind: Optional[str],
        workload_name: Optional[str],
        pod_name: Optional[str],
    ) -> WorkloadContext:
        """Build a scoped :class:`WorkloadContext` from the topology service."""
        ns_ctx = await self.topology_service._fetch_namespace_context(namespace)

        # We also need the workload manifests themselves (Deployments,
        # StatefulSets, etc.). Try the topology service if it exposes a
        # helper; otherwise fetch each kind individually using known APIs.
        workload_manifests = await self._fetch_workload_manifests(namespace)

        # Build a (kind, name) -> manifest dict mapping.
        manifests: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for bucket, kind in _BUCKET_TO_KIND:
            for raw in ns_ctx.get(bucket) or []:
                m = _sanitize(raw)
                if not isinstance(m, dict):
                    continue
                name = _name_of(m)
                if not name:
                    continue
                # Ensure kind is set on the manifest dict so detectors can
                # rely on it even when the K8s client omits it.
                m.setdefault("kind", kind)
                manifests[(kind, name)] = m

        for kind, raw in workload_manifests:
            m = _sanitize(raw)
            if not isinstance(m, dict):
                continue
            name = _name_of(m)
            if not name:
                continue
            m.setdefault("kind", kind)
            manifests[(kind, name)] = m

        pods_all = list(ns_ctx.get("pods") or [])
        pods_sanitised: List[Dict[str, Any]] = []
        for raw in pods_all:
            m = _sanitize(raw)
            if isinstance(m, dict):
                m.setdefault("kind", "Pod")
                pods_sanitised.append(m)

        # ----- Apply scope filtering -----
        if pod_name is not None:
            pods_sanitised = [p for p in pods_sanitised if _name_of(p) == pod_name]
            # All manifests kept; only pod list narrowed.
        elif workload_name is not None and workload_kind is not None:
            manifests, pods_sanitised = self._filter_workload_scope(
                manifests=manifests,
                pods=pods_sanitised,
                workload_kind=workload_kind,
                workload_name=workload_name,
            )
        # else namespace scope: keep everything.

        return WorkloadContext(
            namespace=namespace,
            workload_kind=workload_kind,
            workload_name=workload_name,
            pod_name=pod_name,
            manifests=manifests,
            pods=pods_sanitised,
            hubble=self.hubble,
        )

    async def _fetch_workload_manifests(self, namespace: str) -> List[Tuple[str, Any]]:
        """Fetch Deployment / StatefulSet / DaemonSet / CronJob manifests
        for the namespace via the topology service's underlying clients.

        Returns ``[(kind, manifest), ...]``. If the topology service hasn't
        initialised its clients (no K8s available, e.g. in tests), returns
        an empty list and lets the namespace-context buckets cover what
        they can.
        """
        out: List[Tuple[str, Any]] = []

        ts = self.topology_service
        try:
            ts._init_k8s()
        except Exception:
            return out

        listers: Tuple[Tuple[str, Any], ...] = (
            ("Deployment", getattr(ts._apps, "list_namespaced_deployment", None)),
            ("StatefulSet", getattr(ts._apps, "list_namespaced_stateful_set", None)),
            ("DaemonSet", getattr(ts._apps, "list_namespaced_daemon_set", None)),
            ("CronJob", getattr(ts._batch, "list_namespaced_cron_job", None)),
        )
        for kind, fn in listers:
            if fn is None:
                continue
            try:
                listing = await ts._run(fn, namespace)
            except Exception:
                logger.warning(
                    "AdviceEngine: failed to list %s in ns=%s", kind, namespace
                )
                continue
            items = getattr(listing, "items", None) or []
            for item in items:
                out.append((kind, item))
        return out

    def _filter_workload_scope(
        self,
        *,
        manifests: Dict[Tuple[str, str], Dict[str, Any]],
        pods: List[Dict[str, Any]],
        workload_kind: str,
        workload_name: str,
    ) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]], List[Dict[str, Any]]]:
        """Restrict ``manifests`` / ``pods`` to a single workload's scope."""
        workload = manifests.get((workload_kind, workload_name))
        kept: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Always include the workload itself if present.
        if workload is not None:
            kept[(workload_kind, workload_name)] = workload

        pod_labels = _pod_template_labels(workload) if workload else {}

        # ReplicaSets owned by the Deployment (for pod ownership chain).
        owned_rs_names: List[str] = []
        if workload_kind == "Deployment":
            for (kind, name), manifest in manifests.items():
                if kind != "ReplicaSet":
                    continue
                if _has_owner(manifest, "Deployment", workload_name):
                    kept[(kind, name)] = manifest
                    owned_rs_names.append(name)

        # HPAs targeting the workload.
        for (kind, name), manifest in manifests.items():
            if kind != "HorizontalPodAutoscaler":
                continue
            target = (manifest.get("spec") or {}).get("scaleTargetRef") or {}
            if (
                target.get("kind") == workload_kind
                and target.get("name") == workload_name
            ):
                kept[(kind, name)] = manifest

        # PDBs (best-effort: kind PodDisruptionBudget if it shows up).
        for (kind, name), manifest in manifests.items():
            if kind != "PodDisruptionBudget":
                continue
            sel = (manifest.get("spec") or {}).get("selector") or {}
            match_labels = sel.get("matchLabels") or {}
            if _selector_matches(match_labels, pod_labels):
                kept[(kind, name)] = manifest

        # Services whose selector matches the workload's pod labels.
        for (kind, name), manifest in manifests.items():
            if kind != "Service":
                continue
            sel = (manifest.get("spec") or {}).get("selector") or {}
            if _selector_matches(sel, pod_labels):
                kept[(kind, name)] = manifest

        # NetworkPolicies in the namespace.
        for (kind, name), manifest in manifests.items():
            if kind != "NetworkPolicy":
                continue
            kept[(kind, name)] = manifest

        # PVCs referenced by the workload's pod template volumes.
        if workload is not None:
            pod_spec = workload.get("spec", {}).get("template", {}).get("spec", {})
            for vol in pod_spec.get("volumes") or []:
                pvc = vol.get("persistentVolumeClaim") or {}
                claim = pvc.get("claimName")
                if claim:
                    pvc_manifest = manifests.get(("PersistentVolumeClaim", claim))
                    if pvc_manifest is not None:
                        kept[("PersistentVolumeClaim", claim)] = pvc_manifest

        # ConfigMaps referenced by env / envFrom (so the DB-pool detector
        # can resolve values).
        if workload is not None:
            pod_spec = workload.get("spec", {}).get("template", {}).get("spec", {})
            cm_names: List[str] = []
            for c in pod_spec.get("containers") or []:
                for env_from in c.get("envFrom") or []:
                    cm_ref = env_from.get("configMapRef") or {}
                    n = cm_ref.get("name")
                    if n:
                        cm_names.append(n)
                for env in c.get("env") or []:
                    value_from = env.get("valueFrom") or {}
                    cm_ref = value_from.get("configMapKeyRef") or {}
                    n = cm_ref.get("name")
                    if n:
                        cm_names.append(n)
            for n in cm_names:
                m = manifests.get(("ConfigMap", n))
                if m is not None:
                    kept[("ConfigMap", n)] = m

        # Filter pods to those owned by the workload. For Deployments we
        # also include pods owned by the workload's ReplicaSets.
        filtered_pods: List[Dict[str, Any]] = []
        for pod in pods:
            if _has_owner(pod, workload_kind, workload_name):
                filtered_pods.append(pod)
                continue
            if workload_kind == "Deployment":
                for rs_name in owned_rs_names:
                    if _has_owner(pod, "ReplicaSet", rs_name):
                        filtered_pods.append(pod)
                        break

        return kept, filtered_pods
