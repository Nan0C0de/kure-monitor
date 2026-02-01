import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta, timezone
from services.pod_monitor import PodMonitor


class TestPodMonitor:
    
    @pytest.fixture
    def mock_pod_running(self):
        """Create a mock running pod"""
        pod = Mock()
        pod.metadata.name = "running-pod"
        pod.metadata.namespace = "default"
        pod.metadata.creation_timestamp = datetime.now()
        pod.status.phase = "Running"
        pod.status.container_statuses = [Mock()]
        pod.status.container_statuses[0].ready = True
        pod.status.container_statuses[0].state.waiting = None
        pod.status.container_statuses[0].state.terminated = None
        return pod

    @pytest.fixture
    def mock_pod_failed(self):
        """Create a mock failed pod with ImagePullBackOff (definitive failure)"""
        pod = Mock()
        pod.metadata.name = "failed-pod"
        pod.metadata.namespace = "default"
        pod.metadata.creation_timestamp = datetime.now(timezone.utc)
        pod.status.phase = "Pending"
        pod.status.init_container_statuses = None
        pod.status.container_statuses = [Mock()]
        pod.status.container_statuses[0].ready = False
        pod.status.container_statuses[0].state.waiting = Mock()
        pod.status.container_statuses[0].state.waiting.reason = "ImagePullBackOff"
        pod.status.container_statuses[0].state.waiting.message = "Failed to pull image"
        pod.status.container_statuses[0].state.terminated = None
        return pod

    @pytest.fixture
    def mock_pod_pending(self):
        """Create a mock pending pod that has exceeded the grace period"""
        pod = Mock()
        pod.metadata.name = "pending-pod"
        pod.metadata.namespace = "default"
        # Created 5 minutes ago — well past the 120s grace period
        pod.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(minutes=5)
        pod.status.phase = "Pending"
        pod.status.init_container_statuses = None
        pod.status.container_statuses = None
        return pod

    @pytest.fixture
    def pod_monitor(self):
        """Create PodMonitor with mocked dependencies"""
        with patch('services.pod_monitor.config'), \
             patch('services.pod_monitor.client'):
            monitor = PodMonitor()
            monitor.backend_client = Mock()
            monitor.backend_client.report_failed_pod = AsyncMock(return_value=True)
            monitor.data_collector = Mock()
            monitor.data_collector.collect_pod_data = AsyncMock(return_value={
                "pod_name": "test-pod",
                "failure_reason": "ImagePullBackOff"
            })
            return monitor

    def test_is_pod_failed_running_pod(self, pod_monitor, mock_pod_running):
        """Test that running pods are not considered failed"""
        assert pod_monitor._is_pod_failed(mock_pod_running) == False

    def test_is_pod_failed_pending_pod(self, pod_monitor, mock_pod_pending):
        """Test that pending pods are considered failed"""
        assert pod_monitor._is_pod_failed(mock_pod_pending) == True

    def test_is_pod_failed_with_container_failure(self, pod_monitor, mock_pod_failed):
        """Test that pods with container failures are considered failed"""
        assert pod_monitor._is_pod_failed(mock_pod_failed) == True

    def test_is_pod_failed_system_namespace(self, pod_monitor):
        """Test that system namespace pods are excluded"""
        pod = Mock()
        pod.metadata.namespace = "kube-system"
        pod.status.phase = "Pending"
        
        assert pod_monitor._is_pod_failed(pod) == False

    def test_is_pod_failed_kure_system_namespace(self, pod_monitor):
        """Test that kure-system namespace pods are excluded"""
        pod = Mock()
        pod.metadata.namespace = "kure-system"
        pod.status.phase = "Failed"
        
        assert pod_monitor._is_pod_failed(pod) == False

    def test_is_pod_failed_succeeded_phase(self, pod_monitor):
        """Test that succeeded pods are not considered failed"""
        pod = Mock()
        pod.metadata.namespace = "default"
        pod.status.phase = "Succeeded"
        
        assert pod_monitor._is_pod_failed(pod) == False

    def test_is_pod_failed_explicit_failed_phase(self, pod_monitor):
        """Test that failed phase pods are considered failed"""
        pod = Mock()
        pod.metadata.namespace = "default"
        pod.status.phase = "Failed"
        
        assert pod_monitor._is_pod_failed(pod) == True

    def test_is_pod_failed_pending_within_grace_period(self, pod_monitor):
        """Test that newly created pending pods are NOT considered failed (grace period)"""
        pod = Mock()
        pod.metadata.name = "new-pending-pod"
        pod.metadata.namespace = "default"
        # Created 30 seconds ago — within the 120s grace period
        pod.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(seconds=30)
        pod.status.phase = "Pending"
        pod.status.init_container_statuses = None
        pod.status.container_statuses = None

        assert pod_monitor._is_pod_failed(pod) == False

    def test_is_pod_failed_pending_with_definitive_failure(self, pod_monitor):
        """Test that pending pods with definitive failures are flagged immediately regardless of age"""
        pod = Mock()
        pod.metadata.name = "new-failing-pod"
        pod.metadata.namespace = "default"
        # Created just 10 seconds ago — but has ImagePullBackOff
        pod.metadata.creation_timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)
        pod.status.phase = "Pending"
        pod.status.init_container_statuses = None
        container = Mock()
        container.state.waiting.reason = "ImagePullBackOff"
        pod.status.container_statuses = [container]

        assert pod_monitor._is_pod_failed(pod) == True

    def test_should_report_pod_new_pod(self, pod_monitor):
        """Test that new pods should be reported"""
        pod = Mock()
        pod.metadata.namespace = "default"
        pod.metadata.name = "new-pod"
        
        assert pod_monitor._should_report_pod(pod) == True

    def test_should_report_pod_recently_reported(self, pod_monitor):
        """Test that recently reported pods should not be reported again"""
        pod = Mock()
        pod.metadata.namespace = "default"
        pod.metadata.name = "reported-pod"
        
        # Mark as recently reported
        pod_key = "default/reported-pod"
        pod_monitor.reported_pods[pod_key] = datetime.now()
        
        assert pod_monitor._should_report_pod(pod) == False

    def test_should_report_pod_old_report(self, pod_monitor):
        """Test that pods reported long ago should be reported again"""
        pod = Mock()
        pod.metadata.namespace = "default"
        pod.metadata.name = "old-report-pod"
        
        # Mark as reported 11 minutes ago
        pod_key = "default/old-report-pod"
        pod_monitor.reported_pods[pod_key] = datetime.now() - timedelta(minutes=11)
        
        assert pod_monitor._should_report_pod(pod) == True

    @pytest.mark.asyncio
    async def test_handle_failed_pod_success(self, pod_monitor, mock_pod_failed):
        """Test successful handling of failed pod"""
        await pod_monitor._handle_failed_pod(mock_pod_failed)
        
        # Verify data collection was called
        pod_monitor.data_collector.collect_pod_data.assert_called_once()
        
        # Verify backend reporting was called
        pod_monitor.backend_client.report_failed_pod.assert_called_once()
        
        # Verify pod was marked as reported
        pod_key = f"{mock_pod_failed.metadata.namespace}/{mock_pod_failed.metadata.name}"
        assert pod_key in pod_monitor.reported_pods

    @pytest.mark.asyncio
    async def test_handle_failed_pod_backend_failure(self, pod_monitor, mock_pod_failed):
        """Test handling of failed pod when backend reporting fails"""
        # Make backend reporting fail
        pod_monitor.backend_client.report_failed_pod.return_value = False
        
        await pod_monitor._handle_failed_pod(mock_pod_failed)
        
        # Verify pod was NOT marked as reported on failure
        pod_key = f"{mock_pod_failed.metadata.namespace}/{mock_pod_failed.metadata.name}"
        assert pod_key not in pod_monitor.reported_pods