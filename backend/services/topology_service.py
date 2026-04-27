"""Kubernetes topology graph builder.

Computes a deterministic graph from the K8s API for the Diagram UI. No LLM is
involved. Two scopes are supported:

- ``namespace``: full topology of a namespace, with groups by ``app.kubernetes.io/name``.
- ``workload``:  one workload (Deployment/StatefulSet/DaemonSet/Job/CronJob) and
  everything reachable from it (RS, Pods, Service, EndpointSlice/Endpoints,
  Ingress, HPA, NetworkPolicy, ConfigMap/Secret/PVC mounts).

Results are cached in-memory for 15 seconds, keyed by
``(scope, namespace, root_id_or_None)``.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

from models.models import DiagramEdge, DiagramGroup, DiagramNode, DiagramResponse


logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 15.0

# Workload kinds accepted as the root of a workload-scope diagram
WORKLOAD_ROOT_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}

# All kinds the diagram can reference. Used by the manifest endpoint.
ALL_DIAGRAM_KINDS = {
    "Deployment", "ReplicaSet", "Pod", "Service", "Endpoints", "EndpointSlice",
    "Ingress", "ConfigMap", "Secret", "PersistentVolumeClaim", "ServiceAccount",
    "HorizontalPodAutoscaler", "NetworkPolicy",
    "StatefulSet", "DaemonSet", "Job", "CronJob",
}

# Case-insensitive normalisation map.
_KIND_NORMALISE = {k.lower(): k for k in ALL_DIAGRAM_KINDS}

# Handful of labels we keep in node.metadata.labels (everything else is dropped
# to keep the payload small).
_KEEP_LABEL_KEYS = (
    "app",
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "app.kubernetes.io/component",
    "app.kubernetes.io/part-of",
    "app.kubernetes.io/version",
)


def normalise_kind(kind: str) -> Optional[str]:
    """Normalise a user-supplied kind string to canonical capitalisation.

    Returns ``None`` if the kind is not part of the diagram allow-list.
    """
    if not kind:
        return None
    return _KIND_NORMALISE.get(kind.lower())


def make_node_id(kind: str, namespace: str, name: str) -> str:
    return f"{kind}/{namespace}/{name}"


def _trim_labels(labels: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not labels:
        return {}
    return {k: v for k, v in labels.items() if k in _KEEP_LABEL_KEYS}


def _group_value(labels: Optional[Dict[str, str]]) -> Optional[str]:
    if not labels:
        return None
    return labels.get("app.kubernetes.io/name") or labels.get("app")


def _selector_matches(selector: Optional[Dict[str, str]], labels: Optional[Dict[str, str]]) -> bool:
    """Return True if the given equality selector matches the labels.

    We deliberately only support equality selectors on Services because the
    Service API itself is equality-only. NetworkPolicy uses matchLabels too.
    """
    if not selector:
        return False
    if labels is None:
        return False
    for k, v in selector.items():
        if labels.get(k) != v:
            return False
    return True


def _np_pod_selector_matches(pod_selector: Any, labels: Optional[Dict[str, str]]) -> bool:
    """NetworkPolicy podSelector matcher.

    ``pod_selector`` can be a kubernetes client object or a plain dict. We
    support empty selector (matches everything in namespace) and matchLabels
    only — matchExpressions are treated as non-matching for simplicity.
    """
    if pod_selector is None:
        return True
    match_labels = _attr(pod_selector, "match_labels", "matchLabels") or {}
    match_expressions = _attr(pod_selector, "match_expressions", "matchExpressions")

    if not match_labels and not match_expressions:
        return True

    if match_expressions:
        # Be conservative: if there are matchExpressions we don't fully evaluate,
        # only match when matchLabels match too. (Acceptable approximation.)
        pass

    return _selector_matches(match_labels, labels)


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    """Read an attribute from either a kubernetes client object or a dict.

    Tries each ``names`` candidate in order — first as a Python attribute
    (snake_case from the kubernetes client), then as a dict key (camelCase
    from a sanitised serialisation).
    """
    if obj is None:
        return default
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        else:
            val = getattr(obj, name, None)
            if val is not None:
                return val
    return default


def _meta(obj: Any) -> Any:
    return _attr(obj, "metadata")


def _meta_name(obj: Any) -> Optional[str]:
    return _attr(_meta(obj), "name")


def _meta_namespace(obj: Any) -> Optional[str]:
    return _attr(_meta(obj), "namespace")


def _meta_labels(obj: Any) -> Dict[str, str]:
    return _attr(_meta(obj), "labels") or {}


def _owner_refs(obj: Any) -> List[Any]:
    return _attr(_meta(obj), "owner_references", "ownerReferences") or []


def _items(listing: Any) -> List[Any]:
    return _attr(listing, "items", default=[]) or []


def _container_image(obj: Any) -> Optional[str]:
    """Return the first container image from a pod or workload pod-spec."""
    spec = _attr(obj, "spec")
    if spec is None:
        return None
    template = _attr(spec, "template")
    pod_spec = _attr(template, "spec") if template is not None else spec
    if pod_spec is None:
        return None
    containers = _attr(pod_spec, "containers") or []
    for c in containers:
        img = _attr(c, "image")
        if img:
            return img
    return None


def _pod_status_short(pod: Any) -> str:
    status = _attr(pod, "status")
    phase = _attr(status, "phase") or "Unknown"
    container_statuses = _attr(status, "container_statuses", "containerStatuses") or []
    if container_statuses:
        ready = sum(1 for cs in container_statuses if _attr(cs, "ready"))
        total = len(container_statuses)
        if phase == "Running":
            return f"{ready}/{total} Ready"
    return phase


def _workload_status_short(obj: Any, kind: str) -> str:
    status = _attr(obj, "status")
    spec = _attr(obj, "spec")
    if status is None:
        return "Unknown"
    if kind in ("Deployment", "ReplicaSet", "StatefulSet"):
        ready = _attr(status, "ready_replicas", "readyReplicas") or 0
        desired = _attr(spec, "replicas") if spec is not None else None
        if desired is None:
            desired = _attr(status, "replicas") or 0
        return f"{ready}/{desired} Ready"
    if kind == "DaemonSet":
        ready = _attr(status, "number_ready", "numberReady") or 0
        desired = _attr(status, "desired_number_scheduled", "desiredNumberScheduled") or 0
        return f"{ready}/{desired} Ready"
    if kind == "Job":
        succeeded = _attr(status, "succeeded") or 0
        failed = _attr(status, "failed") or 0
        active = _attr(status, "active") or 0
        if succeeded:
            return "Succeeded"
        if failed:
            return "Failed"
        if active:
            return "Active"
        return "Pending"
    if kind == "CronJob":
        last = _attr(status, "last_schedule_time", "lastScheduleTime")
        return "Scheduled" if last else "Pending"
    return "Ready"


def _replica_count(obj: Any) -> Optional[int]:
    spec = _attr(obj, "spec")
    if spec is None:
        return None
    val = _attr(spec, "replicas")
    if isinstance(val, int):
        return val
    return None


# --- Cache -------------------------------------------------------------------

class _TTLCache:
    def __init__(self, ttl: float):
        self._ttl = ttl
        self._store: Dict[Tuple, Tuple[float, DiagramResponse]] = {}

    def get(self, key: Tuple) -> Optional[DiagramResponse]:
        entry = self._store.get(key)
        if not entry:
            return None
        ts, val = entry
        if time.monotonic() - ts > self._ttl:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: Tuple, value: DiagramResponse) -> None:
        self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._store.clear()


# --- Service -----------------------------------------------------------------

class TopologyService:
    """Builds diagram graphs from the live K8s API."""

    def __init__(self):
        self._initialised = False
        self._core: Any = None
        self._apps: Any = None
        self._batch: Any = None
        self._networking: Any = None
        self._discovery: Any = None
        self._autoscaling: Any = None
        self._cache = _TTLCache(CACHE_TTL_SECONDS)

    # -- K8s client init ----------------------------------------------------

    def _init_k8s(self) -> None:
        if self._initialised:
            return
        if not K8S_AVAILABLE:
            raise RuntimeError("Kubernetes Python client is not installed")

        try:
            config.load_incluster_config()
            logger.info("Topology service: using in-cluster Kubernetes config")
        except Exception:
            try:
                config.load_kube_config()
                logger.info("Topology service: using local kubeconfig")
            except Exception as e:
                raise RuntimeError(f"Could not configure Kubernetes client: {e}")

        self._core = client.CoreV1Api()
        self._apps = client.AppsV1Api()
        self._batch = client.BatchV1Api()
        self._networking = client.NetworkingV1Api()
        self._discovery = client.DiscoveryV1Api()
        self._autoscaling = client.AutoscalingV1Api()
        self._initialised = True

    async def _run(self, fn, *args, **kwargs):
        """Run a sync K8s call in the default executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    # -- Public API ---------------------------------------------------------

    async def list_namespaces(self) -> List[str]:
        self._init_k8s()
        try:
            ns_list = await self._run(self._core.list_namespace)
        except Exception as e:
            logger.error(f"Failed to list namespaces: {e}")
            raise
        return sorted(_meta_name(n) for n in _items(ns_list) if _meta_name(n))

    async def get_namespace_diagram(self, namespace: str) -> DiagramResponse:
        cache_key = ("namespace", namespace, None)
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        self._init_k8s()

        # Gather all top-level workloads
        deployments = _items(await self._safe(self._apps.list_namespaced_deployment, namespace))
        statefulsets = _items(await self._safe(self._apps.list_namespaced_stateful_set, namespace))
        daemonsets = _items(await self._safe(self._apps.list_namespaced_daemon_set, namespace))
        jobs = _items(await self._safe(self._batch.list_namespaced_job, namespace))
        cronjobs = _items(await self._safe(self._batch.list_namespaced_cron_job, namespace))

        # Filter out Jobs that are owned by a CronJob — those will be picked up
        # via the CronJob workload traversal.
        standalone_jobs = [j for j in jobs if not _has_owner_kind(j, "CronJob")]

        # Pre-fetch heavy lists once for the namespace and reuse across walks.
        ctx = await self._fetch_namespace_context(namespace)

        nodes: Dict[str, DiagramNode] = {}
        edges_set: set = set()
        edges: List[DiagramEdge] = []

        def _add_node(node: DiagramNode) -> None:
            existing = nodes.get(node.id)
            if existing is None:
                nodes[node.id] = node
                return
            # Merge: prefer existing but augment metadata
            if node.metadata:
                merged = dict(existing.metadata or {})
                merged.update(node.metadata)
                existing.metadata = merged

        def _add_edge(source: str, target: str, etype: str) -> None:
            key = (source, target, etype)
            if key in edges_set:
                return
            edges_set.add(key)
            edges.append(DiagramEdge(source=source, target=target, type=etype))

        roots = (
            [("Deployment", d) for d in deployments]
            + [("StatefulSet", s) for s in statefulsets]
            + [("DaemonSet", d) for d in daemonsets]
            + [("Job", j) for j in standalone_jobs]
            + [("CronJob", c) for c in cronjobs]
        )

        for kind, obj in roots:
            self._traverse_workload(
                kind=kind,
                workload=obj,
                ctx=ctx,
                add_node=_add_node,
                add_edge=_add_edge,
                emit_policy_edges=False,
            )

        # Build groups by app label
        groups = self._build_groups(nodes, roots)

        response = DiagramResponse(
            scope="namespace",
            root_id=None,
            nodes=list(nodes.values()),
            edges=edges,
            groups=groups,
        )
        self._cache.set(cache_key, response)
        return response

    async def get_workload_diagram(self, namespace: str, kind: str, name: str) -> DiagramResponse:
        norm_kind = normalise_kind(kind)
        if norm_kind not in WORKLOAD_ROOT_KINDS:
            raise ValueError(
                f"Workload kind must be one of {sorted(WORKLOAD_ROOT_KINDS)}, got '{kind}'"
            )
        root_id = make_node_id(norm_kind, namespace, name)
        cache_key = ("workload", namespace, root_id)
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        self._init_k8s()

        try:
            workload = await self._read_workload(norm_kind, namespace, name)
        except Exception as e:
            raise

        ctx = await self._fetch_namespace_context(namespace)

        nodes: Dict[str, DiagramNode] = {}
        edges_set: set = set()
        edges: List[DiagramEdge] = []

        def _add_node(node: DiagramNode) -> None:
            existing = nodes.get(node.id)
            if existing is None:
                nodes[node.id] = node
                return
            if node.metadata:
                merged = dict(existing.metadata or {})
                merged.update(node.metadata)
                existing.metadata = merged

        def _add_edge(source: str, target: str, etype: str) -> None:
            key = (source, target, etype)
            if key in edges_set:
                return
            edges_set.add(key)
            edges.append(DiagramEdge(source=source, target=target, type=etype))

        self._traverse_workload(
            kind=norm_kind,
            workload=workload,
            ctx=ctx,
            add_node=_add_node,
            add_edge=_add_edge,
            emit_policy_edges=True,
        )

        response = DiagramResponse(
            scope="workload",
            root_id=root_id,
            nodes=list(nodes.values()),
            edges=edges,
            groups=[],
        )
        self._cache.set(cache_key, response)
        return response

    async def get_manifest_yaml(self, namespace: str, kind: str, name: str) -> str:
        """Return cleaned YAML for a single resource. Caller must validate kind."""
        import yaml  # local import keeps top-level light

        self._init_k8s()
        api_obj = await self._read_resource(kind, namespace, name)
        sanitised = client.ApiClient().sanitize_for_serialization(api_obj)
        if isinstance(sanitised, dict):
            sanitised.pop("status", None)
            md = sanitised.get("metadata") or {}
            for f in (
                "managedFields", "resourceVersion", "uid",
                "selfLink", "creationTimestamp", "generation",
            ):
                md.pop(f, None)
            sanitised["metadata"] = md
        return yaml.safe_dump(sanitised, default_flow_style=False)

    # -- Internal traversal -------------------------------------------------

    async def _safe(self, fn, namespace: str):
        try:
            return await self._run(fn, namespace)
        except Exception as e:
            logger.warning(f"Topology: list call {fn.__name__} for ns={namespace} failed: {e}")
            return None

    async def _fetch_namespace_context(self, namespace: str) -> Dict[str, Any]:
        """Fetch all the supporting lists once per request."""
        pods = _items(await self._safe(self._core.list_namespaced_pod, namespace))
        replicasets = _items(await self._safe(self._apps.list_namespaced_replica_set, namespace))
        services = _items(await self._safe(self._core.list_namespaced_service, namespace))
        ingresses = _items(await self._safe(self._networking.list_namespaced_ingress, namespace))
        hpas = _items(await self._safe(self._autoscaling.list_namespaced_horizontal_pod_autoscaler, namespace))
        netpols = _items(await self._safe(self._networking.list_namespaced_network_policy, namespace))
        jobs = _items(await self._safe(self._batch.list_namespaced_job, namespace))
        pvcs = _items(await self._safe(self._core.list_namespaced_persistent_volume_claim, namespace))
        configmaps = _items(await self._safe(self._core.list_namespaced_config_map, namespace))

        # EndpointSlice with fallback to Endpoints
        endpoint_slices: List[Any] = []
        endpoints: List[Any] = []
        try:
            slice_list = await self._run(self._discovery.list_namespaced_endpoint_slice, namespace)
            endpoint_slices = _items(slice_list)
            if not endpoint_slices:
                raise RuntimeError("empty slice list, fall back")
        except Exception as e:
            logger.info(
                f"Topology: EndpointSlice unavailable or empty for ns={namespace} ({e}), "
                f"falling back to Endpoints"
            )
            endpoints = _items(await self._safe(self._core.list_namespaced_endpoints, namespace))

        return {
            "namespace": namespace,
            "pods": pods,
            "replicasets": replicasets,
            "services": services,
            "ingresses": ingresses,
            "hpas": hpas,
            "netpols": netpols,
            "jobs": jobs,
            "pvcs": pvcs,
            "configmaps": configmaps,
            "endpoint_slices": endpoint_slices,
            "endpoints": endpoints,
        }

    def _traverse_workload(
        self,
        kind: str,
        workload: Any,
        ctx: Dict[str, Any],
        add_node,
        add_edge,
        emit_policy_edges: bool,
    ) -> None:
        """Walk outwards from a single workload, adding nodes and edges."""
        namespace = ctx["namespace"]
        wname = _meta_name(workload)
        wlabels = _meta_labels(workload)
        if not wname:
            return

        wid = make_node_id(kind, namespace, wname)

        # Workload pods (set later) — we keep a list for HPA / NP / Service matching.
        related_pods: List[Any] = []
        related_pvcs: set = set()

        # Relevant child workloads / pods
        if kind == "Deployment":
            # Find owned ReplicaSets and figure out which is current.
            owned_rses = [
                rs for rs in ctx["replicasets"]
                if _has_owner_kind_name(rs, "Deployment", wname)
            ]
            current_rs = _current_replica_set(owned_rses)
            for rs in owned_rses:
                rs_id = self._add_replica_set_node(rs, namespace, add_node)
                add_edge(wid, rs_id, "owns")
                if current_rs is not None and _meta_name(rs) == _meta_name(current_rs):
                    rs_pods = [
                        p for p in ctx["pods"]
                        if _has_owner_kind_name(p, "ReplicaSet", _meta_name(rs))
                    ]
                    for pod in rs_pods:
                        pod_id = self._add_pod_node(pod, namespace, add_node)
                        add_edge(rs_id, pod_id, "owns")
                        related_pods.append(pod)

        elif kind in ("StatefulSet", "DaemonSet"):
            sset_pods = [
                p for p in ctx["pods"]
                if _has_owner_kind_name(p, kind, wname)
            ]
            for pod in sset_pods:
                pod_id = self._add_pod_node(pod, namespace, add_node)
                add_edge(wid, pod_id, "owns")
                related_pods.append(pod)

        elif kind == "Job":
            job_pods = [
                p for p in ctx["pods"]
                if _has_owner_kind_name(p, "Job", wname)
            ]
            for pod in job_pods:
                pod_id = self._add_pod_node(pod, namespace, add_node)
                add_edge(wid, pod_id, "owns")
                related_pods.append(pod)

        elif kind == "CronJob":
            owned_jobs = [
                j for j in ctx["jobs"]
                if _has_owner_kind_name(j, "CronJob", wname)
            ]
            for job in owned_jobs:
                job_name = _meta_name(job)
                job_id = make_node_id("Job", namespace, job_name)
                add_node(DiagramNode(
                    id=job_id,
                    kind="Job",
                    name=job_name,
                    namespace=namespace,
                    group=_group_value(_meta_labels(job)),
                    status=_workload_status_short(job, "Job"),
                    metadata={"labels": _trim_labels(_meta_labels(job))},
                ))
                add_edge(wid, job_id, "owns")
                job_pods = [
                    p for p in ctx["pods"]
                    if _has_owner_kind_name(p, "Job", job_name)
                ]
                for pod in job_pods:
                    pod_id = self._add_pod_node(pod, namespace, add_node)
                    add_edge(job_id, pod_id, "owns")
                    related_pods.append(pod)

        # Add the workload node itself (after pods so we have status info if needed).
        add_node(DiagramNode(
            id=wid,
            kind=kind,
            name=wname,
            namespace=namespace,
            group=_group_value(wlabels),
            status=_workload_status_short(workload, kind),
            metadata={
                "labels": _trim_labels(wlabels),
                "replicas": _replica_count(workload),
                "image": _container_image(workload),
            },
        ))

        # Services that select these pods
        related_services: List[Any] = []
        for svc in ctx["services"]:
            sel = _attr(_attr(svc, "spec"), "selector") or {}
            if not sel:
                continue
            sel_pods = [p for p in related_pods if _selector_matches(sel, _meta_labels(p))]
            if not sel_pods:
                continue
            svc_id = self._add_service_node(svc, namespace, add_node)
            for pod in sel_pods:
                pod_id = make_node_id("Pod", namespace, _meta_name(pod))
                add_edge(svc_id, pod_id, "selects")
            related_services.append(svc)

        # EndpointSlice / Endpoints for those services
        for svc in related_services:
            svc_name = _meta_name(svc)
            svc_id = make_node_id("Service", namespace, svc_name)

            slice_match = [
                es for es in ctx["endpoint_slices"]
                if (_meta_labels(es).get("kubernetes.io/service-name") == svc_name)
            ]
            if slice_match:
                for es in slice_match:
                    es_name = _meta_name(es)
                    es_id = make_node_id("EndpointSlice", namespace, es_name)
                    add_node(DiagramNode(
                        id=es_id,
                        kind="EndpointSlice",
                        name=es_name,
                        namespace=namespace,
                        group=_group_value(_meta_labels(es)),
                        status=None,
                        metadata={"labels": _trim_labels(_meta_labels(es))},
                    ))
                    add_edge(svc_id, es_id, "routes")
            else:
                # Endpoints fallback: match by name (Endpoints share name with Service)
                ep_match = [e for e in ctx["endpoints"] if _meta_name(e) == svc_name]
                for ep in ep_match:
                    ep_id = make_node_id("Endpoints", namespace, svc_name)
                    add_node(DiagramNode(
                        id=ep_id,
                        kind="Endpoints",
                        name=svc_name,
                        namespace=namespace,
                        group=_group_value(_meta_labels(ep)),
                        status=None,
                        metadata={"labels": _trim_labels(_meta_labels(ep))},
                    ))
                    add_edge(svc_id, ep_id, "routes")

        # Ingresses that route to those services
        related_service_names = {_meta_name(s) for s in related_services}
        for ing in ctx["ingresses"]:
            backend_svc_names = _ingress_backend_services(ing)
            hits = backend_svc_names & related_service_names
            if not hits:
                continue
            ing_name = _meta_name(ing)
            ing_id = make_node_id("Ingress", namespace, ing_name)
            add_node(DiagramNode(
                id=ing_id,
                kind="Ingress",
                name=ing_name,
                namespace=namespace,
                group=_group_value(_meta_labels(ing)),
                status=None,
                metadata={"labels": _trim_labels(_meta_labels(ing))},
            ))
            for svc_name in hits:
                svc_id = make_node_id("Service", namespace, svc_name)
                add_edge(ing_id, svc_id, "routes")

        # HPAs targeting this workload
        for hpa in ctx["hpas"]:
            target = _attr(_attr(hpa, "spec"), "scale_target_ref", "scaleTargetRef")
            if target is None:
                continue
            t_kind = _attr(target, "kind")
            t_name = _attr(target, "name")
            if t_kind == kind and t_name == wname:
                hpa_name = _meta_name(hpa)
                hpa_id = make_node_id("HorizontalPodAutoscaler", namespace, hpa_name)
                add_node(DiagramNode(
                    id=hpa_id,
                    kind="HorizontalPodAutoscaler",
                    name=hpa_name,
                    namespace=namespace,
                    group=_group_value(_meta_labels(hpa)),
                    status=None,
                    metadata={"labels": _trim_labels(_meta_labels(hpa))},
                ))
                add_edge(hpa_id, wid, "scales")

        # NetworkPolicies whose podSelector matches the workload pods
        nps_count = 0
        matching_nps: List[Any] = []
        for np in ctx["netpols"]:
            ps = _attr(_attr(np, "spec"), "pod_selector", "podSelector")
            for pod in related_pods:
                if _np_pod_selector_matches(ps, _meta_labels(pod)):
                    matching_nps.append(np)
                    break
        nps_count = len(matching_nps)

        if emit_policy_edges and matching_nps:
            for np in matching_nps:
                np_name = _meta_name(np)
                np_id = make_node_id("NetworkPolicy", namespace, np_name)
                add_node(DiagramNode(
                    id=np_id,
                    kind="NetworkPolicy",
                    name=np_name,
                    namespace=namespace,
                    group=_group_value(_meta_labels(np)),
                    status=None,
                    metadata={"labels": _trim_labels(_meta_labels(np))},
                ))
                ps = _attr(_attr(np, "spec"), "pod_selector", "podSelector")
                for pod in related_pods:
                    if _np_pod_selector_matches(ps, _meta_labels(pod)):
                        pod_id = make_node_id("Pod", namespace, _meta_name(pod))
                        add_edge(np_id, pod_id, "policy")
        elif nps_count:
            # Stamp the count on the workload node metadata for namespace mode.
            # `add_node` will merge metadata into the existing workload node.
            add_node(DiagramNode(
                id=wid,
                kind=kind,
                name=wname,
                namespace=namespace,
                metadata={"nps_count": nps_count},
            ))

        # Mounts — ConfigMap / Secret / PVC nodes derived from the workload pod-spec
        cm_refs, secret_refs, pvc_refs = _collect_volume_refs(workload)

        # ServiceAccount
        sa_name = _attr(_pod_spec_of(workload), "service_account_name", "serviceAccountName")
        if sa_name:
            sa_id = make_node_id("ServiceAccount", namespace, sa_name)
            add_node(DiagramNode(
                id=sa_id,
                kind="ServiceAccount",
                name=sa_name,
                namespace=namespace,
                group=None,
                status=None,
                metadata={"derived": True},
            ))
            add_edge(wid, sa_id, "mounts")

        # ConfigMaps — emit nodes; if it exists in ctx, we have full info, else mark derived
        cm_by_name = {_meta_name(cm): cm for cm in ctx["configmaps"]}
        for cm_name in cm_refs:
            cm_id = make_node_id("ConfigMap", namespace, cm_name)
            cm_obj = cm_by_name.get(cm_name)
            if cm_obj is not None:
                add_node(DiagramNode(
                    id=cm_id,
                    kind="ConfigMap",
                    name=cm_name,
                    namespace=namespace,
                    group=_group_value(_meta_labels(cm_obj)),
                    status=None,
                    metadata={"labels": _trim_labels(_meta_labels(cm_obj))},
                ))
            else:
                add_node(DiagramNode(
                    id=cm_id,
                    kind="ConfigMap",
                    name=cm_name,
                    namespace=namespace,
                    metadata={"derived": True},
                ))
            add_edge(wid, cm_id, "mounts")

        # Secrets — always derived (no RBAC); never call the API.
        for secret_name in secret_refs:
            sec_id = make_node_id("Secret", namespace, secret_name)
            add_node(DiagramNode(
                id=sec_id,
                kind="Secret",
                name=secret_name,
                namespace=namespace,
                metadata={"derived": True},
            ))
            add_edge(wid, sec_id, "mounts")

        # PVCs
        pvc_by_name = {_meta_name(p): p for p in ctx["pvcs"]}
        for pvc_name in pvc_refs:
            pvc_id = make_node_id("PersistentVolumeClaim", namespace, pvc_name)
            pvc_obj = pvc_by_name.get(pvc_name)
            if pvc_obj is not None:
                add_node(DiagramNode(
                    id=pvc_id,
                    kind="PersistentVolumeClaim",
                    name=pvc_name,
                    namespace=namespace,
                    group=_group_value(_meta_labels(pvc_obj)),
                    status=_attr(_attr(pvc_obj, "status"), "phase") or "Unknown",
                    metadata={"labels": _trim_labels(_meta_labels(pvc_obj))},
                ))
            else:
                add_node(DiagramNode(
                    id=pvc_id,
                    kind="PersistentVolumeClaim",
                    name=pvc_name,
                    namespace=namespace,
                    metadata={"derived": True},
                ))
            add_edge(wid, pvc_id, "mounts")

    # -- Helpers ------------------------------------------------------------

    def _add_replica_set_node(self, rs: Any, namespace: str, add_node) -> str:
        rs_name = _meta_name(rs)
        rs_id = make_node_id("ReplicaSet", namespace, rs_name)
        add_node(DiagramNode(
            id=rs_id,
            kind="ReplicaSet",
            name=rs_name,
            namespace=namespace,
            group=_group_value(_meta_labels(rs)),
            status=_workload_status_short(rs, "ReplicaSet"),
            metadata={
                "labels": _trim_labels(_meta_labels(rs)),
                "replicas": _replica_count(rs),
            },
        ))
        return rs_id

    def _add_pod_node(self, pod: Any, namespace: str, add_node) -> str:
        pod_name = _meta_name(pod)
        pod_id = make_node_id("Pod", namespace, pod_name)
        add_node(DiagramNode(
            id=pod_id,
            kind="Pod",
            name=pod_name,
            namespace=namespace,
            group=_group_value(_meta_labels(pod)),
            status=_pod_status_short(pod),
            metadata={
                "labels": _trim_labels(_meta_labels(pod)),
                "image": _container_image(pod),
            },
        ))
        return pod_id

    def _add_service_node(self, svc: Any, namespace: str, add_node) -> str:
        svc_name = _meta_name(svc)
        svc_id = make_node_id("Service", namespace, svc_name)
        spec = _attr(svc, "spec")
        svc_type = _attr(spec, "type") or "ClusterIP"
        add_node(DiagramNode(
            id=svc_id,
            kind="Service",
            name=svc_name,
            namespace=namespace,
            group=_group_value(_meta_labels(svc)),
            status=svc_type,
            metadata={"labels": _trim_labels(_meta_labels(svc))},
        ))
        return svc_id

    def _build_groups(self, nodes: Dict[str, DiagramNode], roots: List[Tuple[str, Any]]) -> List[DiagramGroup]:
        """Assign every node to a group based on the workload it belongs to."""
        groups: Dict[str, List[str]] = {}

        for node in nodes.values():
            label = node.group or "ungrouped"
            groups.setdefault(label, []).append(node.id)

        out: List[DiagramGroup] = []
        for label, node_ids in sorted(groups.items()):
            out.append(DiagramGroup(
                id=f"group:{label}",
                label=label,
                node_ids=sorted(node_ids),
            ))
        return out

    async def _read_workload(self, kind: str, namespace: str, name: str) -> Any:
        if kind == "Deployment":
            return await self._run(self._apps.read_namespaced_deployment, name, namespace)
        if kind == "StatefulSet":
            return await self._run(self._apps.read_namespaced_stateful_set, name, namespace)
        if kind == "DaemonSet":
            return await self._run(self._apps.read_namespaced_daemon_set, name, namespace)
        if kind == "Job":
            return await self._run(self._batch.read_namespaced_job, name, namespace)
        if kind == "CronJob":
            return await self._run(self._batch.read_namespaced_cron_job, name, namespace)
        raise ValueError(f"Unsupported workload kind: {kind}")

    async def _read_resource(self, kind: str, namespace: str, name: str) -> Any:
        """Read any DiagramNode.kind for the manifest endpoint."""
        if kind == "Deployment":
            return await self._run(self._apps.read_namespaced_deployment, name, namespace)
        if kind == "StatefulSet":
            return await self._run(self._apps.read_namespaced_stateful_set, name, namespace)
        if kind == "DaemonSet":
            return await self._run(self._apps.read_namespaced_daemon_set, name, namespace)
        if kind == "ReplicaSet":
            return await self._run(self._apps.read_namespaced_replica_set, name, namespace)
        if kind == "Pod":
            return await self._run(self._core.read_namespaced_pod, name, namespace)
        if kind == "Service":
            return await self._run(self._core.read_namespaced_service, name, namespace)
        if kind == "Endpoints":
            return await self._run(self._core.read_namespaced_endpoints, name, namespace)
        if kind == "EndpointSlice":
            return await self._run(self._discovery.read_namespaced_endpoint_slice, name, namespace)
        if kind == "Ingress":
            return await self._run(self._networking.read_namespaced_ingress, name, namespace)
        if kind == "ConfigMap":
            return await self._run(self._core.read_namespaced_config_map, name, namespace)
        if kind == "PersistentVolumeClaim":
            return await self._run(self._core.read_namespaced_persistent_volume_claim, name, namespace)
        if kind == "ServiceAccount":
            return await self._run(self._core.read_namespaced_service_account, name, namespace)
        if kind == "HorizontalPodAutoscaler":
            return await self._run(self._autoscaling.read_namespaced_horizontal_pod_autoscaler, name, namespace)
        if kind == "NetworkPolicy":
            return await self._run(self._networking.read_namespaced_network_policy, name, namespace)
        if kind == "Job":
            return await self._run(self._batch.read_namespaced_job, name, namespace)
        if kind == "CronJob":
            return await self._run(self._batch.read_namespaced_cron_job, name, namespace)
        raise ValueError(f"Cannot fetch manifest for kind '{kind}'")


