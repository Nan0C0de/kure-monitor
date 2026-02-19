import asyncio
import logging
import time
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable, Awaitable, TYPE_CHECKING

from kubernetes import watch
from kubernetes.client.rest import ApiException

if TYPE_CHECKING:
    from services.security_scanner import SecurityScanner

logger = logging.getLogger(__name__)


class WatchManager:
    """Manages Kubernetes resource watches and deletion tracking."""

    def __init__(self, scanner: 'SecurityScanner'):
        self.scanner = scanner

    async def handle_resource_deletion(self, resource_type: str, namespace: str, resource_name: str):
        """Handle deletion of a resource - remove its findings from backend"""
        resource_key = (resource_type, namespace, resource_name)

        async with self.scanner._lock:
            if resource_key in self.scanner.tracked_resources:
                self.scanner.tracked_resources.discard(resource_key)
                logger.info(f"Resource deleted: {resource_type}/{namespace}/{resource_name} - removing findings")
                await self.scanner.backend_client.delete_findings_by_resource(resource_type, namespace, resource_name)

    def _create_sync_watch(self, api_method, resource_type: str,
                           timeout_seconds: int = 0, handle_403: bool = False):
        """Create a synchronous watch function for a resource type.

        Returns a function(callback) that runs the watch loop forever,
        calling callback(event) for each event.
        """
        def watch_sync(callback):
            while True:
                try:
                    logger.info(f"Starting {resource_type} watch (sync thread)")
                    w = watch.Watch()
                    for event in w.stream(api_method, timeout_seconds=timeout_seconds):
                        try:
                            callback(event)
                        except Exception as cb_err:
                            logger.error(f"{resource_type} watch callback error: {cb_err}")
                except ApiException as e:
                    if handle_403 and e.status == 403:
                        logger.warning(f"{resource_type} watch forbidden (missing RBAC permissions) - disabling watch")
                        return
                    logger.error(f"{resource_type} watch API error: {e}, restarting...")
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"{resource_type} watch error: {e}, restarting...")
                    logger.error(traceback.format_exc())
                    time.sleep(5)
        return watch_sync

    async def create_namespaced_watch(
        self,
        resource_type: str,
        api_method,
        thread_prefix: str,
        scan_fn: Optional[Callable] = None,
        timeout_seconds: int = 0,
        handle_403: bool = False,
    ):
        """Create and run a namespaced resource watch.

        Args:
            resource_type: e.g. "Deployment", "Service"
            api_method: K8s API list method (e.g. apps_v1.list_deployment_for_all_namespaces)
            thread_prefix: Thread name prefix for the watch thread
            scan_fn: Async function(resource) to call on ADDED/MODIFIED. If None, only deletions are handled.
            timeout_seconds: Watch stream timeout
            handle_403: If True, silently stop on 403 forbidden
        """
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        sync_watch = self._create_sync_watch(api_method, resource_type, timeout_seconds, handle_403)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=thread_prefix)
        executor.submit(sync_watch, on_event)

        logger.info(f"{resource_type} watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                resource = event['object']
                namespace = resource.metadata.namespace

                await self.scanner.exclusion_mgr.refresh_excluded_namespaces()

                if self.scanner.exclusion_mgr.is_namespace_excluded(namespace):
                    continue

                if event['type'] == 'DELETED':
                    await self.handle_resource_deletion(resource_type, namespace, resource.metadata.name)
                elif event['type'] in ['ADDED', 'MODIFIED'] and scan_fn:
                    logger.info(f"Real-time {resource_type} event: {event['type']} {namespace}/{resource.metadata.name}")
                    await scan_fn(resource)
            except Exception as e:
                logger.error(f"{resource_type} watch consumer error: {e}")
                await asyncio.sleep(1)

    async def create_cluster_watch(
        self,
        resource_type: str,
        api_method,
        thread_prefix: str,
        scan_fn: Optional[Callable] = None,
        skip_system_prefix: bool = False,
    ):
        """Create and run a cluster-scoped resource watch (e.g. ClusterRole).

        Args:
            resource_type: e.g. "ClusterRole"
            api_method: K8s API list method
            thread_prefix: Thread name prefix
            scan_fn: Async function(resource) to call on ADDED/MODIFIED
            skip_system_prefix: If True, skip resources with 'system:' name prefix
        """
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        sync_watch = self._create_sync_watch(api_method, resource_type)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=thread_prefix)
        executor.submit(sync_watch, on_event)

        logger.info(f"{resource_type} watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                resource = event['object']

                if skip_system_prefix and resource.metadata.name.startswith('system:'):
                    continue

                if event['type'] == 'DELETED':
                    await self.handle_resource_deletion(resource_type, "cluster-wide", resource.metadata.name)
                elif event['type'] in ['ADDED', 'MODIFIED'] and scan_fn:
                    logger.info(f"Real-time {resource_type} event: {event['type']} {resource.metadata.name}")
                    await scan_fn(resource)
            except Exception as e:
                logger.error(f"{resource_type} watch consumer error: {e}")
                await asyncio.sleep(1)

    async def create_deletion_only_watch(
        self,
        resource_type: str,
        api_method,
        thread_prefix: str,
        namespaced: bool = True,
    ):
        """Create a watch that only tracks resource deletions.

        Args:
            resource_type: e.g. "DaemonSet", "StatefulSet", "Namespace"
            api_method: K8s API list method
            thread_prefix: Thread name prefix
            namespaced: If True, check namespace exclusion and use resource namespace.
                        If False (e.g. Namespace), use the resource name as the namespace key.
        """
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        sync_watch = self._create_sync_watch(api_method, resource_type)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=thread_prefix)
        executor.submit(sync_watch, on_event)

        logger.info(f"{resource_type} watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event['type'] == 'DELETED':
                    resource = event['object']
                    if namespaced:
                        namespace = resource.metadata.namespace
                        if not self.scanner.exclusion_mgr.is_namespace_excluded(namespace):
                            await self.handle_resource_deletion(resource_type, namespace, resource.metadata.name)
                    else:
                        ns_name = resource.metadata.name
                        if not self.scanner.exclusion_mgr.is_namespace_excluded(ns_name):
                            await self.handle_resource_deletion(resource_type, ns_name, ns_name)
            except Exception as e:
                logger.error(f"{resource_type} watch consumer error: {e}")
                await asyncio.sleep(1)

    async def watch_pods(self):
        """Watch for pod changes in real-time using thread + queue."""
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        sync_watch = self._create_sync_watch(
            self.scanner.v1.list_pod_for_all_namespaces, "Pod", timeout_seconds=300
        )
        watch_thread = threading.Thread(
            target=sync_watch, args=(on_event,), daemon=True, name="pod-watch-thread"
        )
        watch_thread.start()
        logger.info(f"Pod watch thread started: {watch_thread.name}, alive={watch_thread.is_alive()}")

        logger.info("Pod watch consumer loop starting...")
        while True:
            try:
                event = await event_queue.get()
                pod = event['object']
                namespace = pod.metadata.namespace

                await self.scanner.exclusion_mgr.refresh_excluded_namespaces()

                if self.scanner.exclusion_mgr.is_namespace_excluded(namespace):
                    continue

                if event['type'] == 'DELETED':
                    await self.handle_resource_deletion("Pod", namespace, pod.metadata.name)
                elif event['type'] in ['ADDED', 'MODIFIED']:
                    logger.info(f"Real-time pod event: {event['type']} {namespace}/{pod.metadata.name}")
                    await self.scanner.pod_scanner.scan_single_pod(pod)
            except Exception as e:
                logger.error(f"Pod watch consumer error: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(1)
