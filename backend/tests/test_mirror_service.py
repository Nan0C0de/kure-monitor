import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime, timezone

from services.mirror_service import MirrorService, DEFAULT_MIRROR_TTL_SECONDS
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
