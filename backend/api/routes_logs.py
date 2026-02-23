from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
import asyncio
import logging
from typing import Optional

# Kubernetes client for pod logs
try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

from .auth import validate_ws_token
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_logs_router(deps: RouterDeps) -> APIRouter:
    """Pod log fetch + SSE streaming."""
    router = APIRouter()

    @router.get("/pods/{namespace}/{pod_name}/logs")
    async def get_pod_logs(
        namespace: str,
        pod_name: str,
        container: Optional[str] = Query(None, description="Container name (optional)"),
        tail_lines: int = Query(100, description="Number of lines to return", ge=1, le=5000),
        previous: bool = Query(False, description="Get logs from previous container instance")
    ):
        """Get logs for a specific pod"""
        if not K8S_AVAILABLE:
            raise HTTPException(status_code=503, detail="Kubernetes client not available")

        try:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                try:
                    config.load_kube_config()
                except config.ConfigException:
                    raise HTTPException(status_code=503, detail="Could not configure Kubernetes client")

            v1 = client.CoreV1Api()

            try:
                pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            except client.ApiException as e:
                if e.status == 404:
                    raise HTTPException(status_code=404, detail=f"Pod '{pod_name}' not found in namespace '{namespace}'")
                raise HTTPException(status_code=e.status, detail=str(e.reason))

            containers = [c.name for c in pod.spec.containers]
            init_containers = [c.name for c in (pod.spec.init_containers or [])]
            all_containers = containers + init_containers

            target_container = container if container else (containers[0] if containers else None)

            if not target_container:
                raise HTTPException(status_code=400, detail="No containers found in pod")

            if target_container not in all_containers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Container '{target_container}' not found. Available: {', '.join(all_containers)}"
                )

            try:
                logs = v1.read_namespaced_pod_log(
                    name=pod_name,
                    namespace=namespace,
                    container=target_container,
                    tail_lines=tail_lines,
                    previous=previous
                )
            except client.ApiException as e:
                if e.status == 400:
                    logs = f"[No logs available: {e.reason}]"
                else:
                    raise HTTPException(status_code=e.status, detail=str(e.reason))

            return {
                "pod_name": pod_name,
                "namespace": namespace,
                "container": target_container,
                "containers": all_containers,
                "logs": logs,
                "tail_lines": tail_lines,
                "previous": previous
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching pod logs: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/pods/{namespace}/{pod_name}/logs/stream", dependencies=[])
    async def stream_pod_logs(
        request: Request,
        namespace: str,
        pod_name: str,
        container: Optional[str] = Query(None, description="Container name (optional)"),
        tail_lines: int = Query(100, description="Initial number of lines to return", ge=1, le=1000),
        token: Optional[str] = Query(None, description="Auth token (for EventSource which cannot set headers)")
    ):
        """Stream logs for a specific pod (Server-Sent Events)"""
        # SSE auth: check query param token (EventSource API cannot set headers)
        if not validate_ws_token(token):
            raise HTTPException(status_code=401, detail="Invalid or missing auth token")

        if not K8S_AVAILABLE:
            raise HTTPException(status_code=503, detail="Kubernetes client not available")

        try:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                try:
                    config.load_kube_config()
                except config.ConfigException:
                    raise HTTPException(status_code=503, detail="Could not configure Kubernetes client")

            v1 = client.CoreV1Api()

            try:
                pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            except client.ApiException as e:
                if e.status == 404:
                    raise HTTPException(status_code=404, detail=f"Pod '{pod_name}' not found in namespace '{namespace}'")
                raise HTTPException(status_code=e.status, detail=str(e.reason))

            containers = [c.name for c in pod.spec.containers]
            target_container = container if container else (containers[0] if containers else None)

            if not target_container:
                raise HTTPException(status_code=400, detail="No containers found in pod")

            async def log_stream_generator():
                """Generator that yields log lines as SSE events using a thread for blocking I/O"""
                import queue
                import threading

                log_queue = queue.Queue()
                stop_event = threading.Event()

                def watch_logs():
                    """Run blocking kubernetes watch in a separate thread"""
                    try:
                        from kubernetes.watch import Watch
                        w = Watch()

                        for line in w.stream(
                            v1.read_namespaced_pod_log,
                            name=pod_name,
                            namespace=namespace,
                            container=target_container,
                            follow=True,
                            tail_lines=tail_lines,
                            _preload_content=False
                        ):
                            if stop_event.is_set():
                                w.stop()
                                break
                            log_queue.put(('data', line))

                    except client.ApiException as e:
                        log_queue.put(('error', f"[Error: {e.reason}]"))
                    except Exception as e:
                        logger.error(f"Error in log watch thread: {e}")
                        log_queue.put(('error', f"[Error: {str(e)}]"))
                    finally:
                        log_queue.put(('done', None))

                watch_thread = threading.Thread(target=watch_logs, daemon=True)
                watch_thread.start()

                try:
                    while True:
                        try:
                            msg_type, msg_data = await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: log_queue.get(timeout=0.5)
                            )

                            if msg_type == 'done':
                                break
                            elif msg_type == 'error':
                                yield f"data: {msg_data}\n\n"
                                break
                            elif msg_type == 'data':
                                yield f"data: {msg_data}\n\n"

                        except queue.Empty:
                            yield ": heartbeat\n\n"
                            continue

                except asyncio.CancelledError:
                    pass
                except GeneratorExit:
                    pass
                finally:
                    stop_event.set()

            return StreamingResponse(
                log_stream_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error setting up log stream: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