# --- Module-level helpers ----------------------------------------------------

def _has_owner_kind(obj: Any, owner_kind: str) -> bool:
    return any(_attr(o, "kind") == owner_kind for o in _owner_refs(obj))


def _has_owner_kind_name(obj: Any, owner_kind: str, owner_name: str) -> bool:
    return any(
        _attr(o, "kind") == owner_kind and _attr(o, "name") == owner_name
        for o in _owner_refs(obj)
    )


def _current_replica_set(rses: List[Any]) -> Optional[Any]:
    """Pick the ReplicaSet considered current.

    Strategy: prefer the one with spec.replicas > 0; tie-break by largest
    revision annotation (``deployment.kubernetes.io/revision``); final
    tie-break by metadata.creation_timestamp (latest wins).
    """
    if not rses:
        return None

    def revision(rs: Any) -> int:
        anns = _attr(_meta(rs), "annotations") or {}
        try:
            return int(anns.get("deployment.kubernetes.io/revision", "0"))
        except (TypeError, ValueError):
            return 0

    def ts(rs: Any) -> str:
        v = _attr(_meta(rs), "creation_timestamp", "creationTimestamp")
        return str(v) if v else ""

    active = [r for r in rses if (_replica_count(r) or 0) > 0]
    pool = active or rses
    pool_sorted = sorted(pool, key=lambda r: (revision(r), ts(r)), reverse=True)
    return pool_sorted[0]


