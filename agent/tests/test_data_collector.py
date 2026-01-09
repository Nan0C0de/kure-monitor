import pytest
from unittest.mock import Mock, AsyncMock
from services.data_collector import DataCollector


class TestDataCollector:
    
    @pytest.fixture
    def data_collector(self):
        """Create DataCollector instance"""
        return DataCollector()

    @pytest.fixture
    def mock_pod(self):
        """Create a mock pod"""
        pod = Mock()
        pod.metadata.name = "test-pod"
        pod.metadata.namespace = "default"
        pod.metadata.creation_timestamp.isoformat.return_value = "2025-01-01T00:00:00Z"
        pod.spec.node_name = "test-node"
        pod.status.phase = "Pending"
        pod.status.container_statuses = [Mock()]
        
        container_status = pod.status.container_statuses[0]
        container_status.name = "test-container"
        container_status.ready = False
        container_status.restart_count = 0
        container_status.image = "test:latest"
        container_status.state.waiting = Mock()
        container_status.state.waiting.reason = "ImagePullBackOff"
        container_status.state.waiting.message = "Failed to pull image"
        container_status.state.running = None
        container_status.state.terminated = None
        
        return pod

    @pytest.fixture
    def mock_v1_client(self):
        """Create mock Kubernetes v1 client"""
        client = Mock()

        # Mock events - use ImagePullBackOff to match expected test results
        events = Mock()
        events.items = [Mock()]
        event = events.items[0]
        event.type = "Warning"
        event.reason = "ImagePullBackOff"
        event.message = "Failed to pull image"
        event.first_timestamp = Mock()
        event.first_timestamp.isoformat.return_value = "2025-01-01T00:00:00Z"

        client.list_namespaced_event.return_value = events

        # Mock logs (will fail with 403)
        from kubernetes.client.rest import ApiException
        client.read_namespaced_pod_log.side_effect = ApiException(status=403, reason="Forbidden")

        return client

    @pytest.mark.asyncio
    async def test_collect_pod_data(self, data_collector, mock_pod, mock_v1_client):
        """Test collecting comprehensive pod data"""
        result = await data_collector.collect_pod_data(mock_pod, mock_v1_client)
        
        # Verify basic pod info
        assert result["pod_name"] == "test-pod"
        assert result["namespace"] == "default"
        assert result["node_name"] == "test-node"
        assert result["phase"] == "Pending"
        assert result["creation_timestamp"] == "2025-01-01T00:00:00Z"
        
        # Verify failure info
        assert result["failure_reason"] == "ImagePullBackOff"
        assert result["failure_message"] == "Failed to pull image"
        
        # Verify container statuses
        assert len(result["container_statuses"]) == 1
        container = result["container_statuses"][0]
        assert container["name"] == "test-container"
        assert container["ready"] == False
        assert container["image"] == "test:latest"
        assert container["reason"] == "ImagePullBackOff"
        
        # Verify events were collected
        assert len(result["events"]) == 1
        event = result["events"][0]
        assert event["type"] == "Warning"
        assert event["reason"] == "ImagePullBackOff"
        
        # Verify logs are empty (due to 403 error)
        assert result["logs"] == ""
        
        # Verify manifest was generated
        assert result["manifest"] is not None

    def test_get_failure_reason_from_container_status(self, data_collector):
        """Test extracting failure reason from container status"""
        # Create a pod with Running phase so it falls through to check container statuses
        pod = Mock()
        pod.status.phase = "Running"  # Not Pending, so it checks container statuses
        pod.status.container_statuses = [Mock()]

        container_status = pod.status.container_statuses[0]
        container_status.state.waiting = Mock()
        container_status.state.waiting.reason = "ImagePullBackOff"

        result = data_collector._get_failure_reason(pod)
        assert result == "ImagePullBackOff"

    def test_get_failure_reason_pending_phase(self, data_collector):
        """Test failure reason for pending phase"""
        pod = Mock()
        pod.status.phase = "Pending"
        pod.status.container_statuses = None
        
        result = data_collector._get_failure_reason(pod)
        assert result == "Pending"

    def test_get_failure_message_from_container(self, data_collector, mock_pod):
        """Test extracting failure message from container status"""
        result = data_collector._get_failure_message(mock_pod)
        assert result == "Failed to pull image"

    def test_get_failure_message_from_events(self, data_collector):
        """Test extracting failure message from events when container message unavailable"""
        pod = Mock()
        pod.status.container_statuses = None
        
        events = [
            {
                "type": "Warning",
                "reason": "FailedMount",
                "message": "MountVolume.SetUp failed: secret 'test' not found"
            }
        ]
        
        result = data_collector._get_failure_message(pod, events)
        assert result == "MountVolume.SetUp failed: secret 'test' not found"

    def test_get_container_statuses_waiting_state(self, data_collector, mock_pod):
        """Test getting container statuses in waiting state"""
        result = data_collector._get_container_statuses(mock_pod)
        
        assert len(result) == 1
        container = result[0]
        assert container["name"] == "test-container"
        assert container["state"] == "waiting"
        assert container["reason"] == "ImagePullBackOff"
        assert container["message"] == "Failed to pull image"

    def test_get_container_statuses_terminated_state(self, data_collector):
        """Test getting container statuses in terminated state"""
        pod = Mock()
        pod.status.container_statuses = [Mock()]
        
        container_status = pod.status.container_statuses[0]
        container_status.name = "terminated-container"
        container_status.ready = False
        container_status.restart_count = 1
        container_status.image = "test:latest"
        container_status.state.waiting = None
        container_status.state.running = None
        container_status.state.terminated = Mock()
        container_status.state.terminated.exit_code = 1
        container_status.state.terminated.reason = "Error"
        
        result = data_collector._get_container_statuses(pod)
        
        assert len(result) == 1
        container = result[0]
        assert container["state"] == "terminated"
        assert container["exit_code"] == 1
        assert container["reason"] == "Error"