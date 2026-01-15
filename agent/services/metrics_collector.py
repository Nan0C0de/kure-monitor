import logging
import json
import ast
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

    def _get_node_storage_stats(self, node_name: str) -> Optional[Dict[str, int]]:
        """Get storage stats from kubelet stats/summary endpoint"""
        try:
            # Use the API server proxy to access kubelet stats
            response = self.v1.connect_get_node_proxy_with_path(
                name=node_name,
                path="stats/summary"
            )
            # The kubernetes client returns Python dict format (single quotes)
            # instead of JSON (double quotes), so use ast.literal_eval
            try:
                stats = json.loads(response)
            except json.JSONDecodeError:
                stats = ast.literal_eval(response)

            # Get node filesystem stats
            node_stats = stats.get('node', {})
            fs = node_stats.get('fs', {})

            capacity = fs.get('capacityBytes', 0)
            used = fs.get('usedBytes', 0)
            available = fs.get('availableBytes', 0)

            return {
                'capacity': capacity,
                'used': used,
                'available': available
            }
        except ApiException as e:
            logger.debug(f"Could not get storage stats for node {node_name}: {e.status}")
            return None
        except Exception as e:
            logger.debug(f"Error getting storage stats for node {node_name}: {e}")
            return None

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
            total_storage_capacity = 0
            total_storage_used = 0
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

            # Get set of existing node names for validation
            existing_nodes = {node.metadata.name for node in nodes.items}

            # Count pods per node and collect pod list
            pods = self.v1.list_pod_for_all_namespaces()
            pods_per_node = {}
            pods_list = []
            unassigned_pods = 0
            for pod in pods.items:
                node_name = pod.spec.node_name
                if node_name and node_name in existing_nodes:
                    # Pod is assigned to an existing node
                    pods_per_node[node_name] = pods_per_node.get(node_name, 0) + 1
                else:
                    # Pod has no node or is assigned to a non-existent node
                    unassigned_pods += 1
                total_pods += 1

                # Get pod status
                phase = pod.status.phase
                ready = False
                restarts = 0
                if pod.status.container_statuses:
                    ready = all(cs.ready for cs in pod.status.container_statuses)
                    restarts = sum(cs.restart_count for cs in pod.status.container_statuses)

                # Determine display node name
                if not node_name:
                    display_node = 'Pending'
                elif node_name not in existing_nodes:
                    display_node = f'{node_name} (Unknown)'
                else:
                    display_node = node_name

                pods_list.append({
                    'name': pod.metadata.name,
                    'namespace': pod.metadata.namespace,
                    'node': display_node,
                    'status': phase,
                    'ready': ready,
                    'restarts': restarts
                })

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

                # Get usage from metrics if available
                usage = node_usage_map.get(node_name, {})
                cpu_usage = usage.get('cpu')
                memory_usage = usage.get('memory')

                # Get storage stats from kubelet
                storage_stats = self._get_node_storage_stats(node_name)
                storage_capacity = storage_stats['capacity'] if storage_stats else 0
                storage_used = storage_stats['used'] if storage_stats else None

                # Update totals
                total_cpu_capacity += cpu_capacity
                total_cpu_allocatable += cpu_allocatable
                total_memory_capacity += memory_capacity
                total_memory_allocatable += memory_allocatable
                if cpu_usage is not None:
                    total_cpu_usage += cpu_usage
                if memory_usage is not None:
                    total_memory_usage += memory_usage
                if storage_capacity:
                    total_storage_capacity += storage_capacity
                if storage_used is not None:
                    total_storage_used += storage_used

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
                    'storage_used': self._format_memory(storage_used) if storage_used is not None else None,
                    'conditions': conditions,
                    'pods_count': pods_per_node.get(node_name, 0)
                }
                node_metrics_data.append(node_data)

            # Calculate usage percentages
            cpu_usage_percent = None
            memory_usage_percent = None
            storage_usage_percent = None
            if self.metrics_available and total_cpu_allocatable > 0:
                cpu_usage_percent = round((total_cpu_usage / total_cpu_allocatable) * 100, 1)
            if self.metrics_available and total_memory_allocatable > 0:
                memory_usage_percent = round((total_memory_usage / total_memory_allocatable) * 100, 1)
            if total_storage_capacity > 0 and total_storage_used > 0:
                storage_usage_percent = round((total_storage_used / total_storage_capacity) * 100, 1)

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
                'total_storage_capacity': self._format_memory(total_storage_capacity) if total_storage_capacity else None,
                'total_storage_used': self._format_memory(total_storage_used) if total_storage_used else None,
                'storage_usage_percent': storage_usage_percent,
                'total_pods': total_pods,
                'unassigned_pods': unassigned_pods,
                'pods': pods_list,
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
                'total_storage_capacity': None,
                'total_storage_used': None,
                'storage_usage_percent': None,
                'total_pods': 0,
                'unassigned_pods': 0,
                'pods': [],
                'metrics_available': False,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