def _ingress_backend_services(ing: Any) -> set:
    """Return the set of Service names referenced by an Ingress."""
    out: set = set()
    spec = _attr(ing, "spec")
    if spec is None:
        return out
    # default backend
    default_backend = _attr(spec, "default_backend", "defaultBackend")
    if default_backend is not None:
        svc = _attr(default_backend, "service")
        sname = _attr(svc, "name")
        if sname:
            out.add(sname)
    rules = _attr(spec, "rules") or []
    for rule in rules:
        http = _attr(rule, "http")
        paths = _attr(http, "paths") if http else None
        for p in paths or []:
            backend = _attr(p, "backend")
            svc = _attr(backend, "service")
            sname = _attr(svc, "name")
            if sname:
                out.add(sname)
    return out


def _pod_spec_of(workload: Any) -> Any:
    """Return the pod spec for a workload (from ``spec.template.spec``).

    For a CronJob we descend through ``spec.jobTemplate.spec.template.spec``.
    """
    spec = _attr(workload, "spec")
    if spec is None:
        return None
    job_template = _attr(spec, "job_template", "jobTemplate")
    if job_template is not None:
        job_spec = _attr(job_template, "spec")
        template = _attr(job_spec, "template") if job_spec is not None else None
    else:
        template = _attr(spec, "template")
    if template is None:
        return None
    return _attr(template, "spec")


