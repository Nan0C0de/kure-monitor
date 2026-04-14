import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, Mock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from fastapi import Request

from api.routes_mirror import create_mirror_router
from api.deps import RouterDeps
from api.middleware import configure_cors
from api.auth import require_user, require_write, require_admin
from services.mirror_service import MirrorService


async def _fake_user():
    """Fake authenticated user for tests."""
    return {"id": 1, "username": "test-admin", "role": "admin"}


class TestMirrorRoutes:
    """Tests for mirror pod API routes."""

    @pytest_asyncio.fixture
    async def mock_mirror_service(self):
        service = AsyncMock(spec=MirrorService)
        service.list_active_mirrors = Mock(return_value=[])
        service.get_default_ttl = AsyncMock(return_value=180)
        service.set_default_ttl = AsyncMock()
        return service

    @pytest_asyncio.fixture
    async def app(self, mock_mirror_service):
        test_app = FastAPI()
        configure_cors(test_app)

        # Override auth dependencies so tests don't need real auth
        test_app.dependency_overrides[require_user] = _fake_user
        test_app.dependency_overrides[require_write] = _fake_user
        test_app.dependency_overrides[require_admin] = _fake_user

        deps = RouterDeps(
            db=AsyncMock(),
            solution_engine=AsyncMock(),
            websocket_manager=AsyncMock(),
        )

        router = create_mirror_router(deps, mock_mirror_service)
        test_app.include_router(router, prefix="/api")

        return test_app

    @pytest_asyncio.fixture
    async def client(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    # --- GET /api/mirror/active ---

    @pytest.mark.asyncio
    async def test_list_active_mirrors_empty(self, client, mock_mirror_service):
        """Returns empty list when no mirrors exist."""
        response = await client.get("/api/mirror/active")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_active_mirrors_with_data(self, client, mock_mirror_service):
        """Returns list of active mirrors."""
        mock_mirror_service.list_active_mirrors.return_value = [
            {
                "mirror_id": "abc-123",
                "mirror_pod_name": "test-kure-mirror",
                "namespace": "default",
                "source_pod_name": "test",
                "pod_failure_id": 42,
                "phase": "Running",
                "ttl_seconds": 180,
                "created_at": "2025-01-01T00:00:00+00:00",
                "expires_at": "2025-01-01T00:03:00+00:00",
            }
        ]

        response = await client.get("/api/mirror/active")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["mirror_id"] == "abc-123"
        assert data[0]["mirror_pod_name"] == "test-kure-mirror"
        assert data[0]["source_pod_name"] == "test"

    # --- POST /api/mirror/preview/{pod_id} ---

    @pytest.mark.asyncio
    async def test_preview_mirror_fix_success(self, client, mock_mirror_service):
        """Returns AI-fixed manifest preview."""
        mock_mirror_service.generate_preview.return_value = {
            "fixed_manifest": "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test",
            "explanation": "Changed image tag from latest to 1.0",
            "is_fallback": False,
        }

        response = await client.post("/api/mirror/preview/42")
        assert response.status_code == 200
        data = response.json()
        assert data["fixed_manifest"] == "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test"
        assert data["explanation"] == "Changed image tag from latest to 1.0"
        assert data["is_fallback"] is False
        mock_mirror_service.generate_preview.assert_called_once_with(pod_failure_id=42)

    @pytest.mark.asyncio
    async def test_preview_mirror_fix_fallback(self, client, mock_mirror_service):
        """Returns fallback when no LLM is configured."""
        mock_mirror_service.generate_preview.return_value = {
            "fixed_manifest": "",
            "explanation": "No LLM configured. Cannot generate a fixed manifest automatically.",
            "is_fallback": True,
        }

        response = await client.post("/api/mirror/preview/42")
        assert response.status_code == 200
        data = response.json()
        assert data["is_fallback"] is True
        assert data["fixed_manifest"] == ""

    @pytest.mark.asyncio
    async def test_preview_mirror_fix_not_found(self, client, mock_mirror_service):
        """Returns 404 when pod failure not found."""
        mock_mirror_service.generate_preview.side_effect = ValueError("Pod failure record not found: 999")

        response = await client.post("/api/mirror/preview/999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_preview_mirror_fix_pod_gone(self, client, mock_mirror_service):
        """Returns 404 when the pod no longer exists in K8s."""
        mock_mirror_service.generate_preview.side_effect = ValueError(
            "Pod 'test-pod' not found in namespace 'default'. It may have been deleted."
        )

        response = await client.post("/api/mirror/preview/42")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_mirror_fix_k8s_error(self, client, mock_mirror_service):
        """Returns 502 when K8s API fails."""
        mock_mirror_service.generate_preview.side_effect = RuntimeError("Kubernetes API error: Forbidden")

        response = await client.post("/api/mirror/preview/42")
        assert response.status_code == 502

    # --- POST /api/mirror/deploy/{pod_id} ---

    @pytest.mark.asyncio
    async def test_deploy_mirror_success(self, client, mock_mirror_service):
        """Successfully deploys a mirror pod."""
        mock_mirror_service.create_mirror.return_value = {
            "mirror_id": "new-uuid",
            "mirror_pod_name": "failing-pod-kure-mirror",
            "namespace": "default",
            "phase": "Pending",
            "ttl_seconds": 180,
            "created_at": "2025-01-01T00:00:00+00:00",
            "fixed_manifest": "apiVersion: v1\nkind: Pod",
            "explanation": "Fixed the image tag",
        }

        response = await client.post("/api/mirror/deploy/42", json={"ttl_seconds": 180})
        assert response.status_code == 200
        data = response.json()
        assert data["mirror_id"] == "new-uuid"
        assert data["mirror_pod_name"] == "failing-pod-kure-mirror"
        assert data["ttl_seconds"] == 180

    @pytest.mark.asyncio
    async def test_deploy_mirror_no_body(self, client, mock_mirror_service):
        """Deploys with default TTL when no body is sent."""
        mock_mirror_service.create_mirror.return_value = {
            "mirror_id": "new-uuid",
            "mirror_pod_name": "pod-kure-mirror",
            "namespace": "default",
            "phase": "Pending",
            "ttl_seconds": 180,
            "created_at": "2025-01-01T00:00:00+00:00",
            "fixed_manifest": "",
            "explanation": "",
        }

        response = await client.post("/api/mirror/deploy/42")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_deploy_mirror_with_manifest(self, client, mock_mirror_service):
        """Deploys using a user-provided manifest instead of AI generation."""
        user_manifest = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: my-fixed-pod"
        mock_mirror_service.create_mirror.return_value = {
            "mirror_id": "custom-uuid",
            "mirror_pod_name": "pod-kure-mirror",
            "namespace": "default",
            "phase": "Pending",
            "ttl_seconds": 300,
            "created_at": "2025-01-01T00:00:00+00:00",
            "fixed_manifest": user_manifest,
            "explanation": "User-provided manifest",
        }

        response = await client.post(
            "/api/mirror/deploy/42",
            json={"ttl_seconds": 300, "manifest": user_manifest},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mirror_id"] == "custom-uuid"
        assert data["fixed_manifest"] == user_manifest
        mock_mirror_service.create_mirror.assert_called_once_with(
            pod_failure_id=42,
            ttl_seconds=300,
            manifest=user_manifest,
        )

    @pytest.mark.asyncio
    async def test_deploy_mirror_not_found(self, client, mock_mirror_service):
        """Returns 404 when pod failure not found."""
        mock_mirror_service.create_mirror.side_effect = ValueError("Pod failure record not found: 999")

        response = await client.post("/api/mirror/deploy/999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_deploy_mirror_k8s_error(self, client, mock_mirror_service):
        """Returns 502 when K8s API fails."""
        mock_mirror_service.create_mirror.side_effect = RuntimeError("Failed to create mirror pod: Forbidden")

        response = await client.post("/api/mirror/deploy/42")
        assert response.status_code == 502

    # --- GET /api/mirror/status/{mirror_id} ---

    @pytest.mark.asyncio
    async def test_get_mirror_status_success(self, client, mock_mirror_service):
        """Returns mirror pod status."""
        mock_mirror_service.get_mirror_status.return_value = {
            "mirror_id": "abc-123",
            "mirror_pod_name": "test-kure-mirror",
            "namespace": "default",
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True", "reason": "", "message": ""}],
            "events": [],
            "created_at": "2025-01-01T00:00:00+00:00",
            "expires_at": "2025-01-01T00:03:00+00:00",
        }

        response = await client.get("/api/mirror/status/abc-123")
        assert response.status_code == 200
        data = response.json()
        assert data["phase"] == "Running"
        assert len(data["conditions"]) == 1

    @pytest.mark.asyncio
    async def test_get_mirror_status_not_found(self, client, mock_mirror_service):
        """Returns 404 when mirror not found."""
        mock_mirror_service.get_mirror_status.side_effect = ValueError("Mirror pod not found: xyz")

        response = await client.get("/api/mirror/status/xyz")
        assert response.status_code == 404

    # --- DELETE /api/mirror/{mirror_id} ---

    @pytest.mark.asyncio
    async def test_delete_mirror_success(self, client, mock_mirror_service):
        """Successfully deletes a mirror pod."""
        mock_mirror_service.delete_mirror.return_value = True

        response = await client.delete("/api/mirror/abc-123")
        assert response.status_code == 200
        assert response.json()["message"] == "Mirror pod deleted"

    @pytest.mark.asyncio
    async def test_delete_mirror_not_found(self, client, mock_mirror_service):
        """Returns 404 when mirror not found."""
        mock_mirror_service.delete_mirror.side_effect = ValueError("Mirror pod not found: xyz")

        response = await client.delete("/api/mirror/xyz")
        assert response.status_code == 404

    # --- GET /api/admin/settings/mirror-ttl ---

    @pytest.mark.asyncio
    async def test_get_mirror_ttl(self, client, mock_mirror_service):
        """Returns the default TTL."""
        mock_mirror_service.get_default_ttl.return_value = 180

        response = await client.get("/api/admin/settings/mirror-ttl")
        assert response.status_code == 200
        assert response.json()["seconds"] == 180

    # --- PUT /api/admin/settings/mirror-ttl ---

    @pytest.mark.asyncio
    async def test_set_mirror_ttl_success(self, client, mock_mirror_service):
        """Sets a valid TTL."""
        response = await client.put("/api/admin/settings/mirror-ttl", json={"seconds": 600})
        assert response.status_code == 200
        assert response.json()["seconds"] == 600
        mock_mirror_service.set_default_ttl.assert_called_once_with(600)

    @pytest.mark.asyncio
    async def test_set_mirror_ttl_too_low(self, client, mock_mirror_service):
        """Rejects TTL below minimum."""
        response = await client.put("/api/admin/settings/mirror-ttl", json={"seconds": 10})
        assert response.status_code == 400
        assert "between 30 and 3600" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_set_mirror_ttl_too_high(self, client, mock_mirror_service):
        """Rejects TTL above maximum."""
        response = await client.put("/api/admin/settings/mirror-ttl", json={"seconds": 7200})
        assert response.status_code == 400
        assert "between 30 and 3600" in response.json()["detail"]
