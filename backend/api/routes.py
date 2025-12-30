from fastapi import APIRouter, HTTPException
import logging
import traceback

from models.models import (
    PodFailureReport, PodFailureResponse,
    SecurityFindingReport, SecurityFindingResponse,
    ExcludedNamespace, ExcludedNamespaceResponse
)
from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager

logger = logging.getLogger(__name__)

def create_api_router(db: Database, solution_engine: SolutionEngine, websocket_manager: WebSocketManager, cluster_info: dict) -> APIRouter:
    """Create and configure the API router"""
    router = APIRouter(prefix="/api")

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
                pod_context=pod_context
            )

            # Create response
            response = PodFailureResponse(
                **report.dict(),
                solution=solution,
                timestamp=report.creation_timestamp
            )

            # Save to database
            logger.info(f"Saving pod failure to database: {report.namespace}/{report.pod_name}")
            await db.save_pod_failure(response)

            # Notify frontend via WebSocket
            logger.info(f"Broadcasting pod failure via WebSocket: {report.namespace}/{report.pod_name}")
            await websocket_manager.broadcast_pod_failure(response)

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
            await db.dismiss_pod_failure(pod_id)
            return {"message": "Pod failure dismissed"}
        except Exception as e:
            logger.error(f"Error dismissing pod failure: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/pods/ignored/{pod_id}/restore")
    async def restore_pod_failure(pod_id: int):
        """Restore/un-ignore a dismissed pod failure"""
        try:
            await db.restore_pod_failure(pod_id)
            return {"message": "Pod failure restored"}
        except Exception as e:
            logger.error(f"Error restoring pod failure: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/pods/dismiss-deleted")
    async def dismiss_deleted_pod(request: dict):
        """Mark pods as dismissed when they're deleted from Kubernetes"""
        try:
            namespace = request.get("namespace")
            pod_name = request.get("pod_name")
            
            if not namespace or not pod_name:
                raise HTTPException(status_code=400, detail="namespace and pod_name required")
            
            await db.dismiss_deleted_pod(namespace, pod_name)
            
            # Notify frontend via WebSocket that pod was removed
            await websocket_manager.broadcast_pod_deleted(namespace, pod_name)
            
            logger.info(f"Dismissed deleted pod: {namespace}/{pod_name}")
            return {"message": "Deleted pod dismissed"}
        except Exception as e:
            logger.error(f"Error dismissing deleted pod: {e}")
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

    @router.post("/cluster/register")
    async def register_cluster_info(request: dict):
        """Register cluster information from agent"""
        try:
            cluster_name = request.get("cluster_name")
            if not cluster_name:
                raise HTTPException(status_code=400, detail="cluster_name is required")
            
            cluster_info["cluster_name"] = cluster_name
            logger.info(f"Registered cluster: {cluster_name}")
            return {"message": "Cluster info registered successfully"}
        except Exception as e:
            logger.error(f"Error registering cluster info: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/cluster/info")
    async def get_cluster_info():
        """Get cluster information"""
        try:
            return cluster_info
        except Exception as e:
            logger.error(f"Error getting cluster info: {e}")
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

    # Admin endpoints - Excluded namespaces
    @router.get("/admin/excluded-namespaces", response_model=list[ExcludedNamespaceResponse])
    async def get_excluded_namespaces():
        """Get all excluded namespaces"""
        try:
            return await db.get_excluded_namespaces()
        except Exception as e:
            logger.error(f"Error getting excluded namespaces: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/excluded-namespaces", response_model=ExcludedNamespaceResponse)
    async def add_excluded_namespace(request: ExcludedNamespace):
        """Add a namespace to the exclusion list"""
        try:
            if not request.namespace or not request.namespace.strip():
                raise HTTPException(status_code=400, detail="Namespace name is required")

            namespace = request.namespace.strip()
            result = await db.add_excluded_namespace(namespace)
            logger.info(f"Added excluded namespace: {namespace}")
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
                return {"message": f"Namespace '{namespace}' removed from exclusion list"}
            else:
                raise HTTPException(status_code=404, detail=f"Namespace '{namespace}' not found in exclusion list")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing excluded namespace: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router