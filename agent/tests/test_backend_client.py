import pytest
import aiohttp
from unittest.mock import Mock, AsyncMock, patch
from clients.backend_client import BackendClient


def _make_session_mock(response):
    """Build a session mock whose .post/.get returns an async-CM yielding response."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=None)

    session = AsyncMock()
    session.closed = False
    session.post = Mock(return_value=cm)
    session.get = Mock(return_value=cm)
    return session, cm


class TestBackendClient:

    @pytest.fixture
    def backend_client(self):
        return BackendClient("http://test-backend:8000")

    @pytest.fixture
    def mock_pod_data(self):
        """Create mock pod failure data"""
        return {
            "pod_name": "test-pod",
            "namespace": "default",
            "failure_reason": "ImagePullBackOff",
            "failure_message": "Failed to pull image",
        }

    @pytest.mark.asyncio
    async def test_report_failed_pod_success(self, backend_client, mock_pod_data):
        """Test successful pod failure reporting"""
        mock_response = AsyncMock()
        mock_response.status = 200
        session, _ = _make_session_mock(mock_response)

        with patch.object(
            backend_client, "_get_session", AsyncMock(return_value=session)
        ):
            result = await backend_client.report_failed_pod(mock_pod_data)

        assert result is True

    @pytest.mark.asyncio
    async def test_report_failed_pod_http_error(self, backend_client, mock_pod_data):
        """Test pod failure reporting with HTTP error"""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(
            return_value={
                "message": "Internal server error",
                "error_type": "DatabaseError",
            }
        )
        session, _ = _make_session_mock(mock_response)

        with patch.object(
            backend_client, "_get_session", AsyncMock(return_value=session)
        ):
            result = await backend_client.report_failed_pod(mock_pod_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_report_failed_pod_timeout(self, backend_client, mock_pod_data):
        """Test pod failure reporting with timeout"""
        session = AsyncMock()
        session.closed = False
        session.post = Mock(side_effect=aiohttp.ClientError("connection failed"))

        with patch.object(
            backend_client, "_get_session", AsyncMock(return_value=session)
        ):
            result = await backend_client.report_failed_pod(mock_pod_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_report_failed_pod_client_error(self, backend_client, mock_pod_data):
        """Test pod failure reporting with client error"""
        session = AsyncMock()
        session.closed = False
        session.post = Mock(side_effect=aiohttp.ClientError("Connection failed"))

        with patch.object(
            backend_client, "_get_session", AsyncMock(return_value=session)
        ):
            result = await backend_client.report_failed_pod(mock_pod_data)

        assert result is False

    @pytest.mark.asyncio
    async def test_dismiss_deleted_pod_success(self, backend_client):
        """Test successful pod dismissal"""
        mock_response = AsyncMock()
        mock_response.status = 200
        session, _ = _make_session_mock(mock_response)

        with patch.object(
            backend_client, "_get_session", AsyncMock(return_value=session)
        ):
            result = await backend_client.dismiss_deleted_pod("default", "deleted-pod")

        assert result is True

    @pytest.mark.asyncio
    async def test_dismiss_deleted_pod_failure(self, backend_client):
        """Test pod dismissal failure"""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.json = AsyncMock(return_value={"message": "Pod not found"})
        session, _ = _make_session_mock(mock_response)

        with patch.object(
            backend_client, "_get_session", AsyncMock(return_value=session)
        ):
            result = await backend_client.dismiss_deleted_pod("default", "missing-pod")

        assert result is False

    def test_backend_url_normalization(self):
        """Test that backend URL is properly normalized"""
        client1 = BackendClient("http://test-backend:8000/")
        client2 = BackendClient("http://test-backend:8000")

        # Both should have the same normalized URL
        assert client1.backend_url == "http://test-backend:8000"
        assert client2.backend_url == "http://test-backend:8000"

    def test_headers_include_service_token(self, monkeypatch):
        """Service token from env must be sent as X-Service-Token header."""
        monkeypatch.setenv("SERVICE_TOKEN", "secret-token-123")
        client = BackendClient("http://test-backend:8000")

        headers = client._headers("application/json")
        assert headers.get("X-Service-Token") == "secret-token-123"
        assert headers.get("Content-Type") == "application/json"
        # The old bearer scheme must not be used.
        assert "Authorization" not in headers

    def test_headers_omit_service_token_when_unset(self, monkeypatch):
        """When SERVICE_TOKEN is missing the header is omitted (degraded mode)."""
        monkeypatch.delenv("SERVICE_TOKEN", raising=False)
        client = BackendClient("http://test-backend:8000")

        headers = client._headers()
        assert "X-Service-Token" not in headers
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_report_failed_pod_sends_service_token_header(
        self, mock_pod_data, monkeypatch
    ):
        """POST /api/pods/failed must include X-Service-Token on the outbound request."""
        monkeypatch.setenv("SERVICE_TOKEN", "outbound-token")
        client = BackendClient("http://test-backend:8000")

        captured = {}

        mock_response = AsyncMock()
        mock_response.status = 200

        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            return cm

        session = AsyncMock()
        session.closed = False
        session.post = Mock(side_effect=fake_post)

        with patch.object(client, "_get_session", AsyncMock(return_value=session)):
            result = await client.report_failed_pod(mock_pod_data)

        assert result is True
        assert captured["headers"]["X-Service-Token"] == "outbound-token"
        assert "Authorization" not in captured["headers"]

    @pytest.mark.asyncio
    async def test_close_closes_session(self, backend_client):
        """close() must close the underlying aiohttp session if present."""
        session = AsyncMock()
        session.closed = False
        session.close = AsyncMock()
        backend_client._session = session

        await backend_client.close()

        session.close.assert_awaited_once()
        assert backend_client._session is None

    @pytest.mark.asyncio
    async def test_close_noop_when_no_session(self, backend_client):
        """close() must be safe when no session has been created."""
        assert backend_client._session is None
        # Should not raise.
        await backend_client.close()
        assert backend_client._session is None

    @pytest.mark.asyncio
    async def test_session_is_reused_across_calls(self, backend_client, mock_pod_data):
        """The shared session must be reused across multiple outbound calls."""
        mock_response = AsyncMock()
        mock_response.status = 200
        session, _ = _make_session_mock(mock_response)

        get_session_mock = AsyncMock(return_value=session)
        with patch.object(backend_client, "_get_session", get_session_mock):
            await backend_client.report_failed_pod(mock_pod_data)
            await backend_client.dismiss_deleted_pod("ns", "pod")
            await backend_client.get_excluded_pods()

        # _get_session was called once per public method, but always returns
        # the same shared session instance.
        assert get_session_mock.await_count == 3
