"""Tests for services.topology_service.

These tests exercise ``TopologyService`` with mocked kubernetes API clients —
no live cluster required. They cover the traversal rules listed in the spec:

- Deployment with two ReplicaSets (current + old): both RSes appear, only
  current RS's Pods are linked.
- Service spec.selector → Pod label match.
- EndpointSlice path; fallback to Endpoints when EndpointSlice list errors.
- HPA ``scales`` edge to a Deployment.
- ConfigMap and PVC ``mounts`` edges from ``volumes[]``.
- Secret derived from ``envFrom[].secretRef``; ``metadata.derived == True``;
  no API call to Secrets.
- Namespace mode groups workloads correctly by ``app.kubernetes.io/name``;
  missing label falls into ``group:ungrouped``.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.topology_service import (
    TopologyService,
    make_node_id,
    normalise_kind,
)


# ---------------------------------------------------------------------------
# Fake K8s objects (use SimpleNamespace so attribute access works).
# ---------------------------------------------------------------------------

def _meta(name, namespace, labels=None, annotations=None, owner_kind=None, owner_name=None,
          creation_timestamp=None):
    owners = []
    if owner_kind and owner_name:
        owners.append(SimpleNamespace(kind=owner_kind, name=owner_name))
    return SimpleNamespace(
        name=name,
        namespace=namespace,
        labels=labels or {},
        annotations=annotations or {},
        owner_references=owners,
        creation_timestamp=creation_timestamp,
    )


def _make_deployment(name, namespace, labels=None, replicas=2, image="nginx:1",
                     volumes=None, env_from=None, env=None, service_account=None):
    template_spec = SimpleNamespace(
        containers=[SimpleNamespace(
            name="app", image=image,
            env_from=env_from or [],
            env=env or [],
        )],
        init_containers=[],
        volumes=volumes or [],
        service_account_name=service_account,
    )
    return SimpleNamespace(
        metadata=_meta(name, namespace, labels=labels),
        spec=SimpleNamespace(
            replicas=replicas,
            template=SimpleNamespace(spec=template_spec),
        ),
        status=SimpleNamespace(replicas=replicas, ready_replicas=replicas),
    )


def _make_replica_set(name, namespace, deployment_name, replicas=2, revision="1",
                       creation_timestamp="2025-01-01T00:00:00Z", labels=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            namespace=namespace,
            labels=labels or {},
            annotations={"deployment.kubernetes.io/revision": revision},
            owner_references=[SimpleNamespace(kind="Deployment", name=deployment_name)],
            creation_timestamp=creation_timestamp,
        ),
        spec=SimpleNamespace(replicas=replicas),
        status=SimpleNamespace(replicas=replicas, ready_replicas=replicas),
    )


def _make_pod(name, namespace, labels=None, owner_kind="ReplicaSet", owner_name="rs",
              phase="Running", image="nginx:1"):
    return SimpleNamespace(
        metadata=_meta(name, namespace, labels=labels, owner_kind=owner_kind,
                       owner_name=owner_name),
        spec=SimpleNamespace(
            containers=[SimpleNamespace(name="app", image=image)],
        ),
        status=SimpleNamespace(
            phase=phase,
            container_statuses=[SimpleNamespace(name="app", ready=True)],
        ),
    )


def _make_service(name, namespace, selector, svc_type="ClusterIP", labels=None):
    return SimpleNamespace(
        metadata=_meta(name, namespace, labels=labels),
        spec=SimpleNamespace(selector=selector, type=svc_type),
    )


def _make_endpoint_slice(name, namespace, service_name):
    return SimpleNamespace(
        metadata=_meta(name, namespace, labels={"kubernetes.io/service-name": service_name}),
    )


def _make_endpoints(name, namespace):
    return SimpleNamespace(
        metadata=_meta(name, namespace),
    )


def _make_hpa(name, namespace, target_kind, target_name):
    return SimpleNamespace(
        metadata=_meta(name, namespace),
        spec=SimpleNamespace(
            scale_target_ref=SimpleNamespace(kind=target_kind, name=target_name),
        ),
    )


def _make_ingress(name, namespace, service_name):
    backend = SimpleNamespace(service=SimpleNamespace(name=service_name))
    path = SimpleNamespace(backend=backend)
    rule = SimpleNamespace(http=SimpleNamespace(paths=[path]))
    return SimpleNamespace(
        metadata=_meta(name, namespace),
        spec=SimpleNamespace(default_backend=None, rules=[rule]),
    )


def _make_netpol(name, namespace, match_labels):
    return SimpleNamespace(
        metadata=_meta(name, namespace),
        spec=SimpleNamespace(
            pod_selector=SimpleNamespace(
                match_labels=match_labels,
                match_expressions=None,
            ),
        ),
    )


def _make_configmap(name, namespace):
    return SimpleNamespace(metadata=_meta(name, namespace))


def _make_pvc(name, namespace, phase="Bound"):
    return SimpleNamespace(
        metadata=_meta(name, namespace),
        status=SimpleNamespace(phase=phase),
    )


def _list_wrapper(items):
    return SimpleNamespace(items=items)


# ---------------------------------------------------------------------------
# Fixture: build a TopologyService with all kube clients pre-populated as
# MagicMocks. Each test customises the mocks before calling.
# ---------------------------------------------------------------------------

@pytest.fixture
def topo():
    svc = TopologyService()
    svc._initialised = True  # bypass _init_k8s
    svc._core = MagicMock()
    svc._apps = MagicMock()
    svc._batch = MagicMock()
    svc._networking = MagicMock()
    svc._discovery = MagicMock()
    svc._autoscaling = MagicMock()

    # Default empty list responses
    svc._core.list_namespaced_pod.return_value = _list_wrapper([])
    svc._core.list_namespaced_service.return_value = _list_wrapper([])
    svc._core.list_namespaced_endpoints.return_value = _list_wrapper([])
    svc._core.list_namespaced_persistent_volume_claim.return_value = _list_wrapper([])
    svc._core.list_namespaced_config_map.return_value = _list_wrapper([])
    svc._apps.list_namespaced_deployment.return_value = _list_wrapper([])
    svc._apps.list_namespaced_stateful_set.return_value = _list_wrapper([])
    svc._apps.list_namespaced_daemon_set.return_value = _list_wrapper([])
    svc._apps.list_namespaced_replica_set.return_value = _list_wrapper([])
    svc._batch.list_namespaced_job.return_value = _list_wrapper([])
    svc._batch.list_namespaced_cron_job.return_value = _list_wrapper([])
    svc._networking.list_namespaced_ingress.return_value = _list_wrapper([])
    svc._networking.list_namespaced_network_policy.return_value = _list_wrapper([])
    svc._autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = _list_wrapper([])
    svc._discovery.list_namespaced_endpoint_slice.return_value = _list_wrapper([])
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNormaliseKind:
    def test_lowercase_input(self):
        assert normalise_kind("deployment") == "Deployment"

    def test_canonical_input(self):
        assert normalise_kind("Deployment") == "Deployment"

    def test_unknown(self):
        assert normalise_kind("NotAKind") is None

    def test_empty(self):
        assert normalise_kind("") is None


class TestNamespaceDiagramGroups:
    @pytest.mark.asyncio
    async def test_groups_by_app_label(self, topo):
        ns = "default"
        dep_a = _make_deployment("api", ns, labels={"app.kubernetes.io/name": "api"})
        dep_b = _make_deployment("worker", ns, labels={"app": "worker"})
        dep_c = _make_deployment("orphan", ns, labels={})

        topo._apps.list_namespaced_deployment.return_value = _list_wrapper(
            [dep_a, dep_b, dep_c]
        )

        result = await topo.get_namespace_diagram(ns)
        group_labels = {g.label for g in result.groups}
        assert "api" in group_labels
        assert "worker" in group_labels
        assert "ungrouped" in group_labels

    @pytest.mark.asyncio
    async def test_scope_is_namespace(self, topo):
        result = await topo.get_namespace_diagram("default")
        assert result.scope == "namespace"
        assert result.root_id is None


class TestWorkloadTraversal:
    """Workload-mode traversal — covers most of the edge semantics."""

    @pytest.mark.asyncio
    async def test_deployment_two_replica_sets_only_current_pods_linked(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app": "api"})
        rs_old = _make_replica_set("api-old", ns, "api", replicas=0, revision="1",
                                    creation_timestamp="2025-01-01T00:00:00Z")
        rs_new = _make_replica_set("api-new", ns, "api", replicas=2, revision="2",
                                    creation_timestamp="2025-02-01T00:00:00Z")
        # Two pods owned by the new RS, none by the old RS
        pod1 = _make_pod("api-new-aaa", ns, labels={"app": "api"},
                         owner_kind="ReplicaSet", owner_name="api-new")
        pod2 = _make_pod("api-new-bbb", ns, labels={"app": "api"},
                         owner_kind="ReplicaSet", owner_name="api-new")

        topo._apps.read_namespaced_deployment.return_value = dep
        topo._apps.list_namespaced_replica_set.return_value = _list_wrapper([rs_old, rs_new])
        topo._core.list_namespaced_pod.return_value = _list_wrapper([pod1, pod2])

        result = await topo.get_workload_diagram(ns, "Deployment", "api")
        node_ids = {n.id for n in result.nodes}

        assert make_node_id("Deployment", ns, "api") in node_ids
        assert make_node_id("ReplicaSet", ns, "api-old") in node_ids
        assert make_node_id("ReplicaSet", ns, "api-new") in node_ids
        assert make_node_id("Pod", ns, "api-new-aaa") in node_ids
        assert make_node_id("Pod", ns, "api-new-bbb") in node_ids

        # owns edges
        owns = {(e.source, e.target) for e in result.edges if e.type == "owns"}
        dep_id = make_node_id("Deployment", ns, "api")
        rs_old_id = make_node_id("ReplicaSet", ns, "api-old")
        rs_new_id = make_node_id("ReplicaSet", ns, "api-new")
        pod1_id = make_node_id("Pod", ns, "api-new-aaa")
        pod2_id = make_node_id("Pod", ns, "api-new-bbb")

        assert (dep_id, rs_old_id) in owns
        assert (dep_id, rs_new_id) in owns
        assert (rs_new_id, pod1_id) in owns
        assert (rs_new_id, pod2_id) in owns
        # Old RS must NOT have any owns edges to a Pod
        assert (rs_old_id, pod1_id) not in owns
        assert (rs_old_id, pod2_id) not in owns
        for e in result.edges:
            if e.type == "owns" and e.source == rs_old_id:
                pytest.fail(f"Old RS should have no pod owns edge, got {e.target}")

    @pytest.mark.asyncio
    async def test_service_selects_pod_by_label_match(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app": "api"})
        rs = _make_replica_set("api-rs", ns, "api", replicas=1, revision="1")
        pod = _make_pod("api-rs-x", ns, labels={"app": "api"},
                        owner_kind="ReplicaSet", owner_name="api-rs")
        svc_match = _make_service("api-svc", ns, selector={"app": "api"})
        svc_nomatch = _make_service("other-svc", ns, selector={"app": "other"})

        topo._apps.read_namespaced_deployment.return_value = dep
        topo._apps.list_namespaced_replica_set.return_value = _list_wrapper([rs])
        topo._core.list_namespaced_pod.return_value = _list_wrapper([pod])
        topo._core.list_namespaced_service.return_value = _list_wrapper(
            [svc_match, svc_nomatch]
        )

        result = await topo.get_workload_diagram(ns, "Deployment", "api")
        node_ids = {n.id for n in result.nodes}
        assert make_node_id("Service", ns, "api-svc") in node_ids
        assert make_node_id("Service", ns, "other-svc") not in node_ids

        selects = {(e.source, e.target) for e in result.edges if e.type == "selects"}
        svc_id = make_node_id("Service", ns, "api-svc")
        pod_id = make_node_id("Pod", ns, "api-rs-x")
        assert (svc_id, pod_id) in selects

    @pytest.mark.asyncio
    async def test_endpoint_slice_path(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app": "api"})
        rs = _make_replica_set("api-rs", ns, "api", replicas=1)
        pod = _make_pod("api-rs-x", ns, labels={"app": "api"},
                        owner_kind="ReplicaSet", owner_name="api-rs")
        svc = _make_service("api-svc", ns, selector={"app": "api"})
        es = _make_endpoint_slice("api-svc-abc", ns, service_name="api-svc")

        topo._apps.read_namespaced_deployment.return_value = dep
        topo._apps.list_namespaced_replica_set.return_value = _list_wrapper([rs])
        topo._core.list_namespaced_pod.return_value = _list_wrapper([pod])
        topo._core.list_namespaced_service.return_value = _list_wrapper([svc])
        topo._discovery.list_namespaced_endpoint_slice.return_value = _list_wrapper([es])

        result = await topo.get_workload_diagram(ns, "Deployment", "api")
        node_ids = {n.id for n in result.nodes}
        assert make_node_id("EndpointSlice", ns, "api-svc-abc") in node_ids

        routes = {(e.source, e.target) for e in result.edges if e.type == "routes"}
        assert (
            make_node_id("Service", ns, "api-svc"),
            make_node_id("EndpointSlice", ns, "api-svc-abc"),
        ) in routes
        # No Endpoints fallback when EndpointSlices succeed
        assert make_node_id("Endpoints", ns, "api-svc") not in node_ids

    @pytest.mark.asyncio
    async def test_endpoints_fallback_when_endpoint_slice_errors(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app": "api"})
        rs = _make_replica_set("api-rs", ns, "api", replicas=1)
        pod = _make_pod("api-rs-x", ns, labels={"app": "api"},
                        owner_kind="ReplicaSet", owner_name="api-rs")
        svc = _make_service("api-svc", ns, selector={"app": "api"})
        ep = _make_endpoints("api-svc", ns)

        topo._apps.read_namespaced_deployment.return_value = dep
        topo._apps.list_namespaced_replica_set.return_value = _list_wrapper([rs])
        topo._core.list_namespaced_pod.return_value = _list_wrapper([pod])
        topo._core.list_namespaced_service.return_value = _list_wrapper([svc])
        topo._discovery.list_namespaced_endpoint_slice.side_effect = RuntimeError(
            "discovery API not available"
        )
        topo._core.list_namespaced_endpoints.return_value = _list_wrapper([ep])

        result = await topo.get_workload_diagram(ns, "Deployment", "api")
        node_ids = {n.id for n in result.nodes}
        assert make_node_id("Endpoints", ns, "api-svc") in node_ids

        routes = {(e.source, e.target) for e in result.edges if e.type == "routes"}
        assert (
            make_node_id("Service", ns, "api-svc"),
            make_node_id("Endpoints", ns, "api-svc"),
        ) in routes

    @pytest.mark.asyncio
    async def test_hpa_scales_deployment(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app": "api"})
        hpa = _make_hpa("api-hpa", ns, "Deployment", "api")

        topo._apps.read_namespaced_deployment.return_value = dep
        topo._autoscaling.list_namespaced_horizontal_pod_autoscaler.return_value = (
            _list_wrapper([hpa])
        )

        result = await topo.get_workload_diagram(ns, "Deployment", "api")
        node_ids = {n.id for n in result.nodes}
        assert make_node_id("HorizontalPodAutoscaler", ns, "api-hpa") in node_ids

        scales = {(e.source, e.target) for e in result.edges if e.type == "scales"}
        assert (
            make_node_id("HorizontalPodAutoscaler", ns, "api-hpa"),
            make_node_id("Deployment", ns, "api"),
        ) in scales

    @pytest.mark.asyncio
    async def test_configmap_and_pvc_mounts_from_volumes(self, topo):
        ns = "default"
        cm_volume = SimpleNamespace(
            name="cfg",
            config_map=SimpleNamespace(name="my-config"),
            secret=None,
            persistent_volume_claim=None,
            projected=None,
        )
        pvc_volume = SimpleNamespace(
            name="data",
            config_map=None,
            secret=None,
            persistent_volume_claim=SimpleNamespace(claim_name="my-pvc"),
            projected=None,
        )
        dep = _make_deployment(
            "api", ns, labels={"app": "api"},
            volumes=[cm_volume, pvc_volume],
        )
        cm = _make_configmap("my-config", ns)
        pvc = _make_pvc("my-pvc", ns)

        topo._apps.read_namespaced_deployment.return_value = dep
        topo._core.list_namespaced_config_map.return_value = _list_wrapper([cm])
        topo._core.list_namespaced_persistent_volume_claim.return_value = _list_wrapper([pvc])

        result = await topo.get_workload_diagram(ns, "Deployment", "api")
        node_ids = {n.id for n in result.nodes}
        assert make_node_id("ConfigMap", ns, "my-config") in node_ids
        assert make_node_id("PersistentVolumeClaim", ns, "my-pvc") in node_ids

        mounts = {(e.source, e.target) for e in result.edges if e.type == "mounts"}
        dep_id = make_node_id("Deployment", ns, "api")
        assert (dep_id, make_node_id("ConfigMap", ns, "my-config")) in mounts
        assert (dep_id, make_node_id("PersistentVolumeClaim", ns, "my-pvc")) in mounts

    @pytest.mark.asyncio
    async def test_secret_derived_from_envfrom_no_secrets_api_call(self, topo):
        ns = "default"
        env_from = [SimpleNamespace(
            config_map_ref=None,
            secret_ref=SimpleNamespace(name="my-secret"),
        )]
        dep = _make_deployment(
            "api", ns, labels={"app": "api"},
            env_from=env_from,
        )

        topo._apps.read_namespaced_deployment.return_value = dep

        # A secrets API method would not be called in any case — but assert
        # there's no list_namespaced_secret invocation just to be explicit.
        # MagicMock allows arbitrary attribute access; we record calls.
        result = await topo.get_workload_diagram(ns, "Deployment", "api")

        secret_id = make_node_id("Secret", ns, "my-secret")
        secret_node = next((n for n in result.nodes if n.id == secret_id), None)
        assert secret_node is not None
        assert secret_node.metadata is not None
        assert secret_node.metadata.get("derived") is True

        mounts = {(e.source, e.target) for e in result.edges if e.type == "mounts"}
        assert (make_node_id("Deployment", ns, "api"), secret_id) in mounts

        # Ensure no attempt was made to call any *secret* API method on _core
        for attr in dir(topo._core):
            if "secret" in attr.lower() and callable(getattr(topo._core, attr, None)):
                # MagicMock auto-creates attributes; check for actual calls
                m = getattr(topo._core, attr)
                if hasattr(m, "called"):
                    assert not m.called, f"Secrets API call detected: {attr}"

    @pytest.mark.asyncio
    async def test_ingress_routes_to_service(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app": "api"})
        rs = _make_replica_set("api-rs", ns, "api", replicas=1)
        pod = _make_pod("api-rs-x", ns, labels={"app": "api"},
                        owner_kind="ReplicaSet", owner_name="api-rs")
        svc = _make_service("api-svc", ns, selector={"app": "api"})
        ing = _make_ingress("api-ing", ns, service_name="api-svc")

        topo._apps.read_namespaced_deployment.return_value = dep
        topo._apps.list_namespaced_replica_set.return_value = _list_wrapper([rs])
        topo._core.list_namespaced_pod.return_value = _list_wrapper([pod])
        topo._core.list_namespaced_service.return_value = _list_wrapper([svc])
        topo._networking.list_namespaced_ingress.return_value = _list_wrapper([ing])

        result = await topo.get_workload_diagram(ns, "Deployment", "api")
        node_ids = {n.id for n in result.nodes}
        assert make_node_id("Ingress", ns, "api-ing") in node_ids

        routes = {(e.source, e.target) for e in result.edges if e.type == "routes"}
        assert (
            make_node_id("Ingress", ns, "api-ing"),
            make_node_id("Service", ns, "api-svc"),
        ) in routes

    @pytest.mark.asyncio
    async def test_networkpolicy_emits_policy_edges_in_workload_mode(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app": "api"})
        rs = _make_replica_set("api-rs", ns, "api", replicas=1)
        pod = _make_pod("api-rs-x", ns, labels={"app": "api"},
                        owner_kind="ReplicaSet", owner_name="api-rs")
        np = _make_netpol("api-np", ns, match_labels={"app": "api"})

        topo._apps.read_namespaced_deployment.return_value = dep
        topo._apps.list_namespaced_replica_set.return_value = _list_wrapper([rs])
        topo._core.list_namespaced_pod.return_value = _list_wrapper([pod])
        topo._networking.list_namespaced_network_policy.return_value = _list_wrapper([np])

        result = await topo.get_workload_diagram(ns, "Deployment", "api")
        policies = {(e.source, e.target) for e in result.edges if e.type == "policy"}
        assert (
            make_node_id("NetworkPolicy", ns, "api-np"),
            make_node_id("Pod", ns, "api-rs-x"),
        ) in policies


class TestNamespaceModeNetworkPolicy:
    @pytest.mark.asyncio
    async def test_netpol_count_on_workload_in_namespace_mode(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app.kubernetes.io/name": "api"})
        rs = _make_replica_set("api-rs", ns, "api", replicas=1, labels={"app.kubernetes.io/name": "api"})
        pod = _make_pod("api-rs-x", ns, labels={"app.kubernetes.io/name": "api"},
                        owner_kind="ReplicaSet", owner_name="api-rs")
        np1 = _make_netpol("np-1", ns, match_labels={"app.kubernetes.io/name": "api"})
        np2 = _make_netpol("np-2", ns, match_labels={"app.kubernetes.io/name": "api"})

        topo._apps.list_namespaced_deployment.return_value = _list_wrapper([dep])
        topo._apps.list_namespaced_replica_set.return_value = _list_wrapper([rs])
        topo._core.list_namespaced_pod.return_value = _list_wrapper([pod])
        topo._networking.list_namespaced_network_policy.return_value = _list_wrapper([np1, np2])

        result = await topo.get_namespace_diagram(ns)
        # No 'policy' edges in namespace mode
        policy_edges = [e for e in result.edges if e.type == "policy"]
        assert policy_edges == []

        # Workload node has nps_count=2
        dep_node = next(n for n in result.nodes if n.kind == "Deployment" and n.name == "api")
        assert dep_node.metadata is not None
        assert dep_node.metadata.get("nps_count") == 2


class TestCache:
    @pytest.mark.asyncio
    async def test_namespace_diagram_caches_result(self, topo):
        ns = "default"
        dep = _make_deployment("api", ns, labels={"app": "api"})
        topo._apps.list_namespaced_deployment.return_value = _list_wrapper([dep])

        first = await topo.get_namespace_diagram(ns)
        # Second call should hit cache; mutate the mock to verify it isn't reused.
        topo._apps.list_namespaced_deployment.return_value = _list_wrapper([])
        second = await topo.get_namespace_diagram(ns)

        assert {n.id for n in first.nodes} == {n.id for n in second.nodes}
        assert any(n.kind == "Deployment" for n in second.nodes)


# ---------------------------------------------------------------------------
# Manifest endpoint behaviour: tested via the route layer with a minimal app
# (no database needed — these endpoints validate kind before any I/O).
# ---------------------------------------------------------------------------

@pytest.fixture
def diagram_client():
    """Minimal FastAPI app exposing only the diagram router.

    Avoids the database fixture chain so these route-level tests run in any
    environment.
    """
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from api.routes_diagram import create_diagram_router
    from api.deps import RouterDeps

    deps = RouterDeps(db=None, solution_engine=None, websocket_manager=None)
    app = FastAPI()
    app.include_router(create_diagram_router(deps), prefix="/api")

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestDiagramRoutes:
    """Route-level validation tests (no DB, no kube cluster)."""

    @pytest.mark.asyncio
    async def test_manifest_secret_returns_403(self, diagram_client):
        async with diagram_client as client:
            resp = await client.get("/api/diagram/manifest/default/Secret/anything")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manifest_secret_lowercase_returns_403(self, diagram_client):
        async with diagram_client as client:
            resp = await client.get("/api/diagram/manifest/default/secret/anything")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manifest_invalid_kind_returns_400(self, diagram_client):
        async with diagram_client as client:
            resp = await client.get("/api/diagram/manifest/default/NotARealKind/anything")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_workload_invalid_kind_returns_400(self, diagram_client):
        async with diagram_client as client:
            resp = await client.get("/api/diagram/workload/default/Pod/some-pod")
        assert resp.status_code == 400