def _collect_volume_refs(workload: Any) -> Tuple[List[str], List[str], List[str]]:
    """Extract ConfigMap / Secret / PVC references from a workload pod-spec.

    Looks at:
      - spec.template.spec.volumes[] (configMap, secret, persistentVolumeClaim)
      - containers[].envFrom[] (configMapRef, secretRef)
      - containers[].env[].valueFrom (configMapKeyRef, secretKeyRef)
    Init containers are included.
    """
    pod_spec = _pod_spec_of(workload)
    if pod_spec is None:
        return [], [], []

    cm_names: List[str] = []
    secret_names: List[str] = []
    pvc_names: List[str] = []

    seen_cm: set = set()
    seen_sec: set = set()
    seen_pvc: set = set()

    def _add(lst: List[str], seen: set, name: Optional[str]) -> None:
        if name and name not in seen:
            seen.add(name)
            lst.append(name)

    for vol in (_attr(pod_spec, "volumes") or []):
        cm = _attr(vol, "config_map", "configMap")
        if cm is not None:
            _add(cm_names, seen_cm, _attr(cm, "name"))
        sec = _attr(vol, "secret")
        if sec is not None:
            _add(secret_names, seen_sec, _attr(sec, "secret_name", "secretName"))
        pvc = _attr(vol, "persistent_volume_claim", "persistentVolumeClaim")
        if pvc is not None:
            _add(pvc_names, seen_pvc, _attr(pvc, "claim_name", "claimName"))
        projected = _attr(vol, "projected")
        if projected is not None:
            for src in (_attr(projected, "sources") or []):
                cm2 = _attr(src, "config_map", "configMap")
                if cm2 is not None:
                    _add(cm_names, seen_cm, _attr(cm2, "name"))
                sec2 = _attr(src, "secret")
                if sec2 is not None:
                    _add(secret_names, seen_sec, _attr(sec2, "name"))

    containers = list(_attr(pod_spec, "containers") or [])
    init_containers = list(_attr(pod_spec, "init_containers", "initContainers") or [])
    for c in containers + init_containers:
        for envFrom in (_attr(c, "env_from", "envFrom") or []):
            cmref = _attr(envFrom, "config_map_ref", "configMapRef")
            if cmref is not None:
                _add(cm_names, seen_cm, _attr(cmref, "name"))
            secref = _attr(envFrom, "secret_ref", "secretRef")
            if secref is not None:
                _add(secret_names, seen_sec, _attr(secref, "name"))
        for env in (_attr(c, "env") or []):
            value_from = _attr(env, "value_from", "valueFrom")
            if value_from is None:
                continue
            cmref = _attr(value_from, "config_map_key_ref", "configMapKeyRef")
            if cmref is not None:
                _add(cm_names, seen_cm, _attr(cmref, "name"))
            secref = _attr(value_from, "secret_key_ref", "secretKeyRef")
            if secref is not None:
                _add(secret_names, seen_sec, _attr(secref, "name"))

    return cm_names, secret_names, pvc_names
