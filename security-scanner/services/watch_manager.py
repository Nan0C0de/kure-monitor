import asyncio
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, List, TYPE_CHECKING

from kubernetes import watch
from kubernetes.client.rest import ApiException

if TYPE_CHECKING:
    from services.security_scanner import SecurityScanner

logger = logging.getLogger(__name__)


@dataclass
class _ProducerRegistration:
    """A tracked watch producer: its executor, the submitted future, and the
    factory needed to resubmit if the producer thread dies unexpectedly."""

    resource_type: str
    thread_prefix: str
    executor: ThreadPoolExecutor
    sync_watch: Callable
    on_event: Callable
    future: Future


class WatchManager:
    """Manages Kubernetes resource watches and deletion tracking."""

    # Interval for the liveness check task that detects dead producer threads.
    LIVENESS_CHECK_INTERVAL = 30.0

    def __init__(self, scanner: "SecurityScanner"):
        self.scanner = scanner
        # All executors created by this manager, tracked for shutdown.
        self._executors: List[ThreadPoolExecutor] = []
        # All registered producers, tracked for the liveness checker.
        self._producers: List[_ProducerRegistration] = []
        self._shutdown = False

    async def handle_resource_deletion(
        self, resource_type: str, namespace: str, resource_name: str
    ):
        """Handle deletion of a resource - remove its findings from backend"""
        resource_key = (resource_type, namespace, resource_name)

        async with self.scanner._lock:
            if resource_key in self.scanner.tracked_resources:
                self.scanner.tracked_resources.discard(resource_key)
                logger.info(
                    f"Resource deleted: {resource_type}/{namespace}/{resource_name} - removing findings"
                )
                await self.scanner.backend_client.delete_findings_by_resource(
                    resource_type, namespace, resource_name
                )

    def _create_sync_watch(
        self,
        api_method,
        resource_type: str,
        timeout_seconds: int = 0,
        handle_403: bool = False,
    ):
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
                            logger.error(
                                f"{resource_type} watch callback error: {cb_err}"
                            )
                except ApiException as e:
                    if handle_403 and e.status == 403:
                        logger.warning(
                            f"{resource_type} watch forbidden (missing RBAC permissions) - disabling watch"
                        )
                        return
                    logger.error(f"{resource_type} watch API error: {e}, restarting...")
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"{resource_type} watch error: {e}, restarting...")
                    logger.error(traceback.format_exc())
                    time.sleep(5)

        return watch_sync

    def _start_producer(
        self,
        resource_type: str,
        thread_prefix: str,
        api_method,
        on_event: Callable,
        timeout_seconds: int = 0,
        handle_403: bool = False,
    ) -> _ProducerRegistration:
        """Create an executor and submit the sync watch producer.

        Tracked on ``self._producers`` and ``self._executors`` so the liveness
        check and shutdown can find them.
        """
        sync_watch = self._create_sync_watch(
            api_method, resource_type, timeout_seconds, handle_403
        )
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=thread_prefix)
        future = executor.submit(sync_watch, on_event)
        reg = _ProducerRegistration(
            resource_type=resource_type,
            thread_prefix=thread_prefix,
            executor=executor,
            sync_watch=sync_watch,
            on_event=on_event,
            future=future,
        )
        self._executors.append(executor)
        self._producers.append(reg)
        return reg

    async def liveness_check_loop(self):
        """Periodic asyncio task that ensures each producer thread is alive.

        If a producer future has completed (which for an infinite watch loop
        means it raised), log ERROR with the exception and resubmit on the
        same executor. Cleanly stops on cancellation.
        """
        try:
            while not self._shutdown:
                await asyncio.sleep(self.LIVENESS_CHECK_INTERVAL)
                for reg in self._producers:
                    if reg.future.done():
                        exc = None
                        try:
                            exc = reg.future.exception()
                        except Exception:
                            exc = None
                        if exc is not None:
                            logger.error(
                                "Watch producer for %s died with exception: %r — restarting",
                                reg.resource_type,
                                exc,
                            )
                        else:
                            logger.error(
                                "Watch producer for %s exited unexpectedly — restarting",
                                reg.resource_type,
                            )
                        if self._shutdown:
                            return
                        try:
                            reg.future = reg.executor.submit(
                                reg.sync_watch, reg.on_event
                            )
                        except RuntimeError as e:
                            # Executor shutdown after we observed dead future.
                            logger.warning(
                                "Could not restart producer for %s: %s",
                                reg.resource_type,
                                e,
                            )
        except asyncio.CancelledError:
            raise

    async def shutdown(self):
        """Shutdown all producer executors.

        K8s watch HTTP streams won't honor cancel directly (they're blocked
        in network I/O) but ``cancel_futures=True`` prevents any pending
        submissions from running. The consumer asyncio tasks get cancelled
        by their owners, so the process can exit.
        """
        self._shutdown = True
        for executor in self._executors:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logger.warning(f"Error shutting down watch executor: {e}")

    async def create_namespaced_watch(
        self,
        resource_type: str,
        api_method,
        thread_prefix: str,
        scan_fn: Optional[Callable] = None,
        timeout_seconds: int = 0,
        handle_403: bool = False,
    ):
        """Create and run a namespaced resource watch."""
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        self._start_producer(
            resource_type,
            thread_prefix,
            api_method,
            on_event,
            timeout_seconds=timeout_seconds,
            handle_403=handle_403,
        )

        logger.info(f"{resource_type} watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                resource = event["object"]
                namespace = resource.metadata.namespace

                await self.scanner.exclusion_mgr.refresh_excluded_namespaces()

                if self.scanner.exclusion_mgr.is_namespace_excluded(namespace):
                    continue

                if event["type"] == "DELETED":
                    await self.handle_resource_deletion(
                        resource_type, namespace, resource.metadata.name
                    )
                elif event["type"] in ["ADDED", "MODIFIED"] and scan_fn:
                    logger.info(
                        f"Real-time {resource_type} event: {event['type']} {namespace}/{resource.metadata.name}"
                    )
                    await scan_fn(resource)
            except asyncio.CancelledError:
                raise
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
        """Create and run a cluster-scoped resource watch (e.g. ClusterRole)."""
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        self._start_producer(resource_type, thread_prefix, api_method, on_event)

        logger.info(f"{resource_type} watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                resource = event["object"]

                if skip_system_prefix and resource.metadata.name.startswith("system:"):
                    continue

                if event["type"] == "DELETED":
                    await self.handle_resource_deletion(
                        resource_type, "cluster-wide", resource.metadata.name
                    )
                elif event["type"] in ["ADDED", "MODIFIED"] and scan_fn:
                    logger.info(
                        f"Real-time {resource_type} event: {event['type']} {resource.metadata.name}"
                    )
                    await scan_fn(resource)
            except asyncio.CancelledError:
                raise
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
        """Create a watch that only tracks resource deletions."""
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        self._start_producer(resource_type, thread_prefix, api_method, on_event)

        logger.info(f"{resource_type} watch consumer started")
        while True:
            try:
                event = await event_queue.get()
                if event["type"] == "DELETED":
                    resource = event["object"]
                    if namespaced:
                        namespace = resource.metadata.namespace
                        if not self.scanner.exclusion_mgr.is_namespace_excluded(
                            namespace
                        ):
                            await self.handle_resource_deletion(
                                resource_type, namespace, resource.metadata.name
                            )
                    else:
                        ns_name = resource.metadata.name
                        if not self.scanner.exclusion_mgr.is_namespace_excluded(
                            ns_name
                        ):
                            await self.handle_resource_deletion(
                                resource_type, ns_name, ns_name
                            )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"{resource_type} watch consumer error: {e}")
                await asyncio.sleep(1)

    async def watch_pods(self):
        """Watch for pod changes in real-time.

        Uses the same ThreadPoolExecutor-backed producer pattern as the other
        watches, so the liveness checker and ``shutdown()`` can manage it
        uniformly. The previous daemon ``threading.Thread`` could die silently
        on any non-ApiException and leave the consumer stalled on
        ``event_queue.get()``.
        """
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        self._start_producer(
            "Pod",
            "pod-watch",
            self.scanner.v1.list_pod_for_all_namespaces,
            on_event,
            timeout_seconds=300,
        )

        logger.info("Pod watch consumer loop starting...")
        while True:
            try:
                event = await event_queue.get()
                pod = event["object"]
                namespace = pod.metadata.namespace

                await self.scanner.exclusion_mgr.refresh_excluded_namespaces()

                if self.scanner.exclusion_mgr.is_namespace_excluded(namespace):
                    continue

                # Skip mirror pods (temporary test pods created by Kure)
                labels = pod.metadata.labels or {}
                if labels.get("kure.io/mirror") == "true":
                    continue

                if event["type"] == "DELETED":
                    await self.handle_resource_deletion(
                        "Pod", namespace, pod.metadata.name
                    )
                elif event["type"] in ["ADDED", "MODIFIED"]:
                    logger.info(
                        f"Real-time pod event: {event['type']} {namespace}/{pod.metadata.name}"
                    )
                    await self.scanner.pod_scanner.scan_single_pod(pod)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Pod watch consumer error: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(1)
