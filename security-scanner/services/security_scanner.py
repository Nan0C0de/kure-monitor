import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Set, Tuple, List, Optional, Dict
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from services.backend_client import BackendClient
from services.websocket_client import WebSocketClient

logger = logging.getLogger(__name__)


class SecurityScanner:
    # Dangerous capabilities that should never be added
    DANGEROUS_CAPABILITIES = [
        'SYS_ADMIN',      # Full admin access
        'NET_RAW',        # Packet spoofing/sniffing
        'SYS_PTRACE',     # Process tracing/debugging
        'SYS_MODULE',     # Load kernel modules
        'DAC_READ_SEARCH', # Bypass file read permissions
        'NET_ADMIN',      # Network configuration
        'SYS_RAWIO',      # Raw I/O operations
        'SYS_BOOT',       # Reboot system
        'SYS_TIME',       # Modify system clock
        'MKNOD',          # Create device files
        'SETUID',         # Set arbitrary UIDs
        'SETGID',         # Set arbitrary GIDs
    ]

    # Capabilities allowed by Pod Security Standards Restricted policy
    ALLOWED_CAPABILITIES = ['NET_BIND_SERVICE']

    # System namespaces to skip
    SYSTEM_NAMESPACES = ['kube-system', 'kube-public', 'kube-node-lease', 'kube-flannel']

    # Trusted container registries (can be customized via config)
    TRUSTED_REGISTRIES = [
        'docker.io',
        'gcr.io',
        'ghcr.io',
        'quay.io',
        'registry.k8s.io',
        'mcr.microsoft.com',
        'public.ecr.aws',
    ]

    # Large emptyDir size limit threshold (in bytes) - 10GB
    LARGE_EMPTYDIR_THRESHOLD = 10 * 1024 * 1024 * 1024

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
        # Lock for thread-safe access to tracked_resources
        self._lock = asyncio.Lock()
        # Cache for admin-configured excluded namespaces
        self.excluded_namespaces: List[str] = []
        self.excluded_namespaces_last_refresh: Optional[datetime] = None
        self.excluded_namespaces_refresh_interval = timedelta(minutes=1)
        # Cache for admin-configured excluded rules
        self.globally_excluded_rules: Set[str] = set()
        self.namespace_excluded_rules: Dict[str, Set[str]] = {}
        self.excluded_rules_last_refresh: Optional[datetime] = None
        self.excluded_rules_refresh_interval = timedelta(minutes=1)

    def _init_kubernetes_client(self):
        """Initialize Kubernetes client"""
        try:
            # Try in-cluster config first
            config.load_incluster_config()
            logger.info("Using in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                # Fall back to local kubeconfig
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

    async def _refresh_excluded_namespaces(self, force: bool = False) -> bool:
        """Refresh the excluded namespaces cache from backend

        Args:
            force: If True, refresh regardless of cache age

        Returns:
            True if refresh was successful, False otherwise
        """
        now = datetime.utcnow()
        if (force or self.excluded_namespaces_last_refresh is None or
                now - self.excluded_namespaces_last_refresh > self.excluded_namespaces_refresh_interval):
            try:
                namespaces = await self.backend_client.get_excluded_namespaces()
                # Only update if we got a successful response (not an empty error response)
                self.excluded_namespaces = namespaces
                self.excluded_namespaces_last_refresh = now
                if self.excluded_namespaces:
                    logger.info(f"Refreshed excluded namespaces: {self.excluded_namespaces}")
                else:
                    logger.info("No excluded namespaces configured")
                return True
            except Exception as e:
                logger.warning(f"Failed to refresh excluded namespaces: {e}")
                return False
        return True

    def _is_namespace_excluded(self, namespace: str) -> bool:
        """Check if a namespace is excluded from scanning"""
        # Check system namespaces
        if namespace in self.SYSTEM_NAMESPACES:
            return True
        # Check admin-configured excluded namespaces
        if namespace in self.excluded_namespaces:
            return True
        return False

    async def _refresh_excluded_rules(self, force: bool = False) -> bool:
        """Refresh the excluded rules cache from backend

        Args:
            force: If True, refresh regardless of cache age

        Returns:
            True if refresh was successful, False otherwise
        """
        now = datetime.utcnow()
        if (force or self.excluded_rules_last_refresh is None or
                now - self.excluded_rules_last_refresh > self.excluded_rules_refresh_interval):
            try:
                rules = await self.backend_client.get_excluded_rules()
                globally_excluded = set()
                namespace_excluded = {}
                for rule in rules:
                    rule_title = rule.get('rule_title')
                    namespace = rule.get('namespace')
                    if not rule_title:
                        continue
                    if namespace is None:
                        globally_excluded.add(rule_title)
                    else:
                        if namespace not in namespace_excluded:
                            namespace_excluded[namespace] = set()
                        namespace_excluded[namespace].add(rule_title)
                self.globally_excluded_rules = globally_excluded
                self.namespace_excluded_rules = namespace_excluded
                self.excluded_rules_last_refresh = now
                if globally_excluded or namespace_excluded:
                    logger.info(f"Refreshed excluded rules: global={globally_excluded}, namespaced={namespace_excluded}")
                else:
                    logger.info("No excluded rules configured")
                return True
            except Exception as e:
                logger.warning(f"Failed to refresh excluded rules: {e}")
                return False
        return True

    def _is_rule_excluded(self, title: str, namespace: str = '') -> bool:
        """Check if a rule title is excluded (globally or for given namespace).
        Supports base-name matching: excluding 'Privilege escalation allowed' also
        matches 'Privilege escalation allowed: container-name'."""
        # Check global exclusions (exact match)
        if title in self.globally_excluded_rules:
            return True
        # Check global exclusions (base-name prefix match)
        if ': ' in title:
            base_name = title.split(': ', 1)[0]
            if base_name in self.globally_excluded_rules:
                return True
        # Check namespace exclusions
        if namespace and namespace in self.namespace_excluded_rules:
            ns_rules = self.namespace_excluded_rules[namespace]
            if title in ns_rules:
                return True
            if ': ' in title:
                base_name = title.split(': ', 1)[0]
                if base_name in ns_rules:
                    return True
        return False

    async def _handle_rule_change(self, rule_title: str, action: str, namespace: str = None):
        """Handle real-time rule exclusion changes from WebSocket"""
        try:
            await self._refresh_excluded_rules(force=True)

            if action == "included":
                if namespace:
                    if not self._is_rule_excluded(rule_title, namespace):
                        logger.info(f"Rule '{rule_title}' included for namespace '{namespace}' - rescanning namespace...")
                        await self._scan_namespace_pods(namespace)
                else:
                    if not self._is_rule_excluded(rule_title):
                        logger.info(f"Rule '{rule_title}' included globally - rescanning cluster...")
                        await self.scan_cluster()
            elif action == "excluded":
                scope = f"for namespace '{namespace}'" if namespace else "globally"
                logger.info(f"Rule '{rule_title}' excluded {scope} - exclusion list updated")
        except Exception as e:
            logger.error(f"Error handling rule change: {e}")

    async def _handle_namespace_change(self, namespace: str, action: str):
        """Handle real-time namespace exclusion changes from WebSocket"""
        try:
            # Refresh excluded namespaces immediately (force refresh)
            await self._refresh_excluded_namespaces(force=True)

            if action == "included":
                # Namespace was included (removed from exclusion) - rescan it
                if not self._is_namespace_excluded(namespace):
                    logger.info(f"Namespace '{namespace}' included - rescanning...")
                    await self._scan_namespace_pods(namespace)
            elif action == "excluded":
                # Namespace was excluded - already handled by backend deleting findings
                logger.info(f"Namespace '{namespace}' excluded - exclusion list updated")
        except Exception as e:
            logger.error(f"Error handling namespace change: {e}")

    async def _scan_namespace_pods(self, namespace: str):
        """Scan all pods in a specific namespace"""
        try:
            pods = self.v1.list_namespaced_pod(namespace)
            for pod in pods.items:
                await self._scan_single_pod(pod)
        except Exception as e:
            logger.error(f"Error scanning namespace {namespace}: {e}")

    async def _wait_for_backend(self, max_retries: int = 30, retry_interval: float = 2.0):
        """Wait for backend to be ready before starting scan

        Args:
            max_retries: Maximum number of retries
            retry_interval: Seconds between retries
        """
        for attempt in range(max_retries):
            try:
                # Try to fetch excluded namespaces as a health check
                success = await self._refresh_excluded_namespaces(force=True)
                if success:
                    await self._refresh_excluded_rules(force=True)
                    logger.info("Backend is ready, excluded namespaces and rules loaded successfully")
                    return True
            except Exception as e:
                logger.warning(f"Backend not ready (attempt {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_interval}s before retrying...")
                await asyncio.sleep(retry_interval)

        logger.error(f"Backend not ready after {max_retries} attempts")
        return False

    async def start_scanning(self):
        """Start real-time security scanning with Kubernetes watches"""
        logger.info("Starting real-time security scanner")
        logger.info(f"Backend URL: {self.backend_url}")

        self._init_kubernetes_client()

        # Wait for backend to be ready and load excluded namespaces
        logger.info("Waiting for backend to be ready...")
        backend_ready = await self._wait_for_backend()
        if not backend_ready:
            logger.warning("Starting scan without confirmed excluded namespaces - some excluded namespaces may be scanned")

        # Clear all findings on startup (after loading exclusions)
        await self.backend_client.clear_security_findings()

        # Set up WebSocket client for real-time exclusion changes
        self.websocket_client.set_namespace_change_handler(self._handle_namespace_change)
        self.websocket_client.set_rule_change_handler(self._handle_rule_change)

        # Run initial scan to populate findings
        logger.info("Running initial security scan...")
        await self.scan_cluster()
        logger.info("Initial security scan completed - switching to real-time mode")

        # Start watches for real-time detection (both additions and deletions)
        watch_tasks = [
            asyncio.create_task(self._watch_pods()),
            asyncio.create_task(self._watch_deployments()),
            asyncio.create_task(self._watch_services()),
            asyncio.create_task(self._watch_cluster_roles()),
            asyncio.create_task(self._watch_roles()),
            asyncio.create_task(self._watch_namespaces()),
            asyncio.create_task(self._watch_daemonsets()),
            asyncio.create_task(self._watch_statefulsets()),
            asyncio.create_task(self._watch_ingresses()),
            asyncio.create_task(self._watch_cronjobs()),
            asyncio.create_task(self.websocket_client.connect()),  # Real-time namespace changes
        ]

        # Wait for watches to run (they run forever until cancelled)
        try:
            await asyncio.gather(*watch_tasks)
        finally:
            # Cancel watch tasks on shutdown
            for task in watch_tasks:
                task.cancel()
            await self.websocket_client.disconnect()

    async def _handle_resource_deletion(self, resource_type: str, namespace: str, resource_name: str):
        """Handle deletion of a resource - remove its findings from backend"""
        resource_key = (resource_type, namespace, resource_name)

        async with self._lock:
            if resource_key in self.tracked_resources:
                self.tracked_resources.discard(resource_key)
                logger.info(f"Resource deleted: {resource_type}/{namespace}/{resource_name} - removing findings")
                await self.backend_client.delete_findings_by_resource(resource_type, namespace, resource_name)

    def _pod_watch_sync(self, callback):
        """Synchronous pod watch that calls callback for each event"""
        import time
        import traceback
        while True:
            try:
                logger.info("Pod watch thread starting stream...")
                w = watch.Watch()
                for event in w.stream(self.v1.list_pod_for_all_namespaces, timeout_seconds=300):
                    try:
                        callback(event)
                    except Exception as cb_err:
                        logger.error(f"Pod watch callback error: {cb_err}")
            except Exception as e:
                logger.error(f"Pod watch stream error: {e}")
                logger.error(traceback.format_exc())
                time.sleep(5)

    async def _watch_pods(self):
        """Watch for pod changes in real-time using thread executor"""
        import threading

        logger.info("_watch_pods async method starting...")
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            logger.debug(f"on_event callback received: {event['type']}")
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        # Start the sync watch in a background thread
        watch_thread = threading.Thread(target=self._pod_watch_sync, args=(on_event,), daemon=True, name="pod-watch-thread")
        watch_thread.start()
        logger.info(f"Pod watch thread started: {watch_thread.name}, alive={watch_thread.is_alive()}")

        logger.info("Pod watch consumer loop starting...")
        while True:
            try:
                event = await event_queue.get()
                pod = event['object']
                namespace = pod.metadata.namespace

                # Refresh excluded namespaces periodically
                await self._refresh_excluded_namespaces()

                if self._is_namespace_excluded(namespace):
                    continue

                if event['type'] == 'DELETED':
                    await self._handle_resource_deletion("Pod", namespace, pod.metadata.name)
                elif event['type'] in ['ADDED', 'MODIFIED']:
                    logger.info(f"Real-time pod event: {event['type']} {namespace}/{pod.metadata.name}")
                    await self._scan_single_pod(pod)
            except Exception as e:
                logger.error(f"Pod watch consumer error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await asyncio.sleep(1)

    def _deployment_watch_sync(self, callback):
        """Synchronous deployment watch"""
        while True:
            try:
                logger.info("Starting deployment watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.apps_v1.list_deployment_for_all_namespaces, timeout_seconds=0):
                    callback(event)
            except Exception as e:
                logger.error(f"Deployment watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_deployments(self):
        """Watch for deployment changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deploy-watch")
        executor.submit(self._deployment_watch_sync, on_event)

        logger.info("Deployment watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    deployment = event['object']
                    namespace = deployment.metadata.namespace
                    if not self._is_namespace_excluded(namespace):
                        await self._handle_resource_deletion("Deployment", namespace, deployment.metadata.name)
            except Exception as e:
                logger.error(f"Deployment watch consumer error: {e}")
                await asyncio.sleep(1)

    def _service_watch_sync(self, callback):
        """Synchronous service watch"""
        while True:
            try:
                logger.info("Starting service watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.v1.list_service_for_all_namespaces, timeout_seconds=0):
                    callback(event)
            except Exception as e:
                logger.error(f"Service watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_services(self):
        """Watch for service changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="svc-watch")
        executor.submit(self._service_watch_sync, on_event)

        logger.info("Service watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    service = event['object']
                    namespace = service.metadata.namespace
                    if not self._is_namespace_excluded(namespace):
                        await self._handle_resource_deletion("Service", namespace, service.metadata.name)
            except Exception as e:
                logger.error(f"Service watch consumer error: {e}")
                await asyncio.sleep(1)

    def _cluster_role_watch_sync(self, callback):
        """Synchronous cluster role watch"""
        while True:
            try:
                logger.info("Starting ClusterRole watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.rbac_v1.list_cluster_role, timeout_seconds=0):
                    callback(event)
            except Exception as e:
                logger.error(f"ClusterRole watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_cluster_roles(self):
        """Watch for ClusterRole changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cr-watch")
        executor.submit(self._cluster_role_watch_sync, on_event)

        logger.info("ClusterRole watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    role = event['object']
                    if not role.metadata.name.startswith('system:'):
                        await self._handle_resource_deletion("ClusterRole", "cluster-wide", role.metadata.name)
            except Exception as e:
                logger.error(f"ClusterRole watch consumer error: {e}")
                await asyncio.sleep(1)

    def _role_watch_sync(self, callback):
        """Synchronous role watch"""
        while True:
            try:
                logger.info("Starting Role watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.rbac_v1.list_role_for_all_namespaces, timeout_seconds=0):
                    callback(event)
            except Exception as e:
                logger.error(f"Role watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_roles(self):
        """Watch for Role changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="role-watch")
        executor.submit(self._role_watch_sync, on_event)

        logger.info("Role watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    role = event['object']
                    namespace = role.metadata.namespace
                    if not self._is_namespace_excluded(namespace):
                        await self._handle_resource_deletion("Role", namespace, role.metadata.name)
            except Exception as e:
                logger.error(f"Role watch consumer error: {e}")
                await asyncio.sleep(1)

    def _namespace_watch_sync(self, callback):
        """Synchronous namespace watch"""
        while True:
            try:
                logger.info("Starting Namespace watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.v1.list_namespace, timeout_seconds=0):
                    callback(event)
            except Exception as e:
                logger.error(f"Namespace watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_namespaces(self):
        """Watch for namespace changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ns-watch")
        executor.submit(self._namespace_watch_sync, on_event)

        logger.info("Namespace watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    ns = event['object']
                    ns_name = ns.metadata.name
                    if not self._is_namespace_excluded(ns_name):
                        await self._handle_resource_deletion("Namespace", ns_name, ns_name)
            except Exception as e:
                logger.error(f"Namespace watch consumer error: {e}")
                await asyncio.sleep(1)

    def _daemonset_watch_sync(self, callback):
        """Synchronous DaemonSet watch"""
        while True:
            try:
                logger.info("Starting DaemonSet watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.apps_v1.list_daemon_set_for_all_namespaces, timeout_seconds=0):
                    callback(event)
            except Exception as e:
                logger.error(f"DaemonSet watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_daemonsets(self):
        """Watch for DaemonSet changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ds-watch")
        executor.submit(self._daemonset_watch_sync, on_event)

        logger.info("DaemonSet watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    ds = event['object']
                    namespace = ds.metadata.namespace
                    if not self._is_namespace_excluded(namespace):
                        await self._handle_resource_deletion("DaemonSet", namespace, ds.metadata.name)
            except Exception as e:
                logger.error(f"DaemonSet watch consumer error: {e}")
                await asyncio.sleep(1)

    def _statefulset_watch_sync(self, callback):
        """Synchronous StatefulSet watch"""
        while True:
            try:
                logger.info("Starting StatefulSet watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.apps_v1.list_stateful_set_for_all_namespaces, timeout_seconds=0):
                    callback(event)
            except Exception as e:
                logger.error(f"StatefulSet watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_statefulsets(self):
        """Watch for StatefulSet changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sts-watch")
        executor.submit(self._statefulset_watch_sync, on_event)

        logger.info("StatefulSet watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    sts = event['object']
                    namespace = sts.metadata.namespace
                    if not self._is_namespace_excluded(namespace):
                        await self._handle_resource_deletion("StatefulSet", namespace, sts.metadata.name)
            except Exception as e:
                logger.error(f"StatefulSet watch consumer error: {e}")
                await asyncio.sleep(1)

    def _ingress_watch_sync(self, callback):
        """Synchronous Ingress watch"""
        while True:
            try:
                logger.info("Starting Ingress watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.networking_v1.list_ingress_for_all_namespaces, timeout_seconds=0):
                    callback(event)
            except Exception as e:
                logger.error(f"Ingress watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_ingresses(self):
        """Watch for Ingress changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingress-watch")
        executor.submit(self._ingress_watch_sync, on_event)

        logger.info("Ingress watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    ingress = event['object']
                    namespace = ingress.metadata.namespace
                    if not self._is_namespace_excluded(namespace):
                        await self._handle_resource_deletion("Ingress", namespace, ingress.metadata.name)
            except Exception as e:
                logger.error(f"Ingress watch consumer error: {e}")
                await asyncio.sleep(1)

    def _cronjob_watch_sync(self, callback):
        """Synchronous CronJob watch"""
        while True:
            try:
                logger.info("Starting CronJob watch (sync thread)")
                w = watch.Watch()
                for event in w.stream(self.batch_v1.list_cron_job_for_all_namespaces, timeout_seconds=0):
                    callback(event)
            except ApiException as e:
                if e.status == 403:
                    logger.warning(f"CronJob watch forbidden (missing RBAC permissions) - disabling CronJob watch")
                    return  # Stop retrying on permission errors
                logger.error(f"CronJob watch API error: {e}, restarting...")
                import time
                time.sleep(5)
            except Exception as e:
                logger.error(f"CronJob watch error: {e}, restarting...")
                import time
                time.sleep(5)

    async def _watch_cronjobs(self):
        """Watch for CronJob changes in real-time"""
        loop = asyncio.get_running_loop()
        event_queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cj-watch")
        executor.submit(self._cronjob_watch_sync, on_event)

        logger.info("CronJob watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    cj = event['object']
                    namespace = cj.metadata.namespace
                    if not self._is_namespace_excluded(namespace):
                        await self._handle_resource_deletion("CronJob", namespace, cj.metadata.name)
            except Exception as e:
                logger.error(f"CronJob watch consumer error: {e}")
                await asyncio.sleep(1)

    async def _scan_single_pod(self, pod):
        """Scan a single pod for security issues (used by real-time watch)"""
        namespace = pod.metadata.namespace
        pod_name = pod.metadata.name
        timestamp = datetime.utcnow().isoformat() + "Z"

        logger.debug(f"Real-time scanning pod: {namespace}/{pod_name}")

        # === Pod-level security checks ===

        if pod.spec.host_network:
            await self.report_finding({
                "resource_type": "Pod",
                "resource_name": pod_name,
                "namespace": namespace,
                "severity": "high",
                "category": "Security",
                "title": "Pod uses host network namespace",
                "description": "Pod is using the host network namespace, which exposes the host's network stack to the container and bypasses network policies.",
                "remediation": "Remove 'hostNetwork: true' unless required for specific use cases like CNI plugins or monitoring agents.",
                "timestamp": timestamp
            })

        if pod.spec.host_pid:
            await self.report_finding({
                "resource_type": "Pod",
                "resource_name": pod_name,
                "namespace": namespace,
                "severity": "high",
                "category": "Security",
                "title": "Pod uses host PID namespace",
                "description": "Pod is using the host PID namespace, which allows viewing and signaling all processes on the host.",
                "remediation": "Remove 'hostPID: true' unless absolutely necessary for debugging or monitoring.",
                "timestamp": timestamp
            })

        if pod.spec.host_ipc:
            await self.report_finding({
                "resource_type": "Pod",
                "resource_name": pod_name,
                "namespace": namespace,
                "severity": "high",
                "category": "Security",
                "title": "Pod uses host IPC namespace",
                "description": "Pod is using the host IPC namespace, which allows reading shared memory with host processes.",
                "remediation": "Remove 'hostIPC: true' from the pod specification.",
                "timestamp": timestamp
            })

        # Check for hostPath volumes
        if pod.spec.volumes:
            for volume in pod.spec.volumes:
                if volume.host_path:
                    severity = "critical" if volume.host_path.path in ['/', '/etc', '/var', '/root', '/home'] else "high"
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": severity,
                        "category": "Security",
                        "title": f"HostPath volume mounted: {volume.host_path.path}",
                        "description": f"Volume '{volume.name}' mounts host path '{volume.host_path.path}'. This provides direct access to the host filesystem and can lead to container escape.",
                        "remediation": "Use persistent volumes, configMaps, secrets, or emptyDir instead of hostPath volumes.",
                        "timestamp": timestamp
                    })

        # === Container-level security checks ===
        all_containers = (pod.spec.containers or []) + (pod.spec.init_containers or [])

        for container in all_containers:
            container_name = container.name
            sec_ctx = container.security_context

            if sec_ctx and sec_ctx.privileged:
                await self.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "critical",
                    "category": "Security",
                    "title": f"Privileged container: {container_name}",
                    "description": f"Container '{container_name}' is running in privileged mode, which grants full access to all host devices and capabilities.",
                    "remediation": "Remove 'privileged: true' from the container's securityContext.",
                    "timestamp": timestamp
                })

            if not sec_ctx or sec_ctx.allow_privilege_escalation is None or sec_ctx.allow_privilege_escalation:
                await self.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "high",
                    "category": "Security",
                    "title": f"Privilege escalation allowed: {container_name}",
                    "description": f"Container '{container_name}' allows privilege escalation via setuid binaries or filesystem capabilities.",
                    "remediation": "Set 'allowPrivilegeEscalation: false' in the container's securityContext.",
                    "timestamp": timestamp
                })

            # Check for dangerous capabilities
            if sec_ctx and sec_ctx.capabilities and sec_ctx.capabilities.add:
                dangerous_caps = [cap for cap in sec_ctx.capabilities.add if cap in self.DANGEROUS_CAPABILITIES]
                if dangerous_caps:
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": f"Dangerous capabilities added: {container_name}",
                        "description": f"Container '{container_name}' adds dangerous capabilities: {', '.join(dangerous_caps)}.",
                        "remediation": "Remove dangerous capabilities from the container.",
                        "timestamp": timestamp
                    })

            # Check for missing capability drop ALL
            caps_dropped_all = (
                sec_ctx and sec_ctx.capabilities and sec_ctx.capabilities.drop and
                ('ALL' in sec_ctx.capabilities.drop or 'all' in sec_ctx.capabilities.drop)
            )
            if not caps_dropped_all:
                await self.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "medium",
                    "category": "Security",
                    "title": f"Capabilities not dropped: {container_name}",
                    "description": f"Container '{container_name}' does not drop all capabilities.",
                    "remediation": "Add 'drop: [\"ALL\"]' to capabilities.",
                    "timestamp": timestamp
                })

            # Check for running as root
            run_as_non_root = sec_ctx and sec_ctx.run_as_non_root
            explicit_root = sec_ctx and sec_ctx.run_as_user == 0
            pod_run_as_non_root = pod.spec.security_context and pod.spec.security_context.run_as_non_root

            if explicit_root:
                await self.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "high",
                    "category": "Security",
                    "title": f"Container runs as root (UID 0): {container_name}",
                    "description": f"Container '{container_name}' explicitly sets runAsUser: 0 (root).",
                    "remediation": "Set 'runAsUser' to a non-zero UID and 'runAsNonRoot: true'.",
                    "timestamp": timestamp
                })
            elif not run_as_non_root and not pod_run_as_non_root:
                await self.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "medium",
                    "category": "Security",
                    "title": f"Container may run as root: {container_name}",
                    "description": f"Container '{container_name}' does not explicitly prevent running as root user.",
                    "remediation": "Set 'runAsNonRoot: true' in the container's securityContext.",
                    "timestamp": timestamp
                })

            # Check for writable root filesystem
            if not sec_ctx or not sec_ctx.read_only_root_filesystem:
                await self.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "medium",
                    "category": "Security",
                    "title": f"Writable root filesystem: {container_name}",
                    "description": f"Container '{container_name}' has a writable root filesystem.",
                    "remediation": "Set 'readOnlyRootFilesystem: true'.",
                    "timestamp": timestamp
                })

            # Check for missing resource limits
            if not container.resources or not container.resources.limits:
                await self.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "medium",
                    "category": "Best Practice",
                    "title": f"Missing resource limits: {container_name}",
                    "description": f"Container '{container_name}' does not have resource limits defined.",
                    "remediation": "Add resource limits (cpu and memory) to the container specification.",
                    "timestamp": timestamp
                })

    async def _track_resource_async(self, resource_type: str, namespace: str, resource_name: str):
        """Track a resource as having findings (async thread-safe)"""
        async with self._lock:
            self.tracked_resources.add((resource_type, namespace, resource_name))

    def _track_resource(self, resource_type: str, namespace: str, resource_name: str):
        """Track a resource as having findings (sync version for report_finding)"""
        self.tracked_resources.add((resource_type, namespace, resource_name))

    def _get_image_registry(self, image: str) -> Optional[str]:
        """Extract registry from container image string"""
        if not image:
            return None
        # Handle images like: registry/repo:tag, repo:tag, registry/namespace/repo:tag
        parts = image.split('/')
        if len(parts) == 1:
            # No registry specified, defaults to docker.io
            return 'docker.io'
        elif len(parts) == 2:
            # Could be registry/repo or namespace/repo
            first_part = parts[0]
            if '.' in first_part or ':' in first_part or first_part == 'localhost':
                return first_part.split(':')[0]  # Remove port if present
            else:
                # Assume it's docker.io namespace/repo
                return 'docker.io'
        else:
            # registry/namespace/repo format
            return parts[0].split(':')[0]  # Remove port if present

    def _parse_size_to_bytes(self, size_str: str) -> Optional[int]:
        """Parse Kubernetes size string to bytes"""
        if not size_str:
            return None
        try:
            size_str = size_str.strip()
            units = {
                'Ki': 1024,
                'Mi': 1024 ** 2,
                'Gi': 1024 ** 3,
                'Ti': 1024 ** 4,
                'K': 1000,
                'M': 1000 ** 2,
                'G': 1000 ** 3,
                'T': 1000 ** 4,
            }
            for suffix, multiplier in units.items():
                if size_str.endswith(suffix):
                    return int(float(size_str[:-len(suffix)]) * multiplier)
            # No suffix, assume bytes
            return int(size_str)
        except (ValueError, TypeError):
            return None

    async def scan_cluster(self):
        """Run all security checks"""
        start_time = time.monotonic()

        # Refresh exclusion caches before full scan
        await self._refresh_excluded_namespaces()
        await self._refresh_excluded_rules()

        await self.scan_pods()
        await self.scan_deployments()
        await self.scan_services()
        await self.scan_rbac()
        await self.scan_network_policies()
        await self.scan_service_accounts()
        await self.scan_pod_security_admission()
        await self.scan_ingresses()
        await self.scan_seccomp_profiles()
        await self.scan_cluster_role_bindings()
        await self.scan_pod_disruption_budgets()
        await self.scan_resource_quotas()
        await self.scan_configmaps()
        await self.scan_cronjobs()
        await self.scan_persistent_volumes()

        # Report scan duration to backend for Prometheus metrics
        duration = time.monotonic() - start_time
        logger.info(f"Security scan completed in {duration:.1f}s")
        await self.backend_client.report_scan_duration(duration)

    async def scan_pods(self):
        """Scan pods for security issues based on Pod Security Standards and NSA/CISA guidelines"""
        logger.info("Scanning pods for security issues...")
        try:
            pods = self.v1.list_pod_for_all_namespaces()

            for pod in pods.items:
                # Skip pods in excluded namespaces (system + admin-configured)
                if self._is_namespace_excluded(pod.metadata.namespace):
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"
                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace

                # === Pod-level security checks ===

                # Check for hostNetwork (Baseline)
                if pod.spec.host_network:
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "Pod uses host network namespace",
                        "description": "Pod is using the host network namespace, which exposes the host's network stack to the container and bypasses network policies.",
                        "remediation": "Remove 'hostNetwork: true' unless required for specific use cases like CNI plugins or monitoring agents.",
                        "timestamp": timestamp
                    })

                # Check for hostPID (Baseline)
                if pod.spec.host_pid:
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "Pod uses host PID namespace",
                        "description": "Pod is using the host PID namespace, which allows viewing and signaling all processes on the host.",
                        "remediation": "Remove 'hostPID: true' unless absolutely necessary for debugging or monitoring.",
                        "timestamp": timestamp
                    })

                # Check for hostIPC (Baseline) - NEW
                if pod.spec.host_ipc:
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "Pod uses host IPC namespace",
                        "description": "Pod is using the host IPC namespace, which allows reading shared memory with host processes.",
                        "remediation": "Remove 'hostIPC: true' from the pod specification.",
                        "timestamp": timestamp
                    })

                # Check for hostPath volumes (Baseline) - NEW
                if pod.spec.volumes:
                    for volume in pod.spec.volumes:
                        if volume.host_path:
                            severity = "critical" if volume.host_path.path in ['/', '/etc', '/var', '/root', '/home'] else "high"
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod_name,
                                "namespace": namespace,
                                "severity": severity,
                                "category": "Security",
                                "title": f"HostPath volume mounted: {volume.host_path.path}",
                                "description": f"Volume '{volume.name}' mounts host path '{volume.host_path.path}'. This provides direct access to the host filesystem and can lead to container escape.",
                                "remediation": "Use persistent volumes, configMaps, secrets, or emptyDir instead of hostPath volumes.",
                                "timestamp": timestamp
                            })

                # === Container-level security checks ===
                all_containers = (pod.spec.containers or []) + (pod.spec.init_containers or [])

                for container in all_containers:
                    container_name = container.name
                    sec_ctx = container.security_context

                    # Check for privileged containers (Baseline)
                    if sec_ctx and sec_ctx.privileged:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "critical",
                            "category": "Security",
                            "title": f"Privileged container: {container_name}",
                            "description": f"Container '{container_name}' is running in privileged mode, which grants full access to all host devices and capabilities. This is equivalent to root on the host.",
                            "remediation": "Remove 'privileged: true' from the container's securityContext. Use specific capabilities if needed.",
                            "timestamp": timestamp
                        })

                    # Check for allowPrivilegeEscalation (Restricted) - NEW
                    if not sec_ctx or sec_ctx.allow_privilege_escalation is None or sec_ctx.allow_privilege_escalation:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "high",
                            "category": "Security",
                            "title": f"Privilege escalation allowed: {container_name}",
                            "description": f"Container '{container_name}' allows privilege escalation via setuid binaries or filesystem capabilities.",
                            "remediation": "Set 'allowPrivilegeEscalation: false' in the container's securityContext.",
                            "timestamp": timestamp
                        })

                    # Check for dangerous capabilities (Baseline/Restricted) - NEW
                    if sec_ctx and sec_ctx.capabilities and sec_ctx.capabilities.add:
                        dangerous_caps = [cap for cap in sec_ctx.capabilities.add if cap in self.DANGEROUS_CAPABILITIES]
                        if dangerous_caps:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod_name,
                                "namespace": namespace,
                                "severity": "high",
                                "category": "Security",
                                "title": f"Dangerous capabilities added: {container_name}",
                                "description": f"Container '{container_name}' adds dangerous capabilities: {', '.join(dangerous_caps)}. These can be used for container escape or privilege escalation.",
                                "remediation": f"Remove dangerous capabilities from the container. Only NET_BIND_SERVICE is allowed in the Restricted policy.",
                                "timestamp": timestamp
                            })

                    # Check for missing capability drop ALL (Restricted) - NEW
                    caps_dropped_all = (
                        sec_ctx and sec_ctx.capabilities and sec_ctx.capabilities.drop and
                        ('ALL' in sec_ctx.capabilities.drop or 'all' in sec_ctx.capabilities.drop)
                    )
                    if not caps_dropped_all:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Capabilities not dropped: {container_name}",
                            "description": f"Container '{container_name}' does not drop all capabilities. Containers inherit default capabilities that may not be needed.",
                            "remediation": "Add 'drop: [\"ALL\"]' to capabilities and only add back specific needed capabilities.",
                            "timestamp": timestamp
                        })

                    # Check for running as root user (Restricted)
                    run_as_non_root = sec_ctx and sec_ctx.run_as_non_root
                    explicit_root = sec_ctx and sec_ctx.run_as_user == 0
                    pod_run_as_non_root = pod.spec.security_context and pod.spec.security_context.run_as_non_root

                    if explicit_root:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "high",
                            "category": "Security",
                            "title": f"Container runs as root (UID 0): {container_name}",
                            "description": f"Container '{container_name}' explicitly sets runAsUser: 0 (root). Running as root increases the impact of container escape.",
                            "remediation": "Set 'runAsUser' to a non-zero UID (e.g., 1000) and 'runAsNonRoot: true'.",
                            "timestamp": timestamp
                        })
                    elif not run_as_non_root and not pod_run_as_non_root:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Container may run as root: {container_name}",
                            "description": f"Container '{container_name}' does not explicitly prevent running as root user.",
                            "remediation": "Set 'runAsNonRoot: true' in the container's or pod's securityContext.",
                            "timestamp": timestamp
                        })

                    # Check for writable root filesystem - NEW
                    if not sec_ctx or not sec_ctx.read_only_root_filesystem:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Writable root filesystem: {container_name}",
                            "description": f"Container '{container_name}' has a writable root filesystem, which allows attackers to modify binaries or add malicious files.",
                            "remediation": "Set 'readOnlyRootFilesystem: true' and use emptyDir or volumes for writable paths.",
                            "timestamp": timestamp
                        })

                    # Check for missing resource limits
                    if not container.resources or not container.resources.limits:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Best Practice",
                            "title": f"Missing resource limits: {container_name}",
                            "description": f"Container '{container_name}' does not have resource limits defined, which can lead to resource exhaustion and DoS.",
                            "remediation": "Add resource limits (cpu and memory) to the container specification.",
                            "timestamp": timestamp
                        })

                    # Check for host ports - NEW
                    if container.ports:
                        for port in container.ports:
                            if port.host_port:
                                await self.report_finding({
                                    "resource_type": "Pod",
                                    "resource_name": pod_name,
                                    "namespace": namespace,
                                    "severity": "medium",
                                    "category": "Security",
                                    "title": f"Host port exposed: {port.host_port}",
                                    "description": f"Container '{container_name}' exposes host port {port.host_port}. This bypasses Kubernetes networking and may expose the service on all nodes.",
                                    "remediation": "Use Services (ClusterIP, NodePort, LoadBalancer) instead of hostPort for external access.",
                                    "timestamp": timestamp
                                })

                    # Check for secrets in environment variables - NEW (NSA/CISA)
                    if container.env:
                        for env in container.env:
                            if env.value_from and env.value_from.secret_key_ref:
                                await self.report_finding({
                                    "resource_type": "Pod",
                                    "resource_name": pod_name,
                                    "namespace": namespace,
                                    "severity": "low",
                                    "category": "Best Practice",
                                    "title": f"Secret exposed as environment variable: {env.name}",
                                    "description": f"Container '{container_name}' exposes secret '{env.value_from.secret_key_ref.name}' as environment variable '{env.name}'. Env vars can be leaked in logs, error messages, or child processes.",
                                    "remediation": "Mount secrets as files using volumes instead of environment variables.",
                                    "timestamp": timestamp
                                })

                    # Check for :latest image tag
                    image = container.image or ""
                    if image.endswith(':latest') or (':' not in image.split('/')[-1]):
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Best Practice",
                            "title": f"Image uses :latest or no tag: {container_name}",
                            "description": f"Container '{container_name}' uses image '{image}' with :latest or no tag. Mutable tags can introduce unexpected changes and make rollbacks difficult.",
                            "remediation": "Use immutable image tags (e.g., specific versions or SHA digests) for reproducible deployments.",
                            "timestamp": timestamp
                        })

                    # Check for untrusted registry
                    image_registry = self._get_image_registry(image)
                    if image_registry and image_registry not in self.TRUSTED_REGISTRIES:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "high",
                            "category": "Security",
                            "title": f"Image from untrusted registry: {container_name}",
                            "description": f"Container '{container_name}' uses image from registry '{image_registry}' which is not in the trusted registry list.",
                            "remediation": f"Use images from trusted registries: {', '.join(self.TRUSTED_REGISTRIES[:4])}. Or add the registry to the trusted list if it's an internal registry.",
                            "timestamp": timestamp
                        })

                    # Check for missing imagePullPolicy
                    if not container.image_pull_policy or container.image_pull_policy == "IfNotPresent":
                        if image.endswith(':latest') or (':' not in image.split('/')[-1]):
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod_name,
                                "namespace": namespace,
                                "severity": "low",
                                "category": "Best Practice",
                                "title": f"Missing imagePullPolicy with mutable tag: {container_name}",
                                "description": f"Container '{container_name}' uses a mutable image tag without imagePullPolicy: Always. Cached vulnerable images may be used.",
                                "remediation": "Set imagePullPolicy: Always when using mutable tags, or use immutable image tags.",
                                "timestamp": timestamp
                            })

                # Check for emptyDir volumes with large sizeLimit
                if pod.spec.volumes:
                    for volume in pod.spec.volumes:
                        if volume.empty_dir and volume.empty_dir.size_limit:
                            size_limit_str = volume.empty_dir.size_limit
                            size_bytes = self._parse_size_to_bytes(size_limit_str)
                            if size_bytes and size_bytes > self.LARGE_EMPTYDIR_THRESHOLD:
                                await self.report_finding({
                                    "resource_type": "Pod",
                                    "resource_name": pod_name,
                                    "namespace": namespace,
                                    "severity": "low",
                                    "category": "Best Practice",
                                    "title": f"EmptyDir with large sizeLimit: {volume.name}",
                                    "description": f"Volume '{volume.name}' has emptyDir with sizeLimit of {size_limit_str}. Large emptyDir volumes can exhaust node disk space.",
                                    "remediation": "Consider using PersistentVolumes for large storage needs, or reduce the sizeLimit.",
                                    "timestamp": timestamp
                                })

                # Check for AppArmor profile
                annotations = pod.metadata.annotations or {}
                for container in all_containers:
                    container_name = container.name
                    apparmor_key = f"container.apparmor.security.beta.kubernetes.io/{container_name}"
                    if apparmor_key not in annotations:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Missing AppArmor profile: {container_name}",
                            "description": f"Container '{container_name}' does not have an AppArmor profile configured. AppArmor provides mandatory access control for Linux applications.",
                            "remediation": f"Add annotation '{apparmor_key}: runtime/default' to use the default AppArmor profile.",
                            "timestamp": timestamp
                        })

                # Check for SELinux options
                pod_sec_ctx = pod.spec.security_context
                pod_has_selinux = pod_sec_ctx and pod_sec_ctx.se_linux_options
                for container in all_containers:
                    container_name = container.name
                    sec_ctx = container.security_context
                    container_has_selinux = sec_ctx and sec_ctx.se_linux_options
                    if not pod_has_selinux and not container_has_selinux:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Missing SELinux options: {container_name}",
                            "description": f"Container '{container_name}' does not have SELinux options configured. SELinux provides mandatory access control enforcement.",
                            "remediation": "Configure seLinuxOptions in the pod or container securityContext if running on SELinux-enabled nodes.",
                            "timestamp": timestamp
                        })

            logger.info("Pod security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning pods: {e}")
        except Exception as e:
            logger.error(f"Error scanning pods: {e}")

    async def scan_deployments(self):
        """Scan deployments for security issues"""
        logger.info("Scanning deployments for security issues...")
        try:
            deployments = self.apps_v1.list_deployment_for_all_namespaces()

            for deployment in deployments.items:
                # Skip deployments in excluded namespaces (system + admin-configured)
                if self._is_namespace_excluded(deployment.metadata.namespace):
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"

                # Check for missing replica count
                if deployment.spec.replicas and deployment.spec.replicas < 2:
                    await self.report_finding({
                        "resource_type": "Deployment",
                        "resource_name": deployment.metadata.name,
                        "namespace": deployment.metadata.namespace,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "Single replica deployment",
                        "description": f"Deployment has only {deployment.spec.replicas} replica(s), which affects high availability.",
                        "remediation": "Increase the number of replicas to at least 2 for production workloads.",
                        "timestamp": timestamp
                    })

                # Check for missing pod anti-affinity in HA deployments
                replicas = deployment.spec.replicas or 1
                if replicas >= 2:
                    pod_template = deployment.spec.template
                    affinity = pod_template.spec.affinity if pod_template.spec else None
                    has_anti_affinity = (
                        affinity and affinity.pod_anti_affinity and
                        (affinity.pod_anti_affinity.required_during_scheduling_ignored_during_execution or
                         affinity.pod_anti_affinity.preferred_during_scheduling_ignored_during_execution)
                    )
                    if not has_anti_affinity:
                        await self.report_finding({
                            "resource_type": "Deployment",
                            "resource_name": deployment.metadata.name,
                            "namespace": deployment.metadata.namespace,
                            "severity": "low",
                            "category": "Best Practice",
                            "title": "HA deployment without pod anti-affinity",
                            "description": f"Deployment '{deployment.metadata.name}' has {replicas} replicas but no pod anti-affinity rules. All replicas could be scheduled on the same node.",
                            "remediation": "Add podAntiAffinity rules to spread replicas across nodes for better fault tolerance.",
                            "timestamp": timestamp
                        })

            logger.info("Deployment security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning deployments: {e}")
        except Exception as e:
            logger.error(f"Error scanning deployments: {e}")

    async def scan_services(self):
        """Scan services for security issues"""
        logger.info("Scanning services for security issues...")
        try:
            services = self.v1.list_service_for_all_namespaces()

            for service in services.items:
                # Skip services in excluded namespaces (system + admin-configured)
                if self._is_namespace_excluded(service.metadata.namespace):
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"
                service_name = service.metadata.name
                namespace = service.metadata.namespace

                # Check for LoadBalancer services
                if service.spec.type == "LoadBalancer":
                    await self.report_finding({
                        "resource_type": "Service",
                        "resource_name": service_name,
                        "namespace": namespace,
                        "severity": "medium",
                        "category": "Security",
                        "title": "Service exposed via LoadBalancer",
                        "description": "Service is exposed externally via LoadBalancer, which may be accessible from the internet.",
                        "remediation": "Review if external exposure is necessary. Consider using ClusterIP with Ingress controller for better control.",
                        "timestamp": timestamp
                    })

                # Check for NodePort services - NEW
                if service.spec.type == "NodePort":
                    await self.report_finding({
                        "resource_type": "Service",
                        "resource_name": service_name,
                        "namespace": namespace,
                        "severity": "medium",
                        "category": "Security",
                        "title": "Service exposed via NodePort",
                        "description": f"Service is exposed on all cluster nodes via NodePort. This exposes the service on every node's IP address.",
                        "remediation": "Consider using ClusterIP with Ingress controller for controlled external access, or LoadBalancer for cloud environments.",
                        "timestamp": timestamp
                    })

                # Check for ExternalName services - NEW
                if service.spec.type == "ExternalName":
                    await self.report_finding({
                        "resource_type": "Service",
                        "resource_name": service_name,
                        "namespace": namespace,
                        "severity": "low",
                        "category": "Security",
                        "title": "ExternalName service detected",
                        "description": f"Service redirects to external DNS name '{service.spec.external_name}'. This can be used for DNS rebinding attacks or unintended external access.",
                        "remediation": "Verify the external name is trusted and consider using NetworkPolicies to restrict egress traffic.",
                        "timestamp": timestamp
                    })

            logger.info("Service security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning services: {e}")
        except Exception as e:
            logger.error(f"Error scanning services: {e}")

    async def scan_rbac(self):
        """Scan RBAC for security issues"""
        logger.info("Scanning RBAC for security issues...")
        try:
            # Check ClusterRoles for overly permissive permissions
            cluster_roles = self.rbac_v1.list_cluster_role()

            for role in cluster_roles.items:
                if role.metadata.name.startswith('system:'):
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"
                role_name = role.metadata.name
                reported_wildcards = False

                if role.rules:
                    for rule in role.rules:
                        resources = rule.resources or []
                        verbs = rule.verbs or []
                        api_groups = rule.api_groups or []

                        # Check for wildcard resource permissions
                        if '*' in resources and not reported_wildcards:
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role_name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": "ClusterRole with wildcard resource permissions",
                                "description": f"ClusterRole '{role_name}' has wildcard (*) resource permissions, which grants access to all resources.",
                                "remediation": "Restrict permissions to specific resources instead of using wildcards.",
                                "timestamp": timestamp
                            })
                            reported_wildcards = True

                        # Check for wildcard verb permissions
                        if '*' in verbs and not reported_wildcards:
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role_name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": "ClusterRole with wildcard verb permissions",
                                "description": f"ClusterRole '{role_name}' has wildcard (*) verb permissions, which grants all actions.",
                                "remediation": "Restrict permissions to specific verbs (get, list, watch, create, update, delete) instead of using wildcards.",
                                "timestamp": timestamp
                            })
                            reported_wildcards = True

                        # Check for secrets access - NEW (NSA/CISA)
                        if 'secrets' in resources:
                            dangerous_verbs = [v for v in verbs if v in ['get', 'list', 'watch', '*']]
                            if dangerous_verbs:
                                await self.report_finding({
                                    "resource_type": "ClusterRole",
                                    "resource_name": role_name,
                                    "namespace": "cluster-wide",
                                    "severity": "high",
                                    "category": "Security",
                                    "title": f"ClusterRole can read secrets",
                                    "description": f"ClusterRole '{role_name}' has {', '.join(dangerous_verbs)} access to secrets. This allows reading sensitive data like passwords, tokens, and keys.",
                                    "remediation": "Restrict secrets access to only the namespaces and specific secrets required.",
                                    "timestamp": timestamp
                                })

                        # Check for pod exec permissions - NEW (NSA/CISA)
                        if 'pods/exec' in resources or ('pods' in resources and 'create' in verbs):
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role_name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": f"ClusterRole allows pod exec",
                                "description": f"ClusterRole '{role_name}' can execute commands inside pods. This allows running arbitrary commands in containers.",
                                "remediation": "Limit exec permissions to specific namespaces or remove if not needed for debugging.",
                                "timestamp": timestamp
                            })

                        # Check for cluster-admin equivalent - NEW
                        if '*' in resources and '*' in verbs and ('' in api_groups or '*' in api_groups):
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role_name,
                                "namespace": "cluster-wide",
                                "severity": "critical",
                                "category": "Security",
                                "title": f"ClusterRole has cluster-admin equivalent permissions",
                                "description": f"ClusterRole '{role_name}' has full access to all resources in all API groups. This is equivalent to cluster-admin.",
                                "remediation": "Review if full cluster access is necessary. Apply principle of least privilege.",
                                "timestamp": timestamp
                            })

            # Also check namespaced Roles for dangerous permissions - NEW
            roles = self.rbac_v1.list_role_for_all_namespaces()
            for role in roles.items:
                # Skip roles in excluded namespaces (system + admin-configured)
                if self._is_namespace_excluded(role.metadata.namespace):
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"
                role_name = role.metadata.name
                namespace = role.metadata.namespace

                if role.rules:
                    for rule in role.rules:
                        resources = rule.resources or []
                        verbs = rule.verbs or []

                        # Check for secrets access in namespaced roles
                        if 'secrets' in resources:
                            dangerous_verbs = [v for v in verbs if v in ['get', 'list', 'watch', '*']]
                            if dangerous_verbs:
                                await self.report_finding({
                                    "resource_type": "Role",
                                    "resource_name": role_name,
                                    "namespace": namespace,
                                    "severity": "medium",
                                    "category": "Security",
                                    "title": f"Role can read secrets in namespace",
                                    "description": f"Role '{role_name}' has {', '.join(dangerous_verbs)} access to secrets in namespace '{namespace}'.",
                                    "remediation": "Review if secrets access is necessary and limit to specific secret names if possible.",
                                    "timestamp": timestamp
                                })

            logger.info("RBAC security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning RBAC: {e}")
        except Exception as e:
            logger.error(f"Error scanning RBAC: {e}")

    async def scan_network_policies(self):
        """Scan for missing network policies (NSA/CISA recommendation)"""
        logger.info("Scanning network policies...")
        try:
            # Get all namespaces
            namespaces = self.v1.list_namespace()

            # Get all network policies
            network_policies = self.networking_v1.list_network_policy_for_all_namespaces()

            # Build a set of namespaces that have at least one NetworkPolicy
            namespaces_with_policies = set()
            for policy in network_policies.items:
                namespaces_with_policies.add(policy.metadata.namespace)

            timestamp = datetime.utcnow().isoformat() + "Z"

            for ns in namespaces.items:
                ns_name = ns.metadata.name

                # Skip excluded namespaces (system + admin-configured)
                if self._is_namespace_excluded(ns_name):
                    continue

                # Check if namespace has any pods (skip empty namespaces)
                pods = self.v1.list_namespaced_pod(ns_name)
                if not pods.items:
                    continue

                # Report if namespace has no network policies
                if ns_name not in namespaces_with_policies:
                    await self.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "medium",
                        "category": "Security",
                        "title": "Namespace has no NetworkPolicy",
                        "description": f"Namespace '{ns_name}' has no NetworkPolicy defined. All pods can communicate with all other pods in the cluster without restriction.",
                        "remediation": "Create NetworkPolicies to implement network segmentation and restrict pod-to-pod communication based on the principle of least privilege.",
                        "timestamp": timestamp
                    })

            logger.info("Network policy scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning network policies: {e}")
        except Exception as e:
            logger.error(f"Error scanning network policies: {e}")

    async def scan_service_accounts(self):
        """Scan service accounts for security issues"""
        logger.info("Scanning service accounts...")
        try:
            # Get all pods to check their service account usage
            pods = self.v1.list_pod_for_all_namespaces()

            timestamp = datetime.utcnow().isoformat() + "Z"

            for pod in pods.items:
                # Skip pods in excluded namespaces (system + admin-configured)
                if self._is_namespace_excluded(pod.metadata.namespace):
                    continue

                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace
                sa_name = pod.spec.service_account_name or 'default'

                # Check for default service account usage - NEW
                if sa_name == 'default':
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "Pod uses default ServiceAccount",
                        "description": f"Pod '{pod_name}' uses the default service account. This makes it harder to apply the principle of least privilege.",
                        "remediation": "Create a dedicated ServiceAccount for this workload and assign only the permissions it needs.",
                        "timestamp": timestamp
                    })

                # Check for automounted service account token - NEW (NSA/CISA)
                automount = pod.spec.automount_service_account_token
                if automount is None or automount:
                    # Check if the service account itself disables it
                    try:
                        sa = self.v1.read_namespaced_service_account(sa_name, namespace)
                        sa_automount = sa.automount_service_account_token
                        if sa_automount is None or sa_automount:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod_name,
                                "namespace": namespace,
                                "severity": "medium",
                                "category": "Security",
                                "title": "ServiceAccount token auto-mounted",
                                "description": f"Pod '{pod_name}' has the ServiceAccount token automatically mounted. If compromised, this token can be used to access the Kubernetes API.",
                                "remediation": "Set 'automountServiceAccountToken: false' in the pod spec or service account if API access is not needed.",
                                "timestamp": timestamp
                            })
                    except ApiException:
                        pass  # Service account might not exist or we don't have permission

                # Check for pods using ServiceAccounts from kube-system
                sa_namespace = namespace  # By default, SA is in the same namespace
                # Check if serviceAccountName includes namespace prefix (rare but possible)
                if '/' in sa_name:
                    sa_namespace, sa_name = sa_name.split('/', 1)

                if sa_namespace == 'kube-system' or (namespace != 'kube-system' and sa_name.startswith('system:')):
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "medium",
                        "category": "Security",
                        "title": f"Pod uses system ServiceAccount: {sa_name}",
                        "description": f"Pod '{pod_name}' uses a system-level ServiceAccount. This could grant unintended elevated permissions.",
                        "remediation": "Create a dedicated ServiceAccount in the workload's namespace with only required permissions.",
                        "timestamp": timestamp
                    })

            logger.info("Service account scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning service accounts: {e}")
        except Exception as e:
            logger.error(f"Error scanning service accounts: {e}")

    async def report_finding(self, finding_data: dict):
        """Report a security finding to the backend and track the resource"""
        # Check if this rule is excluded (globally or for this namespace)
        title = finding_data.get("title", "")
        namespace = finding_data.get("namespace", "")
        if title and self._is_rule_excluded(title, namespace):
            logger.debug(f"Skipping excluded rule: {title} (namespace: {namespace})")
            return

        # Track this resource for deletion detection
        resource_type = finding_data.get("resource_type", "")
        resource_name = finding_data.get("resource_name", "")
        if resource_type and namespace and resource_name:
            self._track_resource(resource_type, namespace, resource_name)

        await self.backend_client.report_security_finding(finding_data)

    async def scan_pod_security_admission(self):
        """Scan namespaces for Pod Security Admission (PSA) labels"""
        logger.info("Scanning Pod Security Admission labels...")
        try:
            namespaces = self.v1.list_namespace()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for ns in namespaces.items:
                ns_name = ns.metadata.name

                # Skip excluded namespaces (system + admin-configured)
                if self._is_namespace_excluded(ns_name):
                    continue

                labels = ns.metadata.labels or {}

                # Check for PSA enforce label
                enforce_label = labels.get('pod-security.kubernetes.io/enforce')
                warn_label = labels.get('pod-security.kubernetes.io/warn')
                audit_label = labels.get('pod-security.kubernetes.io/audit')

                # Check if namespace has any pods
                pods = self.v1.list_namespaced_pod(ns_name)
                if not pods.items:
                    continue

                if not enforce_label and not warn_label and not audit_label:
                    await self.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "medium",
                        "category": "Compliance",
                        "title": "No Pod Security Admission labels configured",
                        "description": f"Namespace '{ns_name}' has no Pod Security Admission labels configured. PSA provides built-in enforcement of Pod Security Standards.",
                        "remediation": "Add PSA labels to the namespace: 'pod-security.kubernetes.io/enforce: baseline' or 'restricted' for production workloads.",
                        "timestamp": timestamp
                    })
                elif enforce_label == 'privileged':
                    await self.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "high",
                        "category": "Security",
                        "title": "Pod Security Admission set to privileged",
                        "description": f"Namespace '{ns_name}' has PSA enforce set to 'privileged', which allows unrestricted pod configurations including privileged containers.",
                        "remediation": "Consider using 'baseline' or 'restricted' enforce level for better security. Use 'privileged' only for system namespaces.",
                        "timestamp": timestamp
                    })

            logger.info("Pod Security Admission scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning PSA: {e}")
        except Exception as e:
            logger.error(f"Error scanning PSA: {e}")

    async def scan_ingresses(self):
        """Scan Ingress resources for security issues"""
        logger.info("Scanning Ingresses for security issues...")
        try:
            ingresses = self.networking_v1.list_ingress_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            # Dangerous annotations that could bypass security
            dangerous_annotations = [
                'nginx.ingress.kubernetes.io/ssl-passthrough',
                'nginx.ingress.kubernetes.io/backend-protocol',
                'nginx.ingress.kubernetes.io/configuration-snippet',
                'nginx.ingress.kubernetes.io/server-snippet',
            ]

            for ingress in ingresses.items:
                if self._is_namespace_excluded(ingress.metadata.namespace):
                    continue

                ingress_name = ingress.metadata.name
                namespace = ingress.metadata.namespace
                annotations = ingress.metadata.annotations or {}

                # Check for missing TLS
                if not ingress.spec.tls:
                    await self.report_finding({
                        "resource_type": "Ingress",
                        "resource_name": ingress_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "Ingress without TLS configuration",
                        "description": f"Ingress '{ingress_name}' does not have TLS configured. Traffic will be unencrypted.",
                        "remediation": "Configure TLS for the Ingress using a certificate from cert-manager or a manually provisioned certificate.",
                        "timestamp": timestamp
                    })

                # Check for wildcard hosts
                if ingress.spec.rules:
                    for rule in ingress.spec.rules:
                        if rule.host and rule.host.startswith('*'):
                            await self.report_finding({
                                "resource_type": "Ingress",
                                "resource_name": ingress_name,
                                "namespace": namespace,
                                "severity": "medium",
                                "category": "Security",
                                "title": f"Ingress with wildcard host: {rule.host}",
                                "description": f"Ingress '{ingress_name}' uses wildcard host '{rule.host}'. This could expose services to unintended subdomains.",
                                "remediation": "Use specific hostnames instead of wildcards to limit exposure.",
                                "timestamp": timestamp
                            })

                # Check for dangerous annotations
                for annotation in dangerous_annotations:
                    if annotation in annotations:
                        await self.report_finding({
                            "resource_type": "Ingress",
                            "resource_name": ingress_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Potentially dangerous Ingress annotation",
                            "description": f"Ingress '{ingress_name}' uses annotation '{annotation}' which could be used to bypass security controls or inject configuration.",
                            "remediation": "Review if this annotation is necessary and ensure it doesn't introduce security vulnerabilities.",
                            "timestamp": timestamp
                        })

            logger.info("Ingress security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning Ingresses: {e}")
        except Exception as e:
            logger.error(f"Error scanning Ingresses: {e}")

    async def scan_seccomp_profiles(self):
        """Scan pods for missing seccomp profiles (PSS Restricted requirement)"""
        logger.info("Scanning seccomp profiles...")
        try:
            pods = self.v1.list_pod_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for pod in pods.items:
                if self._is_namespace_excluded(pod.metadata.namespace):
                    continue

                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace

                # Check pod-level seccomp profile
                pod_sec_ctx = pod.spec.security_context
                pod_has_seccomp = (
                    pod_sec_ctx and pod_sec_ctx.seccomp_profile and
                    pod_sec_ctx.seccomp_profile.type in ['RuntimeDefault', 'Localhost']
                )

                all_containers = (pod.spec.containers or []) + (pod.spec.init_containers or [])

                for container in all_containers:
                    container_name = container.name
                    sec_ctx = container.security_context

                    # Check container-level seccomp profile
                    container_has_seccomp = (
                        sec_ctx and sec_ctx.seccomp_profile and
                        sec_ctx.seccomp_profile.type in ['RuntimeDefault', 'Localhost']
                    )

                    if not pod_has_seccomp and not container_has_seccomp:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Missing seccomp profile: {container_name}",
                            "description": f"Container '{container_name}' does not have a seccomp profile configured. Seccomp restricts which system calls a container can make.",
                            "remediation": "Set seccompProfile.type to 'RuntimeDefault' in the pod or container securityContext. This is required for PSS Restricted compliance.",
                            "timestamp": timestamp
                        })

            logger.info("Seccomp profile scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning seccomp profiles: {e}")
        except Exception as e:
            logger.error(f"Error scanning seccomp profiles: {e}")

    async def scan_cluster_role_bindings(self):
        """Scan ClusterRoleBindings for security issues"""
        logger.info("Scanning ClusterRoleBindings...")
        try:
            bindings = self.rbac_v1.list_cluster_role_binding()
            timestamp = datetime.utcnow().isoformat() + "Z"

            # Dangerous subjects that should never have cluster-wide permissions
            dangerous_subjects = [
                ('Group', 'system:anonymous'),
                ('Group', 'system:unauthenticated'),
            ]

            # High-privilege cluster roles
            high_privilege_roles = ['cluster-admin', 'admin', 'edit']

            for binding in bindings.items:
                if binding.metadata.name.startswith('system:'):
                    continue

                binding_name = binding.metadata.name
                role_ref = binding.role_ref.name if binding.role_ref else None
                subjects = binding.subjects or []

                # Check for bindings to dangerous subjects
                for subject in subjects:
                    subject_key = (subject.kind, subject.name)
                    if subject_key in dangerous_subjects:
                        await self.report_finding({
                            "resource_type": "ClusterRoleBinding",
                            "resource_name": binding_name,
                            "namespace": "cluster-wide",
                            "severity": "critical",
                            "category": "Security",
                            "title": f"ClusterRoleBinding grants permissions to {subject.name}",
                            "description": f"ClusterRoleBinding '{binding_name}' grants cluster-wide permissions to '{subject.name}'. This allows unauthenticated access to cluster resources.",
                            "remediation": "Remove this binding or change the subject to authenticated users/groups only.",
                            "timestamp": timestamp
                        })

                # Check for ServiceAccounts bound to high-privilege roles
                if role_ref in high_privilege_roles:
                    for subject in subjects:
                        if subject.kind == 'ServiceAccount':
                            await self.report_finding({
                                "resource_type": "ClusterRoleBinding",
                                "resource_name": binding_name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": f"ServiceAccount bound to {role_ref}",
                                "description": f"ServiceAccount '{subject.namespace}/{subject.name}' is bound to high-privilege ClusterRole '{role_ref}' via '{binding_name}'.",
                                "remediation": "Review if this ServiceAccount requires cluster-admin level access. Apply principle of least privilege.",
                                "timestamp": timestamp
                            })

            logger.info("ClusterRoleBinding scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning ClusterRoleBindings: {e}")
        except Exception as e:
            logger.error(f"Error scanning ClusterRoleBindings: {e}")

    async def scan_pod_disruption_budgets(self):
        """Scan for critical deployments without PodDisruptionBudgets"""
        logger.info("Scanning PodDisruptionBudgets...")
        try:
            deployments = self.apps_v1.list_deployment_for_all_namespaces()
            pdbs = self.policy_v1.list_pod_disruption_budget_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            # Build a map of namespaces with PDBs and their selectors
            pdb_selectors = {}
            for pdb in pdbs.items:
                ns = pdb.metadata.namespace
                if ns not in pdb_selectors:
                    pdb_selectors[ns] = []
                if pdb.spec.selector and pdb.spec.selector.match_labels:
                    pdb_selectors[ns].append(pdb.spec.selector.match_labels)

            for deployment in deployments.items:
                if self._is_namespace_excluded(deployment.metadata.namespace):
                    continue

                deploy_name = deployment.metadata.name
                namespace = deployment.metadata.namespace
                replicas = deployment.spec.replicas or 1

                # Only check deployments with 2+ replicas (critical/HA workloads)
                if replicas < 2:
                    continue

                # Check if any PDB covers this deployment
                deploy_labels = deployment.spec.selector.match_labels or {}
                has_pdb = False

                if namespace in pdb_selectors:
                    for pdb_labels in pdb_selectors[namespace]:
                        # Check if PDB selector matches deployment
                        if all(deploy_labels.get(k) == v for k, v in pdb_labels.items()):
                            has_pdb = True
                            break

                if not has_pdb:
                    await self.report_finding({
                        "resource_type": "Deployment",
                        "resource_name": deploy_name,
                        "namespace": namespace,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "High-availability deployment without PodDisruptionBudget",
                        "description": f"Deployment '{deploy_name}' has {replicas} replicas but no PodDisruptionBudget. During cluster maintenance, all pods could be evicted simultaneously.",
                        "remediation": "Create a PodDisruptionBudget to ensure minimum availability during voluntary disruptions like node drains.",
                        "timestamp": timestamp
                    })

            logger.info("PodDisruptionBudget scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning PDBs: {e}")
        except Exception as e:
            logger.error(f"Error scanning PDBs: {e}")

    async def scan_resource_quotas(self):
        """Scan namespaces for missing ResourceQuotas and LimitRanges"""
        logger.info("Scanning ResourceQuotas and LimitRanges...")
        try:
            namespaces = self.v1.list_namespace()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for ns in namespaces.items:
                ns_name = ns.metadata.name

                if self._is_namespace_excluded(ns_name):
                    continue

                # Check if namespace has pods
                pods = self.v1.list_namespaced_pod(ns_name)
                if not pods.items:
                    continue

                # Check for ResourceQuota
                quotas = self.v1.list_namespaced_resource_quota(ns_name)
                if not quotas.items:
                    await self.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "Namespace has no ResourceQuota",
                        "description": f"Namespace '{ns_name}' has no ResourceQuota configured. Workloads can consume unlimited cluster resources.",
                        "remediation": "Create a ResourceQuota to limit the total resources (CPU, memory, storage, object count) that can be consumed in this namespace.",
                        "timestamp": timestamp
                    })

                # Check for LimitRange
                limit_ranges = self.v1.list_namespaced_limit_range(ns_name)
                if not limit_ranges.items:
                    await self.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "Namespace has no LimitRange",
                        "description": f"Namespace '{ns_name}' has no LimitRange configured. Containers without resource limits can consume unlimited resources.",
                        "remediation": "Create a LimitRange to set default resource limits and requests for containers in this namespace.",
                        "timestamp": timestamp
                    })

            logger.info("ResourceQuota and LimitRange scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning ResourceQuotas: {e}")
        except Exception as e:
            logger.error(f"Error scanning ResourceQuotas: {e}")

    async def scan_configmaps(self):
        """Scan ConfigMaps for sensitive data patterns"""
        logger.info("Scanning ConfigMaps for sensitive data...")
        try:
            import re
            configmaps = self.v1.list_config_map_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            # Patterns that suggest sensitive data in ConfigMaps
            sensitive_patterns = [
                (r'password\s*[=:]\s*\S+', 'password'),
                (r'api[_-]?key\s*[=:]\s*\S+', 'API key'),
                (r'secret[_-]?key\s*[=:]\s*\S+', 'secret key'),
                (r'access[_-]?token\s*[=:]\s*\S+', 'access token'),
                (r'private[_-]?key', 'private key'),
                (r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----', 'private key'),
                (r'aws[_-]?secret[_-]?access[_-]?key', 'AWS secret'),
            ]

            # Keys that often contain sensitive data
            sensitive_keys = [
                'password', 'passwd', 'secret', 'token', 'api_key', 'apikey',
                'private_key', 'privatekey', 'credentials', 'auth'
            ]

            for cm in configmaps.items:
                if self._is_namespace_excluded(cm.metadata.namespace):
                    continue

                cm_name = cm.metadata.name
                namespace = cm.metadata.namespace
                data = cm.data or {}

                found_sensitive = set()

                for key, value in data.items():
                    # Check if key name suggests sensitive data
                    key_lower = key.lower()
                    for sensitive_key in sensitive_keys:
                        if sensitive_key in key_lower:
                            found_sensitive.add(f"key '{key}' (contains '{sensitive_key}')")
                            break

                    # Check value for sensitive patterns
                    if value:
                        for pattern, pattern_name in sensitive_patterns:
                            if re.search(pattern, value, re.IGNORECASE):
                                found_sensitive.add(f"value matching '{pattern_name}' pattern")
                                break

                if found_sensitive:
                    await self.report_finding({
                        "resource_type": "ConfigMap",
                        "resource_name": cm_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "ConfigMap may contain sensitive data",
                        "description": f"ConfigMap '{cm_name}' appears to contain sensitive data: {', '.join(list(found_sensitive)[:3])}. ConfigMaps are not encrypted and should not store secrets.",
                        "remediation": "Move sensitive data to Kubernetes Secrets (which can be encrypted at rest) or use external secret management like HashiCorp Vault.",
                        "timestamp": timestamp
                    })

            logger.info("ConfigMap scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning ConfigMaps: {e}")
        except Exception as e:
            logger.error(f"Error scanning ConfigMaps: {e}")

    async def scan_cronjobs(self):
        """Scan CronJobs and Jobs for security issues"""
        logger.info("Scanning CronJobs and Jobs...")
        try:
            cronjobs = self.batch_v1.list_cron_job_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for cronjob in cronjobs.items:
                if self._is_namespace_excluded(cronjob.metadata.namespace):
                    continue

                cj_name = cronjob.metadata.name
                namespace = cronjob.metadata.namespace
                job_template = cronjob.spec.job_template.spec.template.spec

                # Check for excessive history limits
                success_limit = cronjob.spec.successful_jobs_history_limit
                failed_limit = cronjob.spec.failed_jobs_history_limit

                if success_limit and success_limit > 10:
                    await self.report_finding({
                        "resource_type": "CronJob",
                        "resource_name": cj_name,
                        "namespace": namespace,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "CronJob retains excessive job history",
                        "description": f"CronJob '{cj_name}' retains {success_limit} successful jobs. This can consume significant cluster resources over time.",
                        "remediation": "Set successfulJobsHistoryLimit to a lower value (e.g., 3) to reduce resource consumption.",
                        "timestamp": timestamp
                    })

                # Check containers in job template for privileged settings
                all_containers = (job_template.containers or []) + (job_template.init_containers or [])

                for container in all_containers:
                    sec_ctx = container.security_context

                    if sec_ctx and sec_ctx.privileged:
                        await self.report_finding({
                            "resource_type": "CronJob",
                            "resource_name": cj_name,
                            "namespace": namespace,
                            "severity": "critical",
                            "category": "Security",
                            "title": f"CronJob runs privileged container: {container.name}",
                            "description": f"CronJob '{cj_name}' creates jobs with privileged container '{container.name}'. Privileged jobs that run on schedule pose significant security risks.",
                            "remediation": "Remove 'privileged: true' from the container's securityContext. Use specific capabilities if elevated permissions are required.",
                            "timestamp": timestamp
                        })

                    # Check for host namespaces
                    if job_template.host_network:
                        await self.report_finding({
                            "resource_type": "CronJob",
                            "resource_name": cj_name,
                            "namespace": namespace,
                            "severity": "high",
                            "category": "Security",
                            "title": "CronJob uses host network",
                            "description": f"CronJob '{cj_name}' creates jobs with hostNetwork access, which bypasses network policies.",
                            "remediation": "Remove 'hostNetwork: true' unless the job specifically requires host network access.",
                            "timestamp": timestamp
                        })
                        break  # Only report once per CronJob

            logger.info("CronJob scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning CronJobs: {e}")
        except Exception as e:
            logger.error(f"Error scanning CronJobs: {e}")

    async def scan_persistent_volumes(self):
        """Scan PersistentVolumes for security issues"""
        logger.info("Scanning PersistentVolumes...")
        try:
            pvs = self.v1.list_persistent_volume()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for pv in pvs.items:
                pv_name = pv.metadata.name

                # Check for hostPath PersistentVolumes
                if pv.spec.host_path:
                    host_path = pv.spec.host_path.path
                    severity = "critical" if host_path in ['/', '/etc', '/var', '/root', '/home'] else "high"
                    await self.report_finding({
                        "resource_type": "PersistentVolume",
                        "resource_name": pv_name,
                        "namespace": "cluster-wide",
                        "severity": severity,
                        "category": "Security",
                        "title": f"PersistentVolume uses hostPath: {host_path}",
                        "description": f"PersistentVolume '{pv_name}' uses hostPath '{host_path}'. This provides direct access to the host filesystem and can lead to container escape or data exposure.",
                        "remediation": "Use cloud provider storage classes, NFS, or other network-attached storage instead of hostPath for PersistentVolumes.",
                        "timestamp": timestamp
                    })

                # Check for local PersistentVolumes (similar security concerns)
                if pv.spec.local:
                    local_path = pv.spec.local.path
                    await self.report_finding({
                        "resource_type": "PersistentVolume",
                        "resource_name": pv_name,
                        "namespace": "cluster-wide",
                        "severity": "medium",
                        "category": "Security",
                        "title": f"PersistentVolume uses local storage: {local_path}",
                        "description": f"PersistentVolume '{pv_name}' uses local storage at '{local_path}'. Local volumes are node-specific and may expose host filesystem.",
                        "remediation": "Consider using network-attached storage for better isolation and portability.",
                        "timestamp": timestamp
                    })

            logger.info("PersistentVolume scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning PersistentVolumes: {e}")
        except Exception as e:
            logger.error(f"Error scanning PersistentVolumes: {e}")