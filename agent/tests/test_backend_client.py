import pytest
from unittest.mock import Mock, AsyncMock, patch
from clients.backend_client import BackendClient
import aiohttp


class TestBackendClient:
    
    @pytest.fixture
    def backend_client(self):
        """Create BackendClient instance"""
        return BackendClient("http://test-backend:8000")

    @pytest.fixture
    def mock_pod_data(self):
        """Create mock pod failure data"""
        return {
            "pod_name": "test-pod",
            "namespace": "default",
            "failure_reason": "ImagePullBackOff",
            "failure_message": "Failed to pull image"
        }

    @pytest.mark.asyncio
    async def test_report_failed_pod_success(self, backend_client, mock_pod_data):
        """Test successful pod failure reporting"""
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Mock successful response
            mock_response = AsyncMock()
            mock_response.status = 200
            
            # Mock the session and post context managers
            mock_session = AsyncMock()
            mock_post = AsyncMock()
            mock_post.__aenter__.return_value = mock_response
            mock_session.post.return_value = mock_post
            mock_session_class.return_value.__aenter__.return_value = mock_session
            
            result = await backend_client.report_failed_pod(mock_pod_data)
            
            assert result == True

    @pytest.mark.asyncio
    async def test_report_failed_pod_http_error(self, backend_client, mock_pod_data):
        """Test pod failure reporting with HTTP error"""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock error response with JSON body
            mock_response = Mock()
            mock_response.status = 500
            mock_response.json = AsyncMock(return_value={
                "message": "Internal server error",
                "error_type": "DatabaseError"
            })
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await backend_client.report_failed_pod(mock_pod_data)
            
            assert result == False

    @pytest.mark.asyncio
    async def test_report_failed_pod_timeout(self, backend_client, mock_pod_data):
        """Test pod failure reporting with timeout"""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock timeout
            mock_session.return_value.__aenter__.return_value.post.side_effect = aiohttp.ClientTimeout()
            
            result = await backend_client.report_failed_pod(mock_pod_data)
            
            assert result == False

    @pytest.mark.asyncio
    async def test_report_failed_pod_client_error(self, backend_client, mock_pod_data):
        """Test pod failure reporting with client error"""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock client error
            mock_session.return_value.__aenter__.return_value.post.side_effect = aiohttp.ClientError("Connection failed")
            
            result = await backend_client.report_failed_pod(mock_pod_data)
            
            assert result == False

    @pytest.mark.asyncio
    async def test_report_cluster_info_success(self, backend_client):
        """Test successful cluster info reporting"""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock successful response
            mock_response = Mock()
            mock_response.status = 200
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await backend_client.report_cluster_info("test-cluster")
            
            assert result == True

    @pytest.mark.asyncio
    async def test_report_cluster_info_failure(self, backend_client):
        """Test cluster info reporting failure"""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock error response
            mock_response = Mock()
            mock_response.status = 400
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await backend_client.report_cluster_info("test-cluster")
            
            assert result == False

    @pytest.mark.asyncio
    async def test_dismiss_deleted_pod_success(self, backend_client):
        """Test successful pod dismissal"""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock successful response
            mock_response = Mock()
            mock_response.status = 200
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await backend_client.dismiss_deleted_pod("default", "deleted-pod")
            
            assert result == True

    @pytest.mark.asyncio
    async def test_dismiss_deleted_pod_failure(self, backend_client):
        """Test pod dismissal failure"""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock error response with JSON
            mock_response = Mock()
            mock_response.status = 404
            mock_response.json = AsyncMock(return_value={
                "message": "Pod not found"
            })
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await backend_client.dismiss_deleted_pod("default", "missing-pod")
            
            assert result == False

    def test_backend_url_normalization(self):
        """Test that backend URL is properly normalized"""
        client1 = BackendClient("http://test-backend:8000/")
        client2 = BackendClient("http://test-backend:8000")
        
        # Both should have the same normalized URL
        assert client1.backend_url == "http://test-backend:8000"
        assert client2.backend_url == "http://test-backend:8000"