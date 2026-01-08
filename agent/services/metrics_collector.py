import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from kubernetes import client
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects cluster metrics from Kubernetes API"""

    def __init__(self, v1_api: client.CoreV1Api):
        self.v1 = v1_api
        self.custom_api = client.CustomObjectsApi()
        self.metrics_available = False

    def _parse_resource(self, resource_str: str) -> int:
        """Parse Kubernetes resource string to base units (millicores for CPU, bytes for memory)"""
        if not resource_str:
            return 0

        resource_str = str(resource_str)

        # CPU parsing
        if resource_str.endswith('m'):
            return int(resource_str[:-1])  # millicores
        elif resource_str.endswith('n'):
            return int(resource_str[:-1]) // 1000000  # nanocores to millicores

        # Memory parsing
        multipliers = {
            'Ki': 1024,
            'Mi': 1024 ** 2,
            'Gi': 1024 ** 3,
            'Ti': 1024 ** 4,
            'K': 1000,
            'M': 1000 ** 2,
            'G': 1000 ** 3,
            'T': 1000 ** 4,
        }

        for suffix, multiplier in multipliers.items():
            if resource_str.endswith(suffix):
                return int(resource_str[:-len(suffix)]) * multiplier

        # Plain number (could be CPU cores or bytes)
        try:
            value = float(resource_str)
            # If it looks like CPU cores (small number), convert to millicores
            if value < 1000:
                return int(value * 1000)
            return int(value)
        except ValueError:
            return 0

    def _format_cpu(self, millicores: int) -> str:
        """Format CPU millicores to human-readable string"""
        if millicores >= 1000:
            return f"{millicores / 1000:.1f} cores"
        return f"{millicores}m"

    def _format_memory(self, bytes_val: int) -> str:
        """Format bytes to human-readable string"""
        if bytes_val >= 1024 ** 3:
            return f"{bytes_val / (1024 ** 3):.1f} Gi"
        elif bytes_val >= 1024 ** 2:
            return f"{bytes_val / (1024 ** 2):.1f} Mi"
        elif bytes_val >= 1024:
            return f"{bytes_val / 1024:.1f} Ki"
        return f"{bytes_val} B"

    async def check_metrics_server(self) -> bool:
        """Check if metrics-server is installed and responding"""
        try:
            # Try to get node metrics from metrics.k8s.io API
            self.custom_api.list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes"
            )
            self.metrics_available = True
            logger.info("Metrics server is available")
            return True
        except ApiException as e:
            if e.status == 404:
                logger.info("Metrics server not installed (API not found)")
            else:
                logger.warning(f"Error checking metrics server: {e}")
            self.metrics_available = False
            return False
        except Exception as e:
            logger.warning(f"Error checking metrics server: {e}")
            self.metrics_available = False
            return False

    async def collect_cluster_metrics(self) -> Dict[str, Any]:
        """Collect cluster metrics from Kubernetes API"""
        try:
            nodes = self.v1.list_node()
            node_metrics_data = []

            # Initialize totals
            total_cpu_capacity = 0
            total_cpu_allocatable = 0
            total_cpu_usage = 0
            total_memory_capacity = 0
            total_memory_allocatable = 0
            total_memory_usage = 0
            total_pods = 0

            # Get node metrics if available
            node_usage_map = {}
            if self.metrics_available:
                try:
                    metrics_response = self.custom_api.list_cluster_custom_object(
                        group="metrics.k8s.io",
                        version="v1beta1",
                        plural="nodes"
                    )
                    for item in metrics_response.get('items', []):
                        node_name = item['metadata']['name']
                        usage = item.get('usage', {})
                        node_usage_map[node_name] = {
                            'cpu': self._parse_resource(usage.get('cpu', '0')),
                            'memory': self._parse_resource(usage.get('memory', '0'))
                        }
                except Exception as e:
                    logger.warning(f"Failed to get node metrics: {e}")
                    self.metrics_available = False

            # Count pods per node
            pods = self.v1.list_pod_for_all_namespaces()
            pods_per_node = {}
            for pod in pods.items:
                node_name = pod.spec.node_name
                if node_name:
                    pods_per_node[node_name] = pods_per_node.get(node_name, 0) + 1
                    total_pods += 1

            # Process each node
            for node in nodes.items:
                node_name = node.metadata.name
                status = node.status
                capacity = status.capacity or {}
                allocatable = status.allocatable or {}

                # Parse resources
                cpu_capacity = self._parse_resource(capacity.get('cpu', '0'))
                cpu_allocatable = self._parse_resource(allocatable.get('cpu', '0'))
                memory_capacity = self._parse_resource(capacity.get('memory', '0'))
                memory_allocatable = self._parse_resource(allocatable.get('memory', '0'))
                storage_capacity = self._parse_resource(capacity.get('ephemeral-storage', '0'))

                # Get usage from metrics if available
                usage = node_usage_map.get(node_name, {})
                cpu_usage = usage.get('cpu')
                memory_usage = usage.get('memory')

                # Update totals
                total_cpu_capacity += cpu_capacity
                total_cpu_allocatable += cpu_allocatable
                total_memory_capacity += memory_capacity
                total_memory_allocatable += memory_allocatable
                if cpu_usage is not None:
                    total_cpu_usage += cpu_usage
                if memory_usage is not None:
                    total_memory_usage += memory_usage

                # Get node conditions
                conditions = []
                if status.conditions:
                    for condition in status.conditions:
                        conditions.append({
                            'type': condition.type,
                            'status': condition.status,
                            'reason': condition.reason,
                            'message': condition.message
                        })

                node_data = {
                    'name': node_name,
                    'cpu_capacity': self._format_cpu(cpu_capacity),
                    'cpu_allocatable': self._format_cpu(cpu_allocatable),
                    'cpu_usage': self._format_cpu(cpu_usage) if cpu_usage is not None else None,
                    'memory_capacity': self._format_memory(memory_capacity),
                    'memory_allocatable': self._format_memory(memory_allocatable),
                    'memory_usage': self._format_memory(memory_usage) if memory_usage is not None else None,
                    'storage_capacity': self._format_memory(storage_capacity) if storage_capacity else None,
                    'conditions': conditions,
                    'pods_count': pods_per_node.get(node_name, 0)
                }
                node_metrics_data.append(node_data)

            # Calculate usage percentages
            cpu_usage_percent = None
            memory_usage_percent = None
            if self.metrics_available and total_cpu_allocatable > 0:
                cpu_usage_percent = round((total_cpu_usage / total_cpu_allocatable) * 100, 1)
            if self.metrics_available and total_memory_allocatable > 0:
                memory_usage_percent = round((total_memory_usage / total_memory_allocatable) * 100, 1)

            return {
                'node_count': len(nodes.items),
                'nodes': node_metrics_data,
                'total_cpu_capacity': self._format_cpu(total_cpu_capacity),
                'total_cpu_allocatable': self._format_cpu(total_cpu_allocatable),
                'total_cpu_usage': self._format_cpu(total_cpu_usage) if self.metrics_available else None,
                'cpu_usage_percent': cpu_usage_percent,
                'total_memory_capacity': self._format_memory(total_memory_capacity),
                'total_memory_allocatable': self._format_memory(total_memory_allocatable),
                'total_memory_usage': self._format_memory(total_memory_usage) if self.metrics_available else None,
                'memory_usage_percent': memory_usage_percent,
                'total_pods': total_pods,
                'metrics_available': self.metrics_available,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }

        except Exception as e:
            logger.error(f"Error collecting cluster metrics: {e}")
            return {
                'node_count': 0,
                'nodes': [],
                'total_cpu_capacity': '0',
                'total_cpu_allocatable': '0',
                'total_cpu_usage': None,
                'cpu_usage_percent': None,
                'total_memory_capacity': '0',
                'total_memory_allocatable': '0',
                'total_memory_usage': None,
                'memory_usage_percent': None,
                'total_pods': 0,
                'metrics_available': False,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
