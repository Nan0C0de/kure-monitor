import pytest
import asyncio
import yaml
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime, timezone

from services.mirror_service import MirrorService, DEFAULT_MIRROR_TTL_SECONDS, clean_manifest
from models.models import PodFailureResponse


class TestMirrorService:
    """Tests for the MirrorService."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.get_app_setting = AsyncMock(return_value=None)
        db.set_app_setting = AsyncMock()
        return db

    @pytest.fixture
    def mock_solution_engine(self):
        engine = AsyncMock()
        engine.generate_pod_fix = AsyncMock(return_value={
            "fixed_manifest": "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod\nspec:\n  containers:\n  - name: app\n    image: nginx:1.25",
            "explanation": "Updated image tag to a valid version",
            "is_fallback": False,
        })
        return engine

    @pytest.fixture
    def mock_websocket_manager(self):
        ws = AsyncMock()
        ws.broadcast_mirror_event = AsyncMock()
        return ws

    @pytest.fixture
    def mirror_service(self, mock_db, mock_solution_engine, mock_websocket_manager):
        service = MirrorService(
            db=mock_db,
            solution_engine=mock_solution_engine,
            websocket_manager=mock_websocket_manager
        )
        # Pre-set K8s client as a mock so _init_k8s_client is effectively a no-op
        service._k8s_core_v1 = MagicMock()
        return service

    @pytest.fixture
    def sample_pod_failure(self):
        return PodFailureResponse(
            id=42,
            pod_name="test-pod",
            namespace="default",
            node_name="node-1",
            phase="Pending",
            creation_timestamp="2025-01-01T00:00:00Z",
            failure_reason="ImagePullBackOff",
            failure_message="Failed to pull image 'nonexistent:latest'",
            container_statuses=[],
            events=[
                {"type": "Warning", "reason": "Failed", "message": "Failed to pull image"}
            ],
            logs="",
            manifest="apiVersion: v1\nkind: Pod",
            solution="Check if the image exists",
            timestamp="2025-01-01T00:00:00Z",
        )

    # --- get_default_ttl ---

    @pytest.mark.asyncio
    async def test_get_default_ttl_no_setting(self, mirror_service, mock_db):
        """Returns default TTL when no setting is stored."""
        mock_db.get_app_setting.return_value = None
        ttl = await mirror_service.get_default_ttl()
        assert ttl == DEFAULT_MIRROR_TTL_SECONDS
        mock_db.get_app_setting.assert_called_once_with("mirror_ttl_seconds")

    @pytest.mark.asyncio
    async def test_get_default_ttl_with_setting(self, mirror_service, mock_db):
        """Returns stored TTL when a setting exists."""
        mock_db.get_app_setting.return_value = "300"
        ttl = await mirror_service.get_default_ttl()
        assert ttl == 300

    @pytest.mark.asyncio
    async def test_set_default_ttl(self, mirror_service, mock_db):
        """Sets TTL in app_settings."""
        await mirror_service.set_default_ttl(600)
        mock_db.set_app_setting.assert_called_once_with("mirror_ttl_seconds", "600")

    # --- _prepare_mirror_spec ---

    def test_prepare_mirror_spec_strips_owner_references(self, mirror_service):
        """ownerReferences should be stripped."""
        spec = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "original",
                "namespace": "default",
                "ownerReferences": [{"kind": "ReplicaSet"}],
                "resourceVersion": "123",
                "uid": "abc-123",
                "creationTimestamp": "2025-01-01T00:00:00Z",
            },
            "spec": {
                "containers": [{"name": "app", "image": "nginx"}]
            },
            "status": {"phase": "Running"}
        }

        mirror_service._prepare_mirror_spec(
            spec,
            mirror_pod_name="original-kure-mirror",
            original_pod_name="original",
            namespace="default",
            pod_failure_id=42,
            mirror_id="test-uuid",
            ttl_seconds=180,
            created_at="2025-01-01T00:00:00Z"
        )

        assert "ownerReferences" not in spec["metadata"]
        assert "resourceVersion" not in spec["metadata"]
        assert "uid" not in spec["metadata"]
        assert "creationTimestamp" not in spec["metadata"]
        assert "status" not in spec

    def test_prepare_mirror_spec_sets_name_and_labels(self, mirror_service):
        """Mirror pod gets correct name, labels, and annotations."""
        spec = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "original",
                "namespace": "default",
            },
            "spec": {
                "containers": [{"name": "app", "image": "nginx"}]
            }
        }

        mirror_service._prepare_mirror_spec(
            spec,
            mirror_pod_name="original-kure-mirror",
            original_pod_name="original",
            namespace="default",
            pod_failure_id=42,
            mirror_id="test-uuid",
            ttl_seconds=300,
            created_at="2025-06-01T12:00:00Z"
        )

        assert spec["metadata"]["name"] == "original-kure-mirror"
        assert spec["metadata"]["labels"]["kure.io/mirror"] == "true"
        assert spec["metadata"]["labels"]["kure.io/mirror-of"] == "original"
        assert spec["metadata"]["labels"]["kure.io/mirror-source-id"] == "42"
        assert spec["metadata"]["annotations"]["kure.io/mirror-ttl"] == "300"
        assert spec["metadata"]["annotations"]["kure.io/mirror-created"] == "2025-06-01T12:00:00Z"
        assert spec["metadata"]["annotations"]["kure.io/mirror-id"] == "test-uuid"

    def test_prepare_mirror_spec_handles_missing_metadata(self, mirror_service):
        """Works even when metadata is missing from the spec."""
        spec = {
            "apiVersion": "v1",
            "kind": "Pod",
            "spec": {"containers": [{"name": "app", "image": "nginx"}]}
        }

        mirror_service._prepare_mirror_spec(
            spec,
            mirror_pod_name="test-kure-mirror",
            original_pod_name="test",
            namespace="default",
            pod_failure_id=1,
            mirror_id="uuid",
            ttl_seconds=180,
            created_at="2025-01-01T00:00:00Z"
        )

        assert spec["metadata"]["name"] == "test-kure-mirror"
        assert spec["metadata"]["labels"]["kure.io/mirror"] == "true"

    def test_prepare_mirror_spec_strips_node_name(self, mirror_service):
        """nodeName should be stripped so the scheduler can place the pod."""
        spec = {
            "metadata": {"name": "x", "namespace": "default"},
            "spec": {
                "nodeName": "specific-node",
                "containers": [{"name": "app", "image": "nginx"}]
            }
        }

        mirror_service._prepare_mirror_spec(
            spec,
            mirror_pod_name="x-kure-mirror",
            original_pod_name="x",
            namespace="default",
            pod_failure_id=1,
            mirror_id="uuid",
            ttl_seconds=180,
            created_at="2025-01-01T00:00:00Z"
        )

        assert "nodeName" not in spec["spec"]

    # --- list_active_mirrors ---

    def test_list_active_mirrors_empty(self, mirror_service):
        """Returns empty list when no mirrors."""
        assert mirror_service.list_active_mirrors() == []

    def test_list_active_mirrors_returns_all(self, mirror_service):
        """Returns all tracked mirrors."""
        mirror_service._active_mirrors = {
            "id-1": {"mirror_id": "id-1", "mirror_pod_name": "a-kure-mirror"},
            "id-2": {"mirror_id": "id-2", "mirror_pod_name": "b-kure-mirror"},
        }
        result = mirror_service.list_active_mirrors()
        assert len(result) == 2

    # --- create_mirror (K8s mocked via fixture) ---

    @pytest.mark.asyncio
    async def test_create_mirror_pod_failure_not_found(self, mirror_service, mock_db):
        """Raises ValueError when pod failure record does not exist."""
        mock_db.get_pod_failure_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Pod failure record not found"):
            await mirror_service.create_mirror(pod_failure_id=999)

    # --- delete_mirror ---

    @pytest.mark.asyncio
    async def test_delete_mirror_not_found(self, mirror_service):
        """Raises ValueError when mirror_id doesn't exist."""
        with pytest.raises(ValueError, match="Mirror pod not found"):
            await mirror_service.delete_mirror("nonexistent-id")

    @pytest.mark.asyncio
    async def test_delete_mirror_success(self, mirror_service, mock_websocket_manager):
        """Successfully deletes a tracked mirror pod."""
        mirror_service._k8s_core_v1.delete_namespaced_pod.return_value = None

        # Pre-populate a mirror
        mirror_service._active_mirrors["test-id"] = {
            "mirror_id": "test-id",
            "mirror_pod_name": "pod-kure-mirror",
            "namespace": "default",
            "source_pod_name": "pod",
            "pod_failure_id": 1,
        }

        result = await mirror_service.delete_mirror("test-id")
        assert result is True
        assert "test-id" not in mirror_service._active_mirrors
        mock_websocket_manager.broadcast_mirror_event.assert_called_once()

    # --- get_mirror_status ---

    @pytest.mark.asyncio
    async def test_get_mirror_status_not_found(self, mirror_service):
        """Raises ValueError when mirror_id doesn't exist."""
        with pytest.raises(ValueError, match="Mirror pod not found"):
            await mirror_service.get_mirror_status("nonexistent-id")

    # --- cleanup ---

    @pytest.mark.asyncio
    async def test_cleanup_expired_mirrors(self, mirror_service, mock_websocket_manager):
        """Cleanup removes expired mirrors."""
        mirror_service._k8s_core_v1.delete_namespaced_pod.return_value = None

        # Add an already-expired mirror
        mirror_service._active_mirrors["expired-id"] = {
            "mirror_id": "expired-id",
            "mirror_pod_name": "expired-kure-mirror",
            "namespace": "default",
            "source_pod_name": "expired",
            "pod_failure_id": 1,
            "expires_at": "2020-01-01T00:00:00+00:00",  # Well in the past
        }

        # Add a still-valid mirror
        mirror_service._active_mirrors["valid-id"] = {
            "mirror_id": "valid-id",
            "mirror_pod_name": "valid-kure-mirror",
            "namespace": "default",
            "source_pod_name": "valid",
            "pod_failure_id": 2,
            "expires_at": "2099-01-01T00:00:00+00:00",  # Far in the future
        }

        await mirror_service._cleanup_expired_mirrors()

        assert "expired-id" not in mirror_service._active_mirrors
        assert "valid-id" in mirror_service._active_mirrors


