from fastapi import APIRouter, HTTPException
import difflib
import logging
import traceback

from models.models import SecurityFindingReport, SecurityFindingResponse
from services.prometheus_metrics import SECURITY_FINDINGS_TOTAL
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def compute_manifest_diff(original: str, fixed: str) -> list:
    """Compute a structured diff between original and fixed manifests"""
    original_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)
    diff_result = []

    matcher = difflib.SequenceMatcher(None, original_lines, fixed_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for line in original_lines[i1:i2]:
                diff_result.append({'content': line.rstrip('\n'), 'type': 'unchanged'})
        elif tag == 'replace':
            for line in original_lines[i1:i2]:
                diff_result.append({'content': line.rstrip('\n'), 'type': 'removed'})
            for line in fixed_lines[j1:j2]:
                diff_result.append({'content': line.rstrip('\n'), 'type': 'added'})
        elif tag == 'delete':
            for line in original_lines[i1:i2]:
                diff_result.append({'content': line.rstrip('\n'), 'type': 'removed'})
        elif tag == 'insert':
            for line in fixed_lines[j1:j2]:
                diff_result.append({'content': line.rstrip('\n'), 'type': 'added'})

    return diff_result


def create_security_router(deps: RouterDeps) -> APIRouter:
    """Security findings CRUD, manifest, fix generation, rescan status."""
    router = APIRouter()
    db = deps.db
    solution_engine = deps.solution_engine
    websocket_manager = deps.websocket_manager

    @router.post("/security/findings", response_model=SecurityFindingResponse)
    async def report_security_finding(report: SecurityFindingReport):
        """Receive security finding report from scanner agent"""
        logger.info(f"Received security finding for {report.resource_type}/{report.namespace}/{report.resource_name}")

        try:
            if not report.resource_name or not report.namespace:
                raise HTTPException(status_code=400, detail="Resource name and namespace are required")

            response = SecurityFindingResponse(**report.dict())

            logger.info(f"Saving security finding to database: {report.resource_type}/{report.namespace}/{report.resource_name}")
            finding_id, is_new = await db.save_security_finding(response)
            response.id = finding_id

            if is_new:
                logger.info(f"Broadcasting NEW security finding via WebSocket: {report.resource_type}/{report.namespace}/{report.resource_name}")
                await websocket_manager.broadcast_security_finding(response)
            else:
                logger.info(f"Updated existing security finding (not broadcasting): {report.resource_type}/{report.namespace}/{report.resource_name}")

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

            for finding in deleted_findings:
                await websocket_manager.broadcast_security_finding_deleted(finding)

            return {"message": f"Deleted {count} findings for resource", "count": count}
        except Exception as e:
            logger.error(f"Error deleting findings by resource: {e}")
            raise HTTPException(status_code=500, detail=str(e))

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

    @router.post("/security/rescan")
    async def trigger_security_rescan():
        """Trigger a full security rescan by broadcasting a request to the scanner via WebSocket"""
        logger.info("Manual security rescan requested")
        await websocket_manager.broadcast_security_rescan_request()
        return {"message": "Security rescan requested"}

    @router.post("/security/rescan-status")
    async def report_security_rescan_status(data: dict):
        """Report security rescan status from scanner (started/completed)"""
        status = data.get("status")
        reason = data.get("reason")
        if status not in ["started", "completed"]:
            raise HTTPException(status_code=400, detail="status must be 'started' or 'completed'")
        logger.info(f"Security rescan {status}" + (f" (reason: {reason})" if reason else ""))
        await websocket_manager.broadcast_security_rescan_status(status, reason)
        return {"message": f"Rescan status '{status}' broadcasted"}

    return router
