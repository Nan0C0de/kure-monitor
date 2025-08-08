import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
import json

from backend_client import BackendClient
from data_collector import DataCollector
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PodMonitor:
    def __init__(self):
        self.config = Config()
        self.backend_client = BackendClient(self.config.backend_url)
        self.data_collector = DataCollector()

        # Track pods we've already reported to avoid spam
        self.reported_pods: Dict[str, datetime] = {}

        # Initialize Kubernetes client
        try:
            config.load_incluster_config()  # For running in cluster
            self.cluster_name = self._get_cluster_name_from_env()
        except:
            config.load_kube_config()  # For local development
            self.cluster_name = self._get_cluster_name_from_config()

        self.v1 = client.CoreV1Api()

    def _get_cluster_name_from_env(self):
        """Get cluster name from environment variables (in-cluster)"""
        import os
        # Try to get from env var first, then try to detect kind cluster
        cluster_name = os.environ.get('CLUSTER_NAME')
        if cluster_name:
            return cluster_name
        
        # Try to detect if we're in a kind cluster by checking hostname patterns
        try:
            hostname = os.environ.get('HOSTNAME', '')
            if 'kind' in hostname:
                return 'kind-kure'
        except:
            pass
            
        return 'k8s-cluster'

    def _get_cluster_name_from_config(self):
        """Get cluster name from kubectl config (local development)"""
        try:
            contexts, current_context = config.list_kube_config_contexts()
            if current_context and 'cluster' in current_context['context']:
                return current_context['context']['cluster']
            elif current_context:
                return current_context['name']
            return 'k8s-cluster'
        except Exception as e:
            logger.warning(f"Could not get cluster name from config: {e}")
            return 'k8s-cluster'

    async def start_monitoring(self):
        """Start monitoring pods for failures"""
        logger.info(f"Starting pod monitoring for cluster: {self.cluster_name}")
        
        # Report cluster name to backend
        await self.backend_client.report_cluster_info(self.cluster_name)

        while True:
            try:
                await self._check_failed_pods()
                await asyncio.sleep(self.config.check_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)

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
        """Check if pod is in a failed state"""
        if not pod.status.container_statuses:
            return False

        failed_states = [
            "ImagePullBackOff",
            "ErrImagePull",
            "CrashLoopBackOff",
            "Error",
            "CreateContainerConfigError",
            "InvalidImageName",
        ]

        # Check if pod is pending for too long
        if pod.status.phase == "Pending":
            creation_time = pod.metadata.creation_timestamp
            if datetime.now(creation_time.tzinfo) - creation_time > timedelta(
                minutes=5
            ):
                return True

        # Check container states
        for container_status in pod.status.container_statuses:
            if container_status.state.waiting:
                reason = container_status.state.waiting.reason
                if reason in failed_states:
                    return True

        return False

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