class TestCleanManifest:
    """Tests for the clean_manifest utility function."""

    def _full_manifest(self) -> dict:
        """Return a realistic pod manifest with all runtime fields present."""
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "my-app-7b8f4d9c6-xz2k4",
                "namespace": "production",
                "labels": {"app": "my-app", "version": "v2"},
                "annotations": {"prometheus.io/scrape": "true"},
                "creationTimestamp": "2025-06-15T10:00:00Z",
                "deletionTimestamp": "2025-06-15T12:00:00Z",
                "deletionGracePeriodSeconds": 30,
                "generateName": "my-app-7b8f4d9c6-",
                "generation": 1,
                "resourceVersion": "987654",
                "selfLink": "/api/v1/namespaces/production/pods/my-app-7b8f4d9c6-xz2k4",
                "uid": "abc-def-123-456",
                "managedFields": [{"manager": "kube-controller-manager"}],
                "ownerReferences": [{"kind": "ReplicaSet", "name": "my-app-7b8f4d9c6"}],
                "finalizers": ["foregroundDeletion"],
            },
            "spec": {
                "containers": [
                    {
                        "name": "app",
                        "image": "my-app:v2",
                        "ports": [{"containerPort": 8080}],
                        "env": [{"name": "LOG_LEVEL", "value": "info"}],
                        "resources": {"limits": {"memory": "512Mi"}, "requests": {"memory": "256Mi"}},
                        "terminationMessagePath": "/dev/termination-log",
                        "terminationMessagePolicy": "File",
                        "volumeMounts": [{"name": "config", "mountPath": "/etc/config"}],
                    }
                ],
                "initContainers": [
                    {
                        "name": "init-db",
                        "image": "busybox:1.36",
                        "command": ["sh", "-c", "echo init"],
                        "terminationMessagePath": "/dev/termination-log",
                        "terminationMessagePolicy": "File",
                    }
                ],
                "volumes": [{"name": "config", "configMap": {"name": "my-config"}}],
                "nodeName": "worker-node-3",
                "serviceAccountName": "default",
                "priority": 0,
                "priorityClassName": "",
                "preemptionPolicy": "PreemptLowerPriority",
                "enableServiceLinks": True,
                "restartPolicy": "Always",
                "nodeSelector": {"disktype": "ssd"},
                "tolerations": [{"key": "dedicated", "operator": "Equal", "value": "gpu"}],
                "securityContext": {"runAsNonRoot": True},
                "dnsPolicy": "ClusterFirst",
                "imagePullSecrets": [{"name": "regcred"}],
            },
            "status": {
                "phase": "Running",
                "podIP": "10.0.0.42",
                "podIPs": [{"ip": "10.0.0.42"}],
                "hostIP": "192.168.1.10",
                "hostIPs": [{"ip": "192.168.1.10"}],
                "startTime": "2025-06-15T10:00:05Z",
                "conditions": [{"type": "Ready", "status": "True"}],
                "containerStatuses": [{"name": "app", "ready": True}],
                "initContainerStatuses": [{"name": "init-db", "ready": True}],
                "qosClass": "Burstable",
            },
        }

    def test_removes_top_level_status(self):
        """The entire status section should be removed."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        assert "status" not in result

    def test_removes_metadata_runtime_fields(self):
        """All runtime metadata fields should be stripped."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        meta = result["metadata"]
        for field in [
            "creationTimestamp", "deletionTimestamp", "deletionGracePeriodSeconds",
            "generateName", "generation", "resourceVersion", "selfLink", "uid",
            "managedFields", "ownerReferences", "finalizers",
        ]:
            assert field not in meta, f"{field} should have been removed from metadata"

    def test_keeps_metadata_user_fields(self):
        """name, namespace, labels, annotations must be preserved."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        meta = result["metadata"]
        assert meta["name"] == "my-app-7b8f4d9c6-xz2k4"
        assert meta["namespace"] == "production"
        assert meta["labels"] == {"app": "my-app", "version": "v2"}
        assert meta["annotations"] == {"prometheus.io/scrape": "true"}

    def test_removes_spec_runtime_fields(self):
        """nodeName, priority, preemptionPolicy, enableServiceLinks should be removed."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        spec = result["spec"]
        for field in ["nodeName", "priority", "preemptionPolicy", "enableServiceLinks"]:
            assert field not in spec, f"{field} should have been removed from spec"

    def test_removes_default_service_account(self):
        """serviceAccountName='default' should be removed."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        assert "serviceAccountName" not in result["spec"]

    def test_keeps_non_default_service_account(self):
        """serviceAccountName with a real name should be preserved."""
        manifest = self._full_manifest()
        manifest["spec"]["serviceAccountName"] = "my-custom-sa"
        result = yaml.safe_load(clean_manifest(manifest))
        assert result["spec"]["serviceAccountName"] == "my-custom-sa"

    def test_removes_empty_priority_class_name(self):
        """Empty priorityClassName should be removed."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        assert "priorityClassName" not in result["spec"]

    def test_keeps_nonempty_priority_class_name(self):
        """Non-empty priorityClassName should be preserved."""
        manifest = self._full_manifest()
        manifest["spec"]["priorityClassName"] = "high-priority"
        result = yaml.safe_load(clean_manifest(manifest))
        assert result["spec"]["priorityClassName"] == "high-priority"

    def test_removes_container_termination_fields(self):
        """terminationMessagePath and terminationMessagePolicy removed from containers."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        container = result["spec"]["containers"][0]
        assert "terminationMessagePath" not in container
        assert "terminationMessagePolicy" not in container

    def test_removes_init_container_termination_fields(self):
        """terminationMessagePath and terminationMessagePolicy removed from initContainers."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        init_container = result["spec"]["initContainers"][0]
        assert "terminationMessagePath" not in init_container
        assert "terminationMessagePolicy" not in init_container

    def test_keeps_container_user_fields(self):
        """Container image, ports, env, resources, volumeMounts should be preserved."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        container = result["spec"]["containers"][0]
        assert container["name"] == "app"
        assert container["image"] == "my-app:v2"
        assert container["ports"] == [{"containerPort": 8080}]
        assert container["env"] == [{"name": "LOG_LEVEL", "value": "info"}]
        assert "resources" in container
        assert container["volumeMounts"] == [{"name": "config", "mountPath": "/etc/config"}]

    def test_keeps_spec_user_fields(self):
        """volumes, nodeSelector, tolerations, restartPolicy, securityContext, etc. preserved."""
        result = yaml.safe_load(clean_manifest(self._full_manifest()))
        spec = result["spec"]
        assert spec["volumes"] == [{"name": "config", "configMap": {"name": "my-config"}}]
        assert spec["nodeSelector"] == {"disktype": "ssd"}
        assert spec["tolerations"] == [{"key": "dedicated", "operator": "Equal", "value": "gpu"}]
        assert spec["restartPolicy"] == "Always"
        assert spec["securityContext"] == {"runAsNonRoot": True}
        assert spec["dnsPolicy"] == "ClusterFirst"
        assert spec["imagePullSecrets"] == [{"name": "regcred"}]

    def test_accepts_yaml_string(self):
        """clean_manifest should accept a YAML string and return a cleaned YAML string."""
        yaml_input = yaml.dump(self._full_manifest(), default_flow_style=False)
        result_str = clean_manifest(yaml_input)
        result = yaml.safe_load(result_str)
        assert "status" not in result
        assert "uid" not in result["metadata"]
        assert "nodeName" not in result["spec"]

    def test_does_not_mutate_input_dict(self):
        """Passing a dict should not modify the original."""
        manifest = self._full_manifest()
        original_uid = manifest["metadata"]["uid"]
        clean_manifest(manifest)
        assert manifest["metadata"]["uid"] == original_uid
        assert "status" in manifest

    def test_returns_string(self):
        """Return type should always be a YAML string."""
        result = clean_manifest(self._full_manifest())
        assert isinstance(result, str)
        # Should be parseable YAML
        parsed = yaml.safe_load(result)
        assert isinstance(parsed, dict)

    def test_handles_minimal_manifest(self):
        """Should work with a bare-minimum manifest (no metadata, no spec)."""
        manifest = {"apiVersion": "v1", "kind": "Pod"}
        result = yaml.safe_load(clean_manifest(manifest))
        assert result["apiVersion"] == "v1"
        assert result["kind"] == "Pod"

    def test_handles_snake_case_fields(self):
        """Should remove snake_case variants (from K8s Python client .to_dict())."""
        manifest = {
            "metadata": {
                "name": "test",
                "creation_timestamp": "2025-01-01T00:00:00Z",
                "resource_version": "123",
                "owner_references": [{"kind": "ReplicaSet"}],
                "managed_fields": [{"manager": "kubectl"}],
                "generate_name": "test-",
                "self_link": "/api/v1/pods/test",
                "deletion_timestamp": "2025-01-02T00:00:00Z",
                "deletion_grace_period_seconds": 30,
            },
            "spec": {
                "node_name": "worker-1",
                "enable_service_links": True,
                "preemption_policy": "PreemptLowerPriority",
                "service_account_name": "default",
                "priority_class_name": "",
                "containers": [
                    {
                        "name": "app",
                        "image": "nginx",
                        "termination_message_path": "/dev/termination-log",
                        "termination_message_policy": "File",
                    }
                ],
            },
        }
        result = yaml.safe_load(clean_manifest(manifest))

        meta = result["metadata"]
        assert meta["name"] == "test"
        for field in ["creation_timestamp", "resource_version", "owner_references",
                      "managed_fields", "generate_name", "self_link",
                      "deletion_timestamp", "deletion_grace_period_seconds"]:
            assert field not in meta

        spec = result["spec"]
        for field in ["node_name", "enable_service_links", "preemption_policy",
                      "service_account_name", "priority_class_name"]:
            assert field not in spec

        container = spec["containers"][0]
        assert "termination_message_path" not in container
        assert "termination_message_policy" not in container

    def test_idempotent(self):
        """Cleaning an already-clean manifest should produce the same result."""
        first_pass = clean_manifest(self._full_manifest())
        second_pass = clean_manifest(first_pass)
        assert first_pass == second_pass

    def test_raises_on_invalid_type(self):
        """Should raise TypeError for non-str, non-dict input."""
        with pytest.raises(TypeError, match="Expected str or dict"):
            clean_manifest(42)

    def test_passthrough_for_non_dict_yaml(self):
        """If YAML string parses to a non-dict (e.g. a list), return as-is."""
        yaml_list = "- item1\n- item2\n"
        result = clean_manifest(yaml_list)
        assert result == yaml_list

    def test_no_containers_key(self):
        """Should handle spec with no containers key gracefully."""
        manifest = {
            "metadata": {"name": "test"},
            "spec": {"nodeName": "worker-1"},
        }
        result = yaml.safe_load(clean_manifest(manifest))
        assert "nodeName" not in result["spec"]
