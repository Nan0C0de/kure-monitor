from fastapi import APIRouter, HTTPException
import logging
from typing import Optional

from models.models import ClusterMetrics, PodMetricsHistory, PodMetricsPoint
from services.metrics_history import metrics_history_store, format_cpu, format_memory
from services.prometheus_metrics import SECURITY_SCAN_DURATION_SECONDS
from .deps import RouterDeps

logger = logging.getLogger(__name__)

# Store latest cluster metrics in memory (no database needed for current values)
latest_cluster_metrics: Optional[dict] = None


def create_metrics_router(deps: RouterDeps) -> APIRouter:
    """Cluster metrics, scan duration, pod metrics history."""
    router = APIRouter()
    websocket_manager = deps.websocket_manager

    @router.post("/metrics/cluster")
    async def report_cluster_metrics(metrics: ClusterMetrics):
        """Receive cluster metrics from agent"""
        global latest_cluster_metrics
        try:
            latest_cluster_metrics = metrics.dict()
            logger.debug(f"Received cluster metrics: {metrics.node_count} nodes")

            metrics_history_store.update_from_cluster_metrics(latest_cluster_metrics)
            await websocket_manager.broadcast_cluster_metrics(metrics)

            return {"message": "Metrics received"}
        except Exception as e:
            logger.error(f"Error processing cluster metrics: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/metrics/security-scan-duration")
    async def report_security_scan_duration(data: dict):
        """Receive security scan duration from scanner for Prometheus metrics"""
        duration = data.get("duration_seconds")
        if duration is not None:
            SECURITY_SCAN_DURATION_SECONDS.set(float(duration))
            logger.info(f"Security scan duration: {duration:.1f}s")
            return {"message": "Scan duration recorded"}
        raise HTTPException(status_code=400, detail="duration_seconds is required")

    @router.get("/metrics/cluster")
    async def get_cluster_metrics():
        """Get latest cluster metrics"""
        if latest_cluster_metrics:
            return latest_cluster_metrics
        else:
            return {"message": "No metrics available yet", "metrics_available": False}

    @router.get("/metrics/pods/{namespace}/{pod_name}/history", response_model=PodMetricsHistory)
    async def get_pod_metrics_history(namespace: str, pod_name: str):
        """Get metrics history for a specific pod"""
        history = metrics_history_store.get_pod_history(namespace, pod_name)

        if not history:
            return PodMetricsHistory(
                name=pod_name,
                namespace=namespace,
                current_cpu=None,
                current_memory=None,
                history=[]
            )

        formatted_history = []
        for point in history:
            formatted_history.append(PodMetricsPoint(
                timestamp=point['timestamp'],
                cpu_millicores=point['cpu_millicores'],
                memory_bytes=point['memory_bytes'],
                cpu_formatted=format_cpu(point['cpu_millicores']),
                memory_formatted=format_memory(point['memory_bytes'])
            ))

        latest = history[-1] if history else {}

        return PodMetricsHistory(
            name=pod_name,
            namespace=namespace,
            current_cpu=format_cpu(latest.get('cpu_millicores')),
            current_memory=format_memory(latest.get('memory_bytes')),
            history=formatted_history
        )

    return router
