"""In-memory store for pod metrics history using circular buffers"""

import logging
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

MAX_HISTORY_POINTS = 15  # Keep last 15 data points (~15 minutes at 1min intervals)


def format_cpu(millicores: Optional[int]) -> Optional[str]:
    """Format CPU millicores to human-readable string"""
    if millicores is None:
        return None
    if millicores >= 1000:
        return f"{millicores / 1000:.1f} cores"
    return f"{millicores}m"


def format_memory(bytes_val: Optional[int]) -> Optional[str]:
    """Format bytes to human-readable string"""
    if bytes_val is None:
        return None
    if bytes_val >= 1024 ** 3:
        return f"{bytes_val / (1024 ** 3):.1f} Gi"
    elif bytes_val >= 1024 ** 2:
        return f"{bytes_val / (1024 ** 2):.1f} Mi"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.1f} Ki"
    return f"{bytes_val} B"


class MetricsHistoryStore:
    """In-memory store for pod metrics history using circular buffers"""

    def __init__(self, max_points: int = MAX_HISTORY_POINTS):
        self.max_points = max_points
        self._pod_history: Dict[str, deque] = {}
        self._lock = Lock()

    def _get_key(self, namespace: str, name: str) -> str:
        return f"{namespace}/{name}"

    def add_pod_metrics(
        self,
        namespace: str,
        name: str,
        cpu_millicores: Optional[int],
        memory_bytes: Optional[int],
        timestamp: str
    ):
        """Add a metrics point for a pod"""
        key = self._get_key(namespace, name)

        with self._lock:
            if key not in self._pod_history:
                self._pod_history[key] = deque(maxlen=self.max_points)

            self._pod_history[key].append({
                'timestamp': timestamp,
                'cpu_millicores': cpu_millicores,
                'memory_bytes': memory_bytes
            })

    def get_pod_history(self, namespace: str, name: str) -> List[dict]:
        """Get metrics history for a pod"""
        key = self._get_key(namespace, name)

        with self._lock:
            if key not in self._pod_history:
                return []
            return list(self._pod_history[key])

    def update_from_cluster_metrics(self, cluster_metrics: dict):
        """Update history from incoming cluster metrics"""
        timestamp = cluster_metrics.get('timestamp', datetime.utcnow().isoformat() + 'Z')
        pods = cluster_metrics.get('pods', [])

        for pod in pods:
            namespace = pod.get('namespace')
            name = pod.get('name')
            if namespace and name:
                self.add_pod_metrics(
                    namespace=namespace,
                    name=name,
                    cpu_millicores=pod.get('cpu_usage'),
                    memory_bytes=pod.get('memory_usage'),
                    timestamp=timestamp
                )

    def cleanup_stale_pods(self, active_pods: set):
        """Remove history for pods that no longer exist"""
        with self._lock:
            stale_keys = [k for k in self._pod_history.keys() if k not in active_pods]
            for key in stale_keys:
                del self._pod_history[key]
            if stale_keys:
                logger.debug(f"Cleaned up metrics history for {len(stale_keys)} stale pods")

    def get_all_pod_keys(self) -> List[str]:
        """Get all pod keys currently in the history store"""
        with self._lock:
            return list(self._pod_history.keys())


# Global instance for the application
metrics_history_store = MetricsHistoryStore()
