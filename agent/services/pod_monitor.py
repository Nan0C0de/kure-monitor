import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
import json

from clients.backend_client import BackendClient
from clients.websocket_client import WebSocketClient
from services.data_collector import DataCollector
from services.metrics_collector import MetricsCollector
from config.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PodMonitor:
    # System namespaces that are always excluded
    SYSTEM_NAMESPACES = ["kube-system", "kube-public", "kube-node-lease", "local-path-storage", "kure-system"]

    def __init__(self):
        self.config = Config()
        self.backend_client = BackendClient(self.config.backend_url)
        self.websocket_client = WebSocketClient(self.config.backend_url)
        self.data_collector = DataCollector()

        # Track pods we've already reported to avoid spam
        self.reported_pods: Dict[str, datetime] = {}

        # Cache for excluded namespaces from admin settings (for security scan only, not used here anymore)
        self.excluded_namespaces: List[str] = []
        self.excluded_namespaces_last_refresh: Optional[datetime] = None
        self.excluded_namespaces_refresh_interval = timedelta(minutes=1)

        # Cache for excluded pods from admin settings (for pod monitoring exclusions - by pod name only)
        self.excluded_pods: List[str] = []  # List of pod names
        self.excluded_pods_last_refresh: Optional[datetime] = None
        self.excluded_pods_refresh_interval = timedelta(minutes=1)

        # Metrics collection interval (default 30 seconds)
        self.metrics_interval = getattr(self.config, 'metrics_interval', 30)

        # Initialize Kubernetes client
        try:
            config.load_incluster_config()  # For running in cluster
        except Exception:
            config.load_kube_config()  # For local development

        self.v1 = client.CoreV1Api()

        # Initialize metrics collector
        self.metrics_collector = MetricsCollector(self.v1)

    async def _refresh_excluded_namespaces(self):
        """Refresh the excluded namespaces cache from backend (kept for compatibility, not used for pod monitoring)"""
        now = datetime.now()
        if (self.excluded_namespaces_last_refresh is None or
                now - self.excluded_namespaces_last_refresh > self.excluded_namespaces_refresh_interval):
            try:
                self.excluded_namespaces = await self.backend_client.get_excluded_namespaces()
                self.excluded_namespaces_last_refresh = now
                if self.excluded_namespaces:
                    logger.debug(f"Refreshed excluded namespaces: {self.excluded_namespaces}")
            except Exception as e:
                logger.warning(f"Failed to refresh excluded namespaces: {e}")

    async def _refresh_excluded_pods(self):
        """Refresh the excluded pods cache from backend"""
        now = datetime.now()
        if (self.excluded_pods_last_refresh is None or
                now - self.excluded_pods_last_refresh > self.excluded_pods_refresh_interval):
            try:
                self.excluded_pods = await self.backend_client.get_excluded_pods()
                self.excluded_pods_last_refresh = now
                if self.excluded_pods:
                    logger.info(f"Refreshed excluded pods: {self.excluded_pods}")
            except Exception as e:
                logger.warning(f"Failed to refresh excluded pods: {e}")

    def _is_namespace_excluded(self, namespace: str) -> bool:
        """Check if a namespace is a system namespace (excluded from scanning)"""
        # Only check system namespaces - admin namespace exclusions are for security scan only
        if namespace in self.SYSTEM_NAMESPACES:
            return True
        return False

    def _is_pod_excluded(self, pod_name: str) -> bool:
        """Check if a specific pod is excluded from pod monitoring (by name only)"""
        return pod_name in self.excluded_pods

    async def _handle_namespace_change(self, namespace: str, action: str):
        """Handle real-time namespace exclusion changes from WebSocket (for security scan only now)"""
        # Namespace exclusions are now only for security scan, not pod monitoring
        # Keep this handler for potential future use or logging
        logger.info(f"Namespace exclusion change received (security scan only): {namespace} -> {action}")

    async def _handle_pod_exclusion_change(self, pod_name: str, action: str):
        """Handle real-time pod exclusion changes from WebSocket"""
        try:
            # Refresh excluded pods immediately
            self.excluded_pods_last_refresh = None
            await self._refresh_excluded_pods()

            if action == "included":
                # Pod was included (removed from exclusion) - clear cache for all pods with this name
                pods_to_clear = [
                    pod_key for pod_key in self.reported_pods.keys()
                    if pod_key.endswith(f"/{pod_name}")
                ]
                for pod_key in pods_to_clear:
                    del self.reported_pods[pod_key]
                    logger.info(f"Cleared cache for pod {pod_key} (pod included)")
            elif action == "excluded":
                # Pod was excluded - clear from reported cache
                pods_to_clear = [
                    pod_key for pod_key in self.reported_pods.keys()
                    if pod_key.endswith(f"/{pod_name}")
                ]
                for pod_key in pods_to_clear:
                    del self.reported_pods[pod_key]
                logger.info(f"Pod '{pod_name}' excluded from monitoring")
        except Exception as e:
            logger.error(f"Error handling pod exclusion change: {e}")

    async def _monitoring_loop(self):
        """Main monitoring loop for checking failed pods"""
        while True:
            try:
                # Refresh excluded pods periodically (namespace exclusions are for security scan only)
                await self._refresh_excluded_pods()
                await self._check_failed_pods()
                await asyncio.sleep(self.config.check_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)

    async def _metrics_loop(self):
        """Metrics collection loop for sending cluster metrics to backend"""
        # Check if metrics-server is available on startup
        await self.metrics_collector.check_metrics_server()

        while True:
            try:
                metrics = await self.metrics_collector.collect_cluster_metrics()
                await self.backend_client.report_cluster_metrics(metrics)
                await asyncio.sleep(self.metrics_interval)
            except Exception as e:
                logger.error(f"Error in metrics loop: {e}")
                await asyncio.sleep(self.metrics_interval)

    async def start_monitoring(self):
        """Start monitoring pods for failures"""
        logger.info("Starting pod monitoring")

        # Initial refresh of excluded pods (namespace exclusions are for security scan only)
        await self._refresh_excluded_pods()

        # Set up WebSocket client for real-time exclusion changes
        self.websocket_client.set_namespace_change_handler(self._handle_namespace_change)
        self.websocket_client.set_pod_exclusion_change_handler(self._handle_pod_exclusion_change)

        # Run monitoring loop, metrics loop (if enabled), and WebSocket client concurrently
        tasks = [
            asyncio.create_task(self._monitoring_loop()),
            asyncio.create_task(self.websocket_client.connect()),
        ]

        # Only start metrics collection if enabled
        if self.config.cluster_metrics_enabled:
            logger.info("Cluster metrics collection enabled")
            tasks.append(asyncio.create_task(self._metrics_loop()))
        else:
            logger.info("Cluster metrics collection disabled")

        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await self.websocket_client.disconnect()

    async def _check_failed_pods(self):
        """Check for failed pods across all namespaces"""
        try:
            pods = self.v1.list_pod_for_all_namespaces()
            
            # Get list of currently existing pods
            current_pods = set()
            for pod in pods.items:
                pod_key = f"{pod.metadata.namespace}/{pod.metadata.name}"
                current_pods.add(pod_key)
                
                if self._is_pod_failed(pod) and self._should_report_pod(pod):
                    await self._handle_failed_pod(pod)
            
            # Clean up pods that no longer exist
            await self._cleanup_deleted_pods(current_pods)

        except ApiException as e:
            logger.error(f"Kubernetes API error: {e}")

    def _is_pod_failed(self, pod) -> bool:
        """Check if pod is not in ready/healthy state"""
        # Skip system namespaces
        namespace = pod.metadata.namespace
        pod_name = pod.metadata.name
        if self._is_namespace_excluded(namespace):
            return False

        # Skip excluded pods (admin-configured pod monitoring exclusions - by name only)
        if self._is_pod_excluded(pod_name):
            return False

        # Failed phase is obviously a failure
        if pod.status.phase == "Failed":
            return True
            
        # Succeeded phase is for completed jobs - not a failure
        if pod.status.phase == "Succeeded":
            return False
            
        # Pending phase indicates the pod is not ready
        if pod.status.phase == "Pending":
            return True
            
        # For Running phase, only report failures for containers that are actually failing
        if pod.status.phase == "Running":
            # If no container statuses yet, pod might still be starting - not necessarily failed
            if not pod.status.container_statuses:
                return False
                
            # Check for actual container failures (not just "not ready")
            for container_status in pod.status.container_statuses:
                # Container terminated with failure (not due to completion)
                if (container_status.state.terminated and 
                    container_status.state.terminated.reason not in ["Completed"] and
                    container_status.state.terminated.exit_code != 0):
                    return True
                    
                # Container in crash loop or image pull issues
                if container_status.state.waiting:
                    waiting_reason = container_status.state.waiting.reason
                    # Only report actual failures, not transitional states
                    if waiting_reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", 
                                         "InvalidImageName", "ErrImageNeverPull", "CreateContainerError"]:
                        return True
            
            # Pod is running and containers are healthy or in normal transitional states
            return False
            
        # Any other phase (shouldn't normally happen) - consider as failure
        return True

    def _should_report_pod(self, pod) -> bool:
        """Check if we should report this pod (avoid spam)"""
        pod_key = f"{pod.metadata.namespace}/{pod.metadata.name}"

        # Don't report if we reported recently (within last 10 minutes)
        if pod_key in self.reported_pods:
            last_reported = self.reported_pods[pod_key]
            if datetime.now() - last_reported < timedelta(minutes=10):
                return False

        return True

    async def _handle_failed_pod(self, pod):
        """Handle a failed pod by collecting data and sending to backend"""
        pod_key = f"{pod.metadata.namespace}/{pod.metadata.name}"
        
        try:
            logger.info(f"Processing failed pod: {pod_key}")
            pod_data = await self.data_collector.collect_pod_data(pod, self.v1)

            # Send to backend
            success = await self.backend_client.report_failed_pod(pod_data)
            
            if success:
                # Mark as reported only if successful
                self.reported_pods[pod_key] = datetime.now()
                logger.info(f"Successfully reported failed pod: {pod_key}")
            else:
                # Log failure but don't mark as reported so we can retry later
                logger.warning(f"Failed to report pod {pod_key} to backend, will retry later")

        except Exception as e:
            logger.error(f"Error handling failed pod {pod_key}: {e}")
            logger.error(f"Error details: {e.__class__.__name__}: {str(e)}")

    async def _cleanup_deleted_pods(self, current_pods: set):
        """Clean up pods that no longer exist in Kubernetes"""
        try:
            # Clean up reported pods tracking
            deleted_pods = []
            for pod_key in list(self.reported_pods.keys()):
                if pod_key not in current_pods:
                    deleted_pods.append(pod_key)
            
            for pod_key in deleted_pods:
                del self.reported_pods[pod_key]
                logger.info(f"Cleaned up tracking for deleted pod: {pod_key}")
                
                # Notify backend to dismiss the pod
                namespace, pod_name = pod_key.split('/', 1)
                await self.backend_client.dismiss_deleted_pod(namespace, pod_name)
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
