from fastapi import APIRouter, HTTPException, Query
import logging

from models.models import (
    ExcludedNamespace, ExcludedNamespaceResponse,
    ExcludedPod,
    ExcludedRule,
    TrustedRegistry,
    NotificationSettingCreate, NotificationSettingResponse,
)
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_admin_router(deps: RouterDeps) -> APIRouter:
    """Excluded namespaces/pods/rules, trusted registries, notifications."""
    router = APIRouter()
    db = deps.db
    websocket_manager = deps.websocket_manager
    notification_service = deps.notification_service

    # --- Excluded namespaces ---

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

            findings_count, deleted_findings = await db.delete_findings_by_namespace(namespace)
            for finding in deleted_findings:
                await websocket_manager.broadcast_security_finding_deleted(finding)
            logger.info(f"Deleted {findings_count} security findings for excluded namespace: {namespace}")

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
                await websocket_manager.broadcast_namespace_exclusion_change(namespace, "included")
                return {"message": f"Namespace '{namespace}' removed from exclusion list"}
            else:
                raise HTTPException(status_code=404, detail=f"Namespace '{namespace}' not found in exclusion list")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing excluded namespace: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # --- Excluded pods ---

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

            count, deleted_pods = await db.delete_pod_failure_by_pod(pod_name)
            for pod in deleted_pods:
                await websocket_manager.broadcast_pod_deleted(pod['namespace'], pod['pod_name'])
            logger.info(f"Deleted {count} pod failures for excluded pod: {pod_name}")

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
                await websocket_manager.broadcast_pod_exclusion_change(pod_name, "included")
                return {"message": f"Pod '{pod_name}' removed from exclusion list"}
            else:
                raise HTTPException(status_code=404, detail=f"Pod '{pod_name}' not found in exclusion list")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing excluded pod: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # --- Excluded rules ---

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

            delete_namespace = request.namespace.strip() if request.namespace else None
            findings_count, deleted_findings = await db.delete_findings_by_rule_title(rule_title, delete_namespace)
            for finding in deleted_findings:
                await websocket_manager.broadcast_security_finding_deleted(finding)
            logger.info(f"Deleted {findings_count} security findings for excluded rule: {rule_title}")

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
                await websocket_manager.broadcast_rule_exclusion_change(rule_title, "included", namespace)
                return {"message": f"Rule '{rule_title}' removed from exclusion list ({scope})"}
            else:
                raise HTTPException(status_code=404, detail=f"Rule '{rule_title}' not found in exclusion list")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error removing excluded rule: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # --- Trusted registries ---

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

    # --- Notifications ---

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

    return router
