from fastapi import APIRouter, HTTPException
import logging
import traceback

from models.models import (
    PodFailureReport, PodFailureResponse, PodStatusUpdate,
)
from services.prometheus_metrics import POD_FAILURES_TOTAL
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_pod_router(deps: RouterDeps) -> APIRouter:
    """Pod CRUD, status, history, retry-solution, delete-record, dismiss-deleted, retention settings."""
    router = APIRouter()
    db = deps.db
    solution_engine = deps.solution_engine
    websocket_manager = deps.websocket_manager
    notification_service = deps.notification_service

    @router.post("/pods/failed", response_model=PodFailureResponse, dependencies=[])
    async def report_failed_pod(report: PodFailureReport):
        """Receive failed pod report from agent"""
        logger.info(f"Received failure report for pod: {report.namespace}/{report.pod_name}")

        try:
            if not report.pod_name or not report.namespace:
                raise HTTPException(status_code=400, detail="Pod name and namespace are required")

            pod_context = {
                "name": report.pod_name,
                "namespace": report.namespace,
                "image": getattr(report, 'image', 'Unknown')
            }

            logger.info(f"Generating solution for pod {report.namespace}/{report.pod_name}, failure reason: {report.failure_reason}")
            solution = await solution_engine.get_solution(
                reason=report.failure_reason,
                message=report.failure_message,
                events=report.events,
                container_statuses=report.container_statuses,
                pod_context=pod_context,
                use_llm=False
            )

            response = PodFailureResponse(
                **report.dict(),
                solution=solution,
                timestamp=report.creation_timestamp
            )

            logger.info(f"Saving pod failure to database: {report.namespace}/{report.pod_name}")
            pod_id = await db.save_pod_failure(response)
            response.id = pod_id

            logger.info(f"Broadcasting pod failure via WebSocket: {report.namespace}/{report.pod_name}")
            await websocket_manager.broadcast_pod_failure(response)

            if notification_service:
                try:
                    await notification_service.send_pod_failure_notification(response)
                except Exception as notif_error:
                    logger.error(f"Error sending notifications: {notif_error}")

            POD_FAILURES_TOTAL.labels(
                namespace=report.namespace,
                reason=report.failure_reason,
            ).inc()

            logger.info(f"Successfully processed failed pod: {report.namespace}/{report.pod_name}")
            return response

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Failed to process pod failure report for {report.namespace}/{report.pod_name}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Error details: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error while processing pod failure: {str(e)}"
            )

    @router.get("/pods/failed", response_model=list[PodFailureResponse])
    async def get_failed_pods():
        """Get all failed pods from database"""
        try:
            return await db.get_pod_failures()
        except Exception as e:
            logger.error(f"Error getting pod failures: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/pods/ignored", response_model=list[PodFailureResponse])
    async def get_ignored_pods():
        """Get all ignored pods from database"""
        try:
            return await db.get_pod_failures(include_dismissed=True, dismissed_only=True)
        except Exception as e:
            logger.error(f"Error getting ignored pods: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/pods/failed/{pod_id}")
    async def dismiss_pod_failure(pod_id: int):
        """Mark a pod failure as resolved/dismissed"""
        try:
            pod_failure = await db.get_pod_failure_by_id(pod_id)
            await db.dismiss_pod_failure(pod_id)

            if pod_failure and notification_service:
                await notification_service.send_pod_resolved_notification(
                    namespace=pod_failure.namespace,
                    pod_name=pod_failure.pod_name
                )

            return {"message": "Pod failure dismissed"}
        except Exception as e:
            logger.error(f"Error dismissing pod failure: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/pods/ignored/{pod_id}/restore")
    async def restore_pod_failure(pod_id: int):
        """Restore/un-ignore a dismissed pod failure"""
        try:
            updated = await db.update_pod_status(pod_id, 'new')
            if updated:
                await websocket_manager.broadcast_pod_status_change(updated)
            return {"message": "Pod failure restored"}
        except Exception as e:
            logger.error(f"Error restoring pod failure: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.patch("/pods/failed/{pod_id}/status", response_model=PodFailureResponse)
    async def update_pod_status(pod_id: int, request: PodStatusUpdate):
        """Update the status of a pod failure (acknowledge, resolve, ignore)"""
        valid_statuses = {'new', 'investigating', 'resolved', 'ignored'}
        if request.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

        valid_transitions = {
            'new': {'investigating', 'ignored'},
            'investigating': {'ignored'},
            'ignored': {'new'},
            'resolved': set(),
        }

        try:
            pod_failure = await db.get_pod_failure_by_id(pod_id)
            if not pod_failure:
                raise HTTPException(status_code=404, detail="Pod failure not found")

            current_status = pod_failure.status
            if request.status not in valid_transitions.get(current_status, set()):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot transition from '{current_status}' to '{request.status}'"
                )

            updated = await db.update_pod_status(pod_id, request.status, request.resolution_note)

            if updated:
                await websocket_manager.broadcast_pod_status_change(updated)

                if request.status in ('resolved', 'ignored') and notification_service:
                    await notification_service.send_pod_resolved_notification(
                        namespace=updated.namespace,
                        pod_name=updated.pod_name
                    )

            return updated

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating pod status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/pods/history", response_model=list[PodFailureResponse])
    async def get_pod_history():
        """Get resolved pod failures (history)"""
        try:
            return await db.get_pod_failures(status_filter=['resolved'])
        except Exception as e:
            logger.error(f"Error getting pod history: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/pods/failed/{pod_id}/retry-solution", response_model=PodFailureResponse)
    async def retry_ai_solution(pod_id: int):
        """Retry generating AI solution for a pod failure"""
        try:
            pod_failure = await db.get_pod_failure_by_id(pod_id)
            if not pod_failure:
                raise HTTPException(status_code=404, detail="Pod failure not found")

            logger.info(f"Retrying AI solution for pod: {pod_failure.namespace}/{pod_failure.pod_name}")

            pod_context = {
                "name": pod_failure.pod_name,
                "namespace": pod_failure.namespace,
                "image": "Unknown"
            }

            from models.models import ContainerStatus, PodEvent
            container_statuses = [ContainerStatus(**s) if isinstance(s, dict) else s for s in pod_failure.container_statuses]
            events = [PodEvent(**e) if isinstance(e, dict) else e for e in pod_failure.events]

            solution = await solution_engine.get_solution(
                reason=pod_failure.failure_reason,
                message=pod_failure.failure_message,
                events=events,
                container_statuses=container_statuses,
                pod_context=pod_context
            )

            await db.update_pod_solution(pod_id, solution)
            updated_pod = await db.get_pod_failure_by_id(pod_id)
            await websocket_manager.broadcast_pod_solution_updated(updated_pod)

            logger.info(f"Successfully regenerated AI solution for pod: {pod_failure.namespace}/{pod_failure.pod_name}")
            return updated_pod

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Failed to retry AI solution for pod {pod_id}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Error details: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/pods/records/{pod_id}")
    async def delete_pod_record(pod_id: int):
        """Permanently delete a resolved or ignored pod failure record"""
        try:
            pod_failure = await db.get_pod_failure_by_id(pod_id)
            if not pod_failure:
                raise HTTPException(status_code=404, detail="Pod failure not found")

            if pod_failure.status not in ('resolved', 'ignored'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Can only delete resolved or ignored records (current status: {pod_failure.status})"
                )

            deleted = await db.delete_pod_failure(pod_id)
            if not deleted:
                raise HTTPException(status_code=500, detail="Failed to delete record")

            await websocket_manager.broadcast_pod_record_deleted(pod_id)

            logger.info(f"Deleted pod record: {pod_failure.namespace}/{pod_failure.pod_name} (id={pod_id})")
            return {"message": "Pod record deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting pod record: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/pods/dismiss-deleted", dependencies=[])
    async def dismiss_deleted_pod(request: dict):
        """Auto-resolve pods when they recover or are deleted from Kubernetes"""
        try:
            namespace = request.get("namespace")
            pod_name = request.get("pod_name")

            if not namespace or not pod_name:
                raise HTTPException(status_code=400, detail="namespace and pod_name required")

            resolved_pods = await db.dismiss_deleted_pod(namespace, pod_name)

            for pod in resolved_pods:
                await websocket_manager.broadcast_pod_status_change(pod)

            if not resolved_pods:
                await websocket_manager.broadcast_pod_deleted(namespace, pod_name)

            if notification_service:
                await notification_service.send_pod_resolved_notification(
                    namespace=namespace,
                    pod_name=pod_name
                )

            logger.info(f"Auto-resolved pod: {namespace}/{pod_name} ({len(resolved_pods)} records)")
            return {"message": "Pod auto-resolved"}
        except Exception as e:
            logger.error(f"Error auto-resolving pod: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/pods/{namespace}/{pod_name}/manifest")
    async def get_pod_manifest(namespace: str, pod_name: str):
        """Get pod manifest YAML from Kubernetes API"""
        try:
            return {"error": "Pod manifest retrieval not implemented yet"}
        except Exception as e:
            logger.error(f"Error getting pod manifest: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/settings/history-retention")
    async def get_history_retention():
        """Get the history auto-delete retention setting (minutes, 0 = disabled)"""
        try:
            value = await db.get_app_setting("history_retention_minutes")
            return {"minutes": int(value) if value else 0}
        except Exception as e:
            logger.error(f"Error getting history retention: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/admin/settings/history-retention")
    async def set_history_retention(request: dict):
        """Set the history auto-delete retention (minutes). 0 = disabled. Min 1, max 43200 (30 days)."""
        try:
            minutes = request.get("minutes", 0)
            if not isinstance(minutes, int) or minutes < 0:
                raise HTTPException(status_code=400, detail="minutes must be a non-negative integer")
            if minutes > 43200:
                raise HTTPException(status_code=400, detail="minutes must not exceed 43200 (30 days)")
            await db.set_app_setting("history_retention_minutes", str(minutes))
            logger.info(f"History retention set to {minutes} minutes")
            return {"minutes": minutes}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error setting history retention: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/settings/ignored-retention")
    async def get_ignored_retention():
        """Get the ignored pods auto-delete retention setting (minutes, 0 = disabled)"""
        try:
            value = await db.get_app_setting("ignored_retention_minutes")
            return {"minutes": int(value) if value else 0}
        except Exception as e:
            logger.error(f"Error getting ignored retention: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/admin/settings/ignored-retention")
    async def set_ignored_retention(request: dict):
        """Set the ignored pods auto-delete retention (minutes). 0 = disabled. Min 1, max 43200 (30 days)."""
        try:
            minutes = request.get("minutes", 0)
            if not isinstance(minutes, int) or minutes < 0:
                raise HTTPException(status_code=400, detail="minutes must be a non-negative integer")
            if minutes > 43200:
                raise HTTPException(status_code=400, detail="minutes must not exceed 43200 (30 days)")
            await db.set_app_setting("ignored_retention_minutes", str(minutes))
            logger.info(f"Ignored retention set to {minutes} minutes")
            return {"minutes": minutes}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error setting ignored retention: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
