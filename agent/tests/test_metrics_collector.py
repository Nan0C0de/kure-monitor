import pytest
from unittest.mock import Mock, MagicMock, patch
from services.metrics_collector import MetricsCollector


class TestMetricsCollector:

    @pytest.fixture
    def mock_v1_api(self):
        """Create mock Kubernetes v1 API client"""
        return Mock()

    @pytest.fixture
    def metrics_collector(self, mock_v1_api):
        """Create MetricsCollector instance"""
        return MetricsCollector(mock_v1_api)

    def test_parse_resource_millicores(self, metrics_collector):
        """Test parsing CPU millicores"""
        assert metrics_collector._parse_resource("100m") == 100
        assert metrics_collector._parse_resource("1000m") == 1000

    def test_parse_resource_nanocores(self, metrics_collector):
        """Test parsing CPU nanocores"""
        assert metrics_collector._parse_resource("1000000000n") == 1000

    def test_parse_resource_memory_ki(self, metrics_collector):
        """Test parsing memory in Ki"""
        assert metrics_collector._parse_resource("1024Ki") == 1024 * 1024

    def test_parse_resource_memory_mi(self, metrics_collector):
        """Test parsing memory in Mi"""
        assert metrics_collector._parse_resource("1Mi") == 1024 * 1024

    def test_parse_resource_memory_gi(self, metrics_collector):
        """Test parsing memory in Gi"""
        assert metrics_collector._parse_resource("1Gi") == 1024 * 1024 * 1024

    def test_parse_resource_plain_number(self, metrics_collector):
        """Test parsing plain CPU cores"""
        assert metrics_collector._parse_resource("2") == 2000  # 2 cores = 2000m

    def test_parse_resource_empty(self, metrics_collector):
        """Test parsing empty string"""
        assert metrics_collector._parse_resource("") == 0
        assert metrics_collector._parse_resource(None) == 0

    def test_format_cpu_millicores(self, metrics_collector):
        """Test formatting CPU millicores"""
        assert metrics_collector._format_cpu(500) == "500m"

    def test_format_cpu_cores(self, metrics_collector):
        """Test formatting CPU cores"""
        assert metrics_collector._format_cpu(2000) == "2.0 cores"

    def test_format_memory_bytes(self, metrics_collector):
        """Test formatting memory in bytes"""
        assert metrics_collector._format_memory(512) == "512 B"

    def test_format_memory_ki(self, metrics_collector):
        """Test formatting memory in Ki"""
        assert metrics_collector._format_memory(2048) == "2.0 Ki"

    def test_format_memory_mi(self, metrics_collector):
        """Test formatting memory in Mi"""
        assert metrics_collector._format_memory(1024 * 1024) == "1.0 Mi"

    def test_format_memory_gi(self, metrics_collector):
        """Test formatting memory in Gi"""
        assert metrics_collector._format_memory(1024 * 1024 * 1024) == "1.0 Gi"

    @pytest.mark.asyncio
    async def test_check_metrics_server_available(self, metrics_collector):
        """Test checking metrics server availability"""
        metrics_collector.custom_api = Mock()
        metrics_collector.custom_api.list_cluster_custom_object.return_value = {"items": []}

        result = await metrics_collector.check_metrics_server()

        assert result == True
        assert metrics_collector.metrics_available == True

    @pytest.mark.asyncio
    async def test_check_metrics_server_not_installed(self, metrics_collector):
        """Test checking metrics server when not installed"""
        from kubernetes.client.rest import ApiException

        metrics_collector.custom_api = Mock()
        metrics_collector.custom_api.list_cluster_custom_object.side_effect = ApiException(
            status=404, reason="Not Found"
        )

        result = await metrics_collector.check_metrics_server()

        assert result == False
        assert metrics_collector.metrics_available == False

    @pytest.mark.asyncio
    async def test_collect_cluster_metrics_counts_unassigned_pods(self, metrics_collector):
        """Test that unassigned (pending) pods are counted separately"""
        # Mock nodes
        mock_node = Mock()
        mock_node.metadata.name = "test-node"
        mock_node.status.capacity = {"cpu": "4", "memory": "8Gi"}
        mock_node.status.allocatable = {"cpu": "4", "memory": "8Gi"}
        mock_node.status.conditions = []

        nodes_response = Mock()
        nodes_response.items = [mock_node]
        metrics_collector.v1.list_node.return_value = nodes_response

        # Mock pods - 2 assigned, 1 unassigned (pending)
        mock_pod_assigned1 = Mock()
        mock_pod_assigned1.metadata.name = "pod-1"
        mock_pod_assigned1.metadata.namespace = "default"
        mock_pod_assigned1.spec.node_name = "test-node"
        mock_pod_assigned1.status.phase = "Running"
        mock_pod_assigned1.status.container_statuses = [Mock(ready=True, restart_count=0)]

        mock_pod_assigned2 = Mock()
        mock_pod_assigned2.metadata.name = "pod-2"
        mock_pod_assigned2.metadata.namespace = "default"
        mock_pod_assigned2.spec.node_name = "test-node"
        mock_pod_assigned2.status.phase = "Running"
        mock_pod_assigned2.status.container_statuses = [Mock(ready=True, restart_count=0)]

        mock_pod_pending = Mock()
        mock_pod_pending.metadata.name = "pending-pod"
        mock_pod_pending.metadata.namespace = "default"
        mock_pod_pending.spec.node_name = None  # Not assigned to any node
        mock_pod_pending.status.phase = "Pending"
        mock_pod_pending.status.container_statuses = None

        pods_response = Mock()
        pods_response.items = [mock_pod_assigned1, mock_pod_assigned2, mock_pod_pending]
        metrics_collector.v1.list_pod_for_all_namespaces.return_value = pods_response

        # Mock storage stats to return None
        with patch.object(metrics_collector, '_get_node_storage_stats', return_value=None):
            result = await metrics_collector.collect_cluster_metrics()

        # Verify counts - only pods assigned to existing nodes are counted
        assert result["total_pods"] == 2
        assert result["nodes"][0]["pods_count"] == 2

    @pytest.mark.asyncio
    async def test_collect_cluster_metrics_all_pods_assigned(self, metrics_collector):
        """Test metrics when all pods are assigned to nodes"""
        # Mock nodes
        mock_node = Mock()
        mock_node.metadata.name = "test-node"
        mock_node.status.capacity = {"cpu": "4", "memory": "8Gi"}
        mock_node.status.allocatable = {"cpu": "4", "memory": "8Gi"}
        mock_node.status.conditions = []

        nodes_response = Mock()
        nodes_response.items = [mock_node]
        metrics_collector.v1.list_node.return_value = nodes_response

        # Mock pods - all assigned
        mock_pod = Mock()
        mock_pod.metadata.name = "pod-1"
        mock_pod.metadata.namespace = "default"
        mock_pod.spec.node_name = "test-node"
        mock_pod.status.phase = "Running"
        mock_pod.status.container_statuses = [Mock(ready=True, restart_count=0)]

        pods_response = Mock()
        pods_response.items = [mock_pod]
        metrics_collector.v1.list_pod_for_all_namespaces.return_value = pods_response

        with patch.object(metrics_collector, '_get_node_storage_stats', return_value=None):
            result = await metrics_collector.collect_cluster_metrics()

        assert result["total_pods"] == 1
        assert result["nodes"][0]["pods_count"] == 1

    @pytest.mark.asyncio
    async def test_collect_cluster_metrics_error_handling(self, metrics_collector):
        """Test error handling in collect_cluster_metrics"""
        metrics_collector.v1.list_node.side_effect = Exception("API Error")

        result = await metrics_collector.collect_cluster_metrics()

        assert result["node_count"] == 0
        assert result["total_pods"] == 0
        assert result["metrics_available"] == False
