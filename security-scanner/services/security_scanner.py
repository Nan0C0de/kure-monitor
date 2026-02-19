import asyncio
import logging
import os
import time
from typing import Set, Tuple

from kubernetes import client, config

from services.backend_client import BackendClient
from services.websocket_client import WebSocketClient
from services.scanner_base import get_resource_manifest
from services.exclusion_manager import ExclusionManager
from services.watch_manager import WatchManager
from services.scanners import PodScanner, ResourceScanner

logger = logging.getLogger(__name__)


class SecurityScanner:
    def __init__(self):
        self.backend_url = os.getenv("BACKEND_URL", "http://kure-monitor-backend:8000")
        self.backend_client = BackendClient(self.backend_url)
        self.websocket_client = WebSocketClient(self.backend_url)
        self.v1 = None
        self.apps_v1 = None
        self.rbac_v1 = None
        self.networking_v1 = None
        self.batch_v1 = None
        self.policy_v1 = None
        # Track resources that have findings: Set of (resource_type, namespace, resource_name)
        self.tracked_resources: Set[Tuple[str, str, str]] = set()
        self._lock = asyncio.Lock()
        # Current resource context for automatic manifest inclusion
        self._current_resource_obj = None
        self._current_resource_api_version = None
        self._current_resource_kind = None
        # Composed helpers
        self.exclusion_mgr = ExclusionManager(self)
        self.watch_mgr = WatchManager(self)
        self.pod_scanner = PodScanner(self)
        self.resource_scanner = ResourceScanner(self)

    def _init_kubernetes_client(self):
        """Initialize Kubernetes client"""
        try:
            config.load_incluster_config()
            logger.info("Using in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Using local kubeconfig")
            except config.ConfigException:
                logger.error("Could not configure Kubernetes client")
                raise

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.rbac_v1 = client.RbacAuthorizationV1Api()
        self.networking_v1 = client.NetworkingV1Api()
        self.batch_v1 = client.BatchV1Api()
        self.policy_v1 = client.PolicyV1Api()

    def _set_resource_context(self, resource_obj, api_version: str, kind: str):
        """Set the current resource context for automatic manifest inclusion in report_finding"""
        self._current_resource_obj = resource_obj
        self._current_resource_api_version = api_version
        self._current_resource_kind = kind

    def _clear_resource_context(self):
        """Clear the current resource context"""
        self._current_resource_obj = None
        self._current_resource_api_version = None
        self._current_resource_kind = None

    async def report_finding(self, finding_data: dict):
        """Report a security finding to the backend and track the resource"""
        title = finding_data.get("title", "")
        namespace = finding_data.get("namespace", "")
        if title and self.exclusion_mgr.is_rule_excluded(title, namespace):
            logger.debug(f"Skipping excluded rule: {title} (namespace: {namespace})")
            return

        if 'manifest' not in finding_data and self._current_resource_obj:
            finding_data['manifest'] = get_resource_manifest(
                self._current_resource_obj,
                self._current_resource_api_version,
                self._current_resource_kind
            )

        resource_type = finding_data.get("resource_type", "")
        resource_name = finding_data.get("resource_name", "")
        if resource_type and namespace and resource_name:
            self.tracked_resources.add((resource_type, namespace, resource_name))

        await self.backend_client.report_security_finding(finding_data)

    async def _wait_for_backend(self, max_retries: int = 30, retry_interval: float = 2.0):
        """Wait for backend to be ready before starting scan"""
        for attempt in range(max_retries):
            try:
                success = await self.exclusion_mgr.refresh_excluded_namespaces(force=True)
                if success:
                    await self.exclusion_mgr.refresh_excluded_rules(force=True)
                    logger.info("Backend is ready, excluded namespaces and rules loaded successfully")
                    return True
            except Exception as e:
                logger.warning(f"Backend not ready (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_interval}s before retrying...")
                await asyncio.sleep(retry_interval)

        logger.error(f"Backend not ready after {max_retries} attempts")
        return False

    async def scan_cluster(self):
        """Run all security checks"""
        start_time = time.monotonic()

        await self.exclusion_mgr.refresh_excluded_namespaces()
        await self.exclusion_mgr.refresh_excluded_rules()

        await self.pod_scanner.scan_pods()
        await self.resource_scanner.scan_deployments()
        await self.resource_scanner.scan_services()
        await self.resource_scanner.scan_rbac()
        await self.resource_scanner.scan_network_policies()
        await self.pod_scanner.scan_service_accounts()
        await self.resource_scanner.scan_pod_security_admission()
        await self.resource_scanner.scan_ingresses()
        await self.pod_scanner.scan_seccomp_profiles()
        await self.resource_scanner.scan_cluster_role_bindings()
        await self.resource_scanner.scan_pod_disruption_budgets()
        await self.resource_scanner.scan_resource_quotas()
        await self.resource_scanner.scan_configmaps()
        await self.resource_scanner.scan_cronjobs()
        await self.resource_scanner.scan_persistent_volumes()

        duration = time.monotonic() - start_time
        logger.info(f"Security scan completed in {duration:.1f}s")
        await self.backend_client.report_scan_duration(duration)

    async def start_scanning(self):
        """Start real-time security scanning with Kubernetes watches"""
        logger.info("Starting real-time security scanner")
        logger.info(f"Backend URL: {self.backend_url}")

        self._init_kubernetes_client()

        logger.info("Waiting for backend to be ready...")
        backend_ready = await self._wait_for_backend()
        if not backend_ready:
            logger.warning("Starting scan without confirmed excluded namespaces - some excluded namespaces may be scanned")

        await self.backend_client.clear_security_findings()

        self.websocket_client.set_namespace_change_handler(self.exclusion_mgr.handle_namespace_change)
        self.websocket_client.set_rule_change_handler(self.exclusion_mgr.handle_rule_change)
        self.websocket_client.set_registry_change_handler(self.exclusion_mgr.handle_registry_change)

        logger.info("Running initial security scan...")
        await self.scan_cluster()
        logger.info("Initial security scan completed - switching to real-time mode")

        rs = self.resource_scanner
        watch_tasks = [
            asyncio.create_task(self.watch_mgr.watch_pods()),
            asyncio.create_task(self.watch_mgr.create_namespaced_watch(
                "Deployment", self.apps_v1.list_deployment_for_all_namespaces,
                "deploy-watch", rs.scan_single_deployment)),
            asyncio.create_task(self.watch_mgr.create_namespaced_watch(
                "Service", self.v1.list_service_for_all_namespaces,
                "svc-watch", rs.scan_single_service)),
            asyncio.create_task(self.watch_mgr.create_cluster_watch(
                "ClusterRole", self.rbac_v1.list_cluster_role,
                "cr-watch", rs.scan_single_cluster_role, skip_system_prefix=True)),
            asyncio.create_task(self.watch_mgr.create_namespaced_watch(
                "Role", self.rbac_v1.list_role_for_all_namespaces,
                "role-watch", rs.scan_single_role)),
            asyncio.create_task(self.watch_mgr.create_deletion_only_watch(
                "Namespace", self.v1.list_namespace, "ns-watch", namespaced=False)),
            asyncio.create_task(self.watch_mgr.create_deletion_only_watch(
                "DaemonSet", self.apps_v1.list_daemon_set_for_all_namespaces, "ds-watch")),
            asyncio.create_task(self.watch_mgr.create_deletion_only_watch(
                "StatefulSet", self.apps_v1.list_stateful_set_for_all_namespaces, "sts-watch")),
            asyncio.create_task(self.watch_mgr.create_namespaced_watch(
                "Ingress", self.networking_v1.list_ingress_for_all_namespaces,
                "ingress-watch", rs.scan_single_ingress)),
            asyncio.create_task(self.watch_mgr.create_namespaced_watch(
                "CronJob", self.batch_v1.list_cron_job_for_all_namespaces,
                "cj-watch", rs.scan_single_cronjob, handle_403=True)),
            asyncio.create_task(self.websocket_client.connect()),
        ]

        try:
            await asyncio.gather(*watch_tasks)
        finally:
            for task in watch_tasks:
                task.cancel()
            await self.websocket_client.disconnect()
