from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import difflib
import logging
import traceback
import asyncio
from typing import Optional

# Kubernetes client for pod logs
try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

from models.models import (
    PodFailureReport, PodFailureResponse, PodStatusUpdate,
    SecurityFindingReport, SecurityFindingResponse,
    ExcludedNamespace, ExcludedNamespaceResponse,
    ExcludedPod, ExcludedPodResponse,
    ExcludedRule, ExcludedRuleResponse,
    TrustedRegistry, TrustedRegistryResponse,
    NotificationSettingCreate, NotificationSettingResponse,
    ClusterMetrics, PodMetricsHistory, PodMetricsPoint,
    LLMConfigCreate, LLMConfigResponse, LLMConfigStatus
)
from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager
from services.metrics_history import metrics_history_store, format_cpu, format_memory
from services.prometheus_metrics import (
    POD_FAILURES_TOTAL,
    SECURITY_FINDINGS_TOTAL,
    SECURITY_SCAN_DURATION_SECONDS,
)

logger = logging.getLogger(__name__)

# Store latest cluster metrics in memory (no database needed for current values)
latest_cluster_metrics: Optional[dict] = None

def create_api_router(db: Database, solution_engine: SolutionEngine, websocket_manager: WebSocketManager, notification_service=None) -> APIRouter:
    """Create and configure the API router"""
    router = APIRouter(prefix="/api")

    @router.get("/config")
    async def get_config():
        """Get application configuration status"""
        return {
            "ai_enabled": solution_engine.llm_provider is not None,
            "ai_provider": solution_engine.llm_provider.provider_name if solution_engine.llm_provider else None
        }

    @router.post("/pods/failed", response_model=PodFailureResponse)
    async def report_failed_pod(report: PodFailureReport):
        """Receive failed pod report from agent"""
        logger.info(f"Received failure report for pod: {report.namespace}/{report.pod_name}")
        
        try:
            # Validate required fields
            if not report.pod_name or not report.namespace:
                raise HTTPException(status_code=400, detail="Pod name and namespace are required")
            
            # Generate solution
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
                use_llm=False  # AI generates on-demand when user expands the pod
            )

            # Create response
            response = PodFailureResponse(
                **report.dict(),
                solution=solution,
                timestamp=report.creation_timestamp
            )

            # Save to database and get the ID
            logger.info(f"Saving pod failure to database: {report.namespace}/{report.pod_name}")
            pod_id = await db.save_pod_failure(response)

            # Update response with the database ID
            response.id = pod_id

            # Notify frontend via WebSocket
            logger.info(f"Broadcasting pod failure via WebSocket: {report.namespace}/{report.pod_name}")
            await websocket_manager.broadcast_pod_failure(response)

            # Send notifications to configured providers
            if notification_service:
                try:
                    await notification_service.send_pod_failure_notification(response)
                except Exception as notif_error:
                    logger.error(f"Error sending notifications: {notif_error}")
                    # Don't fail the request if notifications fail

            # Record Prometheus metric
            POD_FAILURES_TOTAL.labels(
                namespace=report.namespace,
                reason=report.failure_reason,
            ).inc()

            logger.info(f"Successfully processed failed pod: {report.namespace}/{report.pod_name}")
            return response

        except HTTPException:
            # Re-raise HTTP exceptions as-is
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
            # Get pod details before dismissing for notification
            pod_failure = await db.get_pod_failure_by_id(pod_id)

            await db.dismiss_pod_failure(pod_id)

            # Send resolved notification if we have pod details and notification service
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

                # Send resolved notification when pod is resolved or ignored
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
            # Get the pod failure from database
            pod_failure = await db.get_pod_failure_by_id(pod_id)
            if not pod_failure:
                raise HTTPException(status_code=404, detail="Pod failure not found")

            logger.info(f"Retrying AI solution for pod: {pod_failure.namespace}/{pod_failure.pod_name}")

            # Generate new solution
            pod_context = {
                "name": pod_failure.pod_name,
                "namespace": pod_failure.namespace,
                "image": "Unknown"
            }

            # Convert container_statuses and events from dicts to model objects for solution engine
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

            # Update solution in database
            await db.update_pod_solution(pod_id, solution)

            # Get updated pod failure
            updated_pod = await db.get_pod_failure_by_id(pod_id)

            # Broadcast update via WebSocket
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

            # Broadcast deletion so frontend removes it from the list
            await websocket_manager.broadcast_pod_record_deleted(pod_id)

            logger.info(f"Deleted pod record: {pod_failure.namespace}/{pod_failure.pod_name} (id={pod_id})")
            return {"message": "Pod record deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting pod record: {e}")
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

    @router.post("/pods/dismiss-deleted")
    async def dismiss_deleted_pod(request: dict):
        """Auto-resolve pods when they recover or are deleted from Kubernetes"""
        try:
            namespace = request.get("namespace")
            pod_name = request.get("pod_name")

            if not namespace or not pod_name:
                raise HTTPException(status_code=400, detail="namespace and pod_name required")

            resolved_pods = await db.dismiss_deleted_pod(namespace, pod_name)

            # Broadcast status change for each auto-resolved pod so frontend moves them to History
            for pod in resolved_pods:
                await websocket_manager.broadcast_pod_status_change(pod)

            # Fallback: also broadcast pod_deleted for frontend cleanup if no DB records matched
            if not resolved_pods:
                await websocket_manager.broadcast_pod_deleted(namespace, pod_name)

            # Send resolved notification
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
            # This would require Kubernetes client access from backend
            # For now, return placeholder - this should be implemented if needed
            return {"error": "Pod manifest retrieval not implemented yet"}
        except Exception as e:
            logger.error(f"Error getting pod manifest: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Security findings endpoints
    @router.post("/security/findings", response_model=SecurityFindingResponse)
    async def report_security_finding(report: SecurityFindingReport):
        """Receive security finding report from scanner agent"""
        logger.info(f"Received security finding for {report.resource_type}/{report.namespace}/{report.resource_name}")

        try:
            # Validate required fields
            if not report.resource_name or not report.namespace:
                raise HTTPException(status_code=400, detail="Resource name and namespace are required")

            # Create response
            response = SecurityFindingResponse(
                **report.dict()
            )

            # Save to database
            logger.info(f"Saving security finding to database: {report.resource_type}/{report.namespace}/{report.resource_name}")
            finding_id, is_new = await db.save_security_finding(response)
            response.id = finding_id

            # Only notify frontend via WebSocket if this is a NEW finding (not an update)
            if is_new:
                logger.info(f"Broadcasting NEW security finding via WebSocket: {report.resource_type}/{report.namespace}/{report.resource_name}")
                await websocket_manager.broadcast_security_finding(response)
            else:
                logger.info(f"Updated existing security finding (not broadcasting): {report.resource_type}/{report.namespace}/{report.resource_name}")

            # Record Prometheus metric
            SECURITY_FINDINGS_TOTAL.labels(severity=report.severity).inc()

            logger.info(f"Successfully processed security finding: {report.resource_type}/{report.namespace}/{report.resource_name}")
            return response

        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Failed to process security finding for {report.namespace}/{report.resource_name}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Error details: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error while processing security finding: {str(e)}"
            )

    @router.get("/security/findings", response_model=list[SecurityFindingResponse])
    async def get_security_findings():
        """Get all security findings from database"""
        try:
            return await db.get_security_findings()
        except Exception as e:
            logger.error(f"Error getting security findings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/security/findings/{finding_id}")
    async def dismiss_security_finding(finding_id: int):
        """Mark a security finding as dismissed"""
        try:
            await db.dismiss_security_finding(finding_id)
            return {"message": "Security finding dismissed"}
        except Exception as e:
            logger.error(f"Error dismissing security finding: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/security/findings/{finding_id}/restore")
    async def restore_security_finding(finding_id: int):
        """Restore a dismissed security finding"""
        try:
            await db.restore_security_finding(finding_id)
            return {"message": "Security finding restored"}
        except Exception as e:
            logger.error(f"Error restoring security finding: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/security/scan/clear")
    async def clear_security_findings():
        """Clear all security findings (for new scans)"""
        try:
            await db.clear_security_findings()
            return {"message": "Security findings cleared"}
        except Exception as e:
            logger.error(f"Error clearing security findings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/security/findings/resource/{resource_type}/{namespace}/{resource_name}")
    async def delete_findings_by_resource(resource_type: str, namespace: str, resource_name: str):
        """Delete all security findings for a specific resource (when resource is deleted from cluster)"""
        try:
            count, deleted_findings = await db.delete_findings_by_resource(resource_type, namespace, resource_name)
            logger.info(f"Deleted {count} findings for {resource_type}/{namespace}/{resource_name}")

            # Broadcast each deleted finding to connected clients
            for finding in deleted_findings:
                await websocket_manager.broadcast_security_finding_deleted(finding)

            return {"message": f"Deleted {count} findings for resource", "count": count}
        except Exception as e:
            logger.error(f"Error deleting findings by resource: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Security fix endpoints
    def compute_manifest_diff(original: str, fixed: str) -> list:
        """Compute a structured diff between original and fixed manifests"""
        original_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)
        diff_result = []

        matcher = difflib.SequenceMatcher(None, original_lines, fixed_lines)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for line in original_lines[i1:i2]:
                    diff_result.append({
                        'content': line.rstrip('\n'),
                        'type': 'unchanged'
                    })
            elif tag == 'replace':
                for line in original_lines[i1:i2]:
                    diff_result.append({
                        'content': line.rstrip('\n'),
                        'type': 'removed'
                    })
                for line in fixed_lines[j1:j2]:
                    diff_result.append({
                        'content': line.rstrip('\n'),
                        'type': 'added'
                    })
            elif tag == 'delete':
                for line in original_lines[i1:i2]:
                    diff_result.append({
                        'content': line.rstrip('\n'),
                        'type': 'removed'
                    })
            elif tag == 'insert':
                for line in fixed_lines[j1:j2]:
                    diff_result.append({
                        'content': line.rstrip('\n'),
                        'type': 'added'
                    })

        return diff_result

    @router.get("/security/findings/{finding_id}/manifest")
    async def get_security_finding_manifest(finding_id: int):
        """Get the manifest and metadata for a security finding"""
        try:
            finding = await db.get_security_finding_by_id(finding_id)
            if not finding:
                raise HTTPException(status_code=404, detail="Finding not found")
            return {
                "id": finding.id,
                "manifest": finding.manifest,
                "resource_type": finding.resource_type,
                "resource_name": finding.resource_name,
                "namespace": finding.namespace,
                "title": finding.title,
                "description": finding.description,
                "remediation": finding.remediation,
                "severity": finding.severity
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting security finding manifest: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/security/findings/{finding_id}/fix")
    async def generate_security_fix(finding_id: int):
        """Generate an AI-powered security fix for a finding"""
        try:
            finding = await db.get_security_finding_by_id(finding_id)
            if not finding:
                raise HTTPException(status_code=404, detail="Finding not found")

            if not finding.manifest:
                return {
                    "finding_id": finding_id,
                    "original_manifest": "",
                    "fixed_manifest": "",
                    "diff": [],
                    "explanation": finding.remediation,
                    "is_fallback": True
                }

            result = await solution_engine.generate_security_fix(
                manifest=finding.manifest,
                title=finding.title,
                description=finding.description,
                remediation=finding.remediation,
                resource_type=finding.resource_type,
                resource_name=finding.resource_name,
                namespace=finding.namespace,
                severity=finding.severity
            )

            diff = []
            if result['fixed_manifest']:
                diff = compute_manifest_diff(finding.manifest, result['fixed_manifest'])

            return {
                "finding_id": finding_id,
                "original_manifest": finding.manifest,
                "fixed_manifest": result['fixed_manifest'],
                "diff": diff,
                "explanation": result['explanation'],
                "is_fallback": result['is_fallback']
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating security fix: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Admin endpoints - Excluded namespaces
    @router.get("/admin/excluded-namespaces", response_model=list[ExcludedNamespaceResponse])
    async def get_excluded_namespaces():
        """Get all excluded namespaces"""
        try:
            return await db.get_excluded_namespaces()
        except Exception as e:
            logger.error(f"Error getting excluded namespaces: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/namespaces")
    async def get_all_namespaces():
        """Get all namespaces that have findings (for suggestions)"""
        try:
            return await db.get_all_namespaces()
        except Exception as e:
            logger.error(f"Error getting namespaces: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/excluded-namespaces", response_model=ExcludedNamespaceResponse)
    async def add_excluded_namespace(request: ExcludedNamespace):
        """Add a namespace to the security scan exclusion list and remove all its findings"""
        try:
            if not request.namespace or not request.namespace.strip():
                raise HTTPException(status_code=400, detail="Namespace name is required")

            namespace = request.namespace.strip()
            result = await db.add_excluded_namespace(namespace)
            logger.info(f"Added excluded namespace for security scan: {namespace}")

            # Delete all security findings for this namespace and broadcast deletions
            findings_count, deleted_findings = await db.delete_findings_by_namespace(namespace)
            for finding in deleted_findings:
                await websocket_manager.broadcast_security_finding_deleted(finding)
            logger.info(f"Deleted {findings_count} security findings for excluded namespace: {namespace}")

            # Broadcast to all connected clients (frontend + scanners) for real-time update
            await websocket_manager.broadcast_namespace_exclusion_change(namespace, "excluded")

            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding excluded namespace: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/admin/excluded-namespaces/{namespace}")
    async def remove_excluded_namespace(namespace: str):
        """Remove a namespace from the exclusion list"""
        try:
            removed = await db.remove_excluded_namespace(namespace)
            if removed:
                logger.info(f"Removed excluded namespace: {namespace}")
                # Broadcast to all connected clients (frontend + scanners) for real-time update
                await websocket_manager.broadcast_namespace_exclusion_change(namespace, "included")
                return {"message": f"Namespace '{namespace}' removed from exclusion list"}
            else:
                raise HTTPException(status_code=404, detail=f"Namespace '{namespace}' not found in exclusion list")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing excluded namespace: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Admin endpoints - Excluded pods (pod monitoring exclusions)
    @router.get("/admin/excluded-pods")
    async def get_excluded_pods():
        """Get all excluded pods from pod monitoring"""
        try:
            return await db.get_excluded_pods()
        except Exception as e:
            logger.error(f"Error getting excluded pods: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/monitored-pods")
    async def get_monitored_pods():
        """Get all pods that are currently being monitored (for suggestions)"""
        try:
            return await db.get_all_monitored_pods()
        except Exception as e:
            logger.error(f"Error getting monitored pods: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/excluded-pods")
    async def add_excluded_pod(request: ExcludedPod):
        """Add a pod to the monitoring exclusion list (by name only) and remove its failures"""
        try:
            if not request.pod_name or not request.pod_name.strip():
                raise HTTPException(status_code=400, detail="Pod name is required")

            pod_name = request.pod_name.strip()
            result = await db.add_excluded_pod(pod_name)
            logger.info(f"Added excluded pod: {pod_name}")

            # Delete pod failures for this pod name and broadcast deletion
            count, deleted_pods = await db.delete_pod_failure_by_pod(pod_name)
            for pod in deleted_pods:
                await websocket_manager.broadcast_pod_deleted(pod['namespace'], pod['pod_name'])
            logger.info(f"Deleted {count} pod failures for excluded pod: {pod_name}")

            # Broadcast pod exclusion change for real-time update
            await websocket_manager.broadcast_pod_exclusion_change(pod_name, "excluded")

            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding excluded pod: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/admin/excluded-pods/{pod_name}")
    async def remove_excluded_pod(pod_name: str):
        """Remove a pod from the monitoring exclusion list"""
        try:
            removed = await db.remove_excluded_pod(pod_name)
            if removed:
                logger.info(f"Removed excluded pod: {pod_name}")
                # Broadcast pod exclusion change for real-time update
                await websocket_manager.broadcast_pod_exclusion_change(pod_name, "included")
                return {"message": f"Pod '{pod_name}' removed from exclusion list"}
            else:
                raise HTTPException(status_code=404, detail=f"Pod '{pod_name}' not found in exclusion list")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing excluded pod: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Admin endpoints - Excluded security rules
    @router.get("/admin/excluded-rules")
    async def get_excluded_rules():
        """Get all excluded security rules"""
        try:
            return await db.get_excluded_rules()
        except Exception as e:
            logger.error(f"Error getting excluded rules: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/rule-titles")
    async def get_all_rule_titles(namespace: str = Query(None)):
        """Get all rule titles that have findings (for suggestions). Optionally filter by namespace."""
        try:
            return await db.get_all_rule_titles(namespace)
        except Exception as e:
            logger.error(f"Error getting rule titles: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/excluded-rules")
    async def add_excluded_rule(request: ExcludedRule):
        """Add a rule to the security scan exclusion list and remove matching findings"""
        try:
            if not request.rule_title or not request.rule_title.strip():
                raise HTTPException(status_code=400, detail="Rule title is required")

            rule_title = request.rule_title.strip()
            namespace_db = request.namespace.strip() if request.namespace else ''

            result = await db.add_excluded_rule(rule_title, namespace_db)
            scope = f"namespace '{request.namespace}'" if request.namespace else "global"
            logger.info(f"Added excluded security rule: {rule_title} ({scope})")

            # Delete findings: global = all, per-namespace = only that namespace
            delete_namespace = request.namespace.strip() if request.namespace else None
            findings_count, deleted_findings = await db.delete_findings_by_rule_title(rule_title, delete_namespace)
            for finding in deleted_findings:
                await websocket_manager.broadcast_security_finding_deleted(finding)
            logger.info(f"Deleted {findings_count} security findings for excluded rule: {rule_title}")

            # Broadcast to all connected clients (frontend + scanners) for real-time update
            await websocket_manager.broadcast_rule_exclusion_change(rule_title, "excluded", request.namespace)

            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding excluded rule: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/admin/excluded-rules/{rule_title:path}")
    async def remove_excluded_rule(rule_title: str, namespace: str = Query(None)):
        """Remove a rule from the exclusion list (query param namespace for per-namespace)"""
        try:
            namespace_db = namespace.strip() if namespace else ''
            removed = await db.remove_excluded_rule(rule_title, namespace_db)
            if removed:
                scope = f"namespace '{namespace}'" if namespace else "global"
                logger.info(f"Removed excluded rule: {rule_title} ({scope})")
                # Broadcast to all connected clients for real-time update
                await websocket_manager.broadcast_rule_exclusion_change(rule_title, "included", namespace)
                return {"message": f"Rule '{rule_title}' removed from exclusion list ({scope})"}
            else:
                raise HTTPException(status_code=404, detail=f"Rule '{rule_title}' not found in exclusion list")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing excluded rule: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Trusted registries endpoints (admin-managed trusted container registries)
    @router.get("/admin/trusted-registries")
    async def get_trusted_registries():
        """Get all admin-added trusted container registries"""
        try:
            registries = await db.get_trusted_registries()
            return [r.model_dump() if hasattr(r, 'model_dump') else r for r in registries]
        except Exception as e:
            logger.error(f"Error getting trusted registries: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/trusted-registries")
    async def add_trusted_registry(data: TrustedRegistry):
        """Add a trusted container registry"""
        try:
            registry = data.registry.strip().lower()
            if not registry:
                raise HTTPException(status_code=400, detail="Registry name is required")

            result = await db.add_trusted_registry(registry)
            logger.info(f"Added trusted registry: {registry}")

            # Broadcast change to connected clients
            await websocket_manager.broadcast_trusted_registry_change(registry, "added")

            return result.model_dump() if hasattr(result, 'model_dump') else result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error adding trusted registry: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/admin/trusted-registries/{registry}")
    async def remove_trusted_registry(registry: str):
        """Remove a trusted container registry"""
        try:
            removed = await db.remove_trusted_registry(registry)
            if removed:
                logger.info(f"Removed trusted registry: {registry}")
                await websocket_manager.broadcast_trusted_registry_change(registry, "removed")
                return {"message": f"Registry '{registry}' removed from trusted list"}
            else:
                raise HTTPException(status_code=404, detail=f"Registry '{registry}' not found in trusted list")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing trusted registry: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Notification settings endpoints
    @router.get("/admin/notifications", response_model=list[NotificationSettingResponse])
    async def get_notification_settings():
        """Get all notification settings"""
        try:
            return await db.get_notification_settings()
        except Exception as e:
            logger.error(f"Error getting notification settings: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/notifications", response_model=NotificationSettingResponse)
    async def create_notification_setting(setting: NotificationSettingCreate):
        """Create or update a notification setting"""
        try:
            result = await db.save_notification_setting(setting)
            logger.info(f"Saved notification setting for provider: {setting.provider}")
            return result
        except Exception as e:
            logger.error(f"Error saving notification setting: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/admin/notifications/{provider}", response_model=NotificationSettingResponse)
    async def update_notification_setting(provider: str, setting: NotificationSettingCreate):
        """Update a notification setting"""
        try:
            result = await db.update_notification_setting(provider, setting)
            if result:
                logger.info(f"Updated notification setting for provider: {provider}")
                return result
            else:
                raise HTTPException(status_code=404, detail=f"Notification setting for '{provider}' not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating notification setting: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/admin/notifications/{provider}")
    async def delete_notification_setting(provider: str):
        """Delete a notification setting"""
        try:
            deleted = await db.delete_notification_setting(provider)
            if deleted:
                logger.info(f"Deleted notification setting for provider: {provider}")
                return {"message": f"Notification setting for '{provider}' deleted"}
            else:
                raise HTTPException(status_code=404, detail=f"Notification setting for '{provider}' not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting notification setting: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/notifications/{provider}/test")
    async def test_notification(provider: str):
        """Send a test notification"""
        try:
            if not notification_service:
                raise HTTPException(status_code=500, detail="Notification service not configured")

            setting = await db.get_notification_setting(provider)
            if not setting:
                raise HTTPException(status_code=404, detail=f"Notification setting for '{provider}' not found")

            await notification_service.test_notification(provider, setting.config)
            logger.info(f"Test notification sent for provider: {provider}")
            return {"message": f"Test notification sent successfully via {provider}"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error sending test notification: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Cluster metrics endpoints
    @router.post("/metrics/cluster")
    async def report_cluster_metrics(metrics: ClusterMetrics):
        """Receive cluster metrics from agent"""
        global latest_cluster_metrics
        try:
            latest_cluster_metrics = metrics.dict()
            logger.debug(f"Received cluster metrics: {metrics.node_count} nodes")

            # Update pod metrics history store
            metrics_history_store.update_from_cluster_metrics(latest_cluster_metrics)

            # Broadcast metrics to connected clients via WebSocket
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

    @router.post("/security/rescan-status")
    async def report_security_rescan_status(data: dict):
        """Report security rescan status from scanner (started/completed)"""
        status = data.get("status")  # "started" or "completed"
        reason = data.get("reason")  # e.g., "trusted_registry_change"
        if status not in ["started", "completed"]:
            raise HTTPException(status_code=400, detail="status must be 'started' or 'completed'")
        logger.info(f"Security rescan {status}" + (f" (reason: {reason})" if reason else ""))
        await websocket_manager.broadcast_security_rescan_status(status, reason)
        return {"message": f"Rescan status '{status}' broadcasted"}

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

        # Format history points
        formatted_history = []
        for point in history:
            formatted_history.append(PodMetricsPoint(
                timestamp=point['timestamp'],
                cpu_millicores=point['cpu_millicores'],
                memory_bytes=point['memory_bytes'],
                cpu_formatted=format_cpu(point['cpu_millicores']),
                memory_formatted=format_memory(point['memory_bytes'])
            ))

        # Get current values from latest point
        latest = history[-1] if history else {}

        return PodMetricsHistory(
            name=pod_name,
            namespace=namespace,
            current_cpu=format_cpu(latest.get('cpu_millicores')),
            current_memory=format_memory(latest.get('memory_bytes')),
            history=formatted_history
        )

    # Pod logs endpoint
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
            # Try in-cluster config first, then fall back to local kubeconfig
            try:
                config.load_incluster_config()
            except config.ConfigException:
                try:
                    config.load_kube_config()
                except config.ConfigException:
                    raise HTTPException(status_code=503, detail="Could not configure Kubernetes client")

            v1 = client.CoreV1Api()

            # Get pod to find containers
            try:
                pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            except client.ApiException as e:
                if e.status == 404:
                    raise HTTPException(status_code=404, detail=f"Pod '{pod_name}' not found in namespace '{namespace}'")
                raise HTTPException(status_code=e.status, detail=str(e.reason))

            # Get container names
            containers = [c.name for c in pod.spec.containers]
            init_containers = [c.name for c in (pod.spec.init_containers or [])]
            all_containers = containers + init_containers

            # If no container specified, use the first one
            target_container = container if container else (containers[0] if containers else None)

            if not target_container:
                raise HTTPException(status_code=400, detail="No containers found in pod")

            if target_container not in all_containers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Container '{target_container}' not found. Available: {', '.join(all_containers)}"
                )

            # Fetch logs
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
                    # Container might not have started yet
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

    # Streaming pod logs endpoint (live logs)
    @router.get("/pods/{namespace}/{pod_name}/logs/stream")
    async def stream_pod_logs(
        namespace: str,
        pod_name: str,
        container: Optional[str] = Query(None, description="Container name (optional)"),
        tail_lines: int = Query(100, description="Initial number of lines to return", ge=1, le=1000)
    ):
        """Stream logs for a specific pod (Server-Sent Events)"""
        if not K8S_AVAILABLE:
            raise HTTPException(status_code=503, detail="Kubernetes client not available")

        try:
            # Try in-cluster config first, then fall back to local kubeconfig
            try:
                config.load_incluster_config()
            except config.ConfigException:
                try:
                    config.load_kube_config()
                except config.ConfigException:
                    raise HTTPException(status_code=503, detail="Could not configure Kubernetes client")

            v1 = client.CoreV1Api()

            # Get pod to find containers
            try:
                pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            except client.ApiException as e:
                if e.status == 404:
                    raise HTTPException(status_code=404, detail=f"Pod '{pod_name}' not found in namespace '{namespace}'")
                raise HTTPException(status_code=e.status, detail=str(e.reason))

            # Get container names
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

                # Start the watch thread
                watch_thread = threading.Thread(target=watch_logs, daemon=True)
                watch_thread.start()

                try:
                    while True:
                        try:
                            # Non-blocking check with timeout to allow async cancellation
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
                            # Send heartbeat to keep connection alive
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

    # LLM Configuration endpoints
    @router.get("/admin/llm/status", response_model=LLMConfigStatus)
    async def get_llm_status():
        """Get current LLM configuration status"""
        try:
            # Check database for LLM configuration
            db_config = await db.get_llm_config()
            if db_config:
                return LLMConfigStatus(
                    configured=True,
                    provider=db_config['provider'],
                    model=db_config['model'],
                    source="database"
                )

            return LLMConfigStatus(configured=False)
        except Exception as e:
            logger.error(f"Error getting LLM status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/llm/config", response_model=LLMConfigResponse)
    async def save_llm_config(config: LLMConfigCreate):
        """Save LLM configuration"""
        try:
            # Validate provider
            valid_providers = ["openai", "anthropic", "claude", "groq", "groq_cloud", "gemini", "google"]
            if config.provider.lower() not in valid_providers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid provider. Supported: {', '.join(valid_providers)}"
                )

            # Save to database
            result = await db.save_llm_config(
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model
            )

            # Reinitialize the solution engine with new config
            await solution_engine.reinitialize_llm(
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model
            )

            logger.info(f"LLM configuration saved: provider={config.provider}")

            return LLMConfigResponse(
                id=result['id'],
                provider=result['provider'],
                model=result['model'],
                configured=True,
                created_at=result['created_at'],
                updated_at=result['updated_at']
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error saving LLM config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/admin/llm/config")
    async def delete_llm_config():
        """Delete LLM configuration (revert to rule-based solutions)"""
        try:
            deleted = await db.delete_llm_config()

            # Reset solution engine to rule-based mode (no LLM)
            solution_engine.llm_provider = None

            if deleted:
                return {"message": "LLM configuration deleted"}
            else:
                return {"message": "No LLM configuration to delete"}
        except Exception as e:
            logger.error(f"Error deleting LLM config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/llm/test")
    async def test_llm_config(config: LLMConfigCreate):
        """Test LLM configuration without saving"""
        try:
            from services.llm_factory import LLMFactory

            # Create a temporary provider to test
            provider = LLMFactory.create_provider(
                provider_name=config.provider.lower(),
                api_key=config.api_key,
                model=config.model
            )

            # Test with a simple prompt
            test_response = await provider.generate_solution(
                failure_reason="CrashLoopBackOff",
                failure_message="Test connection to LLM provider",
                pod_context={"name": "test-pod", "namespace": "test"},
                events=[{"type": "Warning", "reason": "BackOff", "message": "Back-off restarting container"}]
            )

            if test_response and test_response.content and len(test_response.content) > 10:
                return {"success": True, "message": "LLM connection successful"}
            else:
                return {"success": False, "message": "LLM returned empty response"}
        except Exception as e:
            logger.error(f"Error testing LLM config: {e}")
            return {"success": False, "message": str(e)}

    return router