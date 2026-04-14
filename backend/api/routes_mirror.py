from fastapi import APIRouter, Depends, HTTPException
import logging

from models.models import (
    MirrorDeployRequest, MirrorDeployResponse, MirrorPreviewResponse,
    MirrorStatusResponse, MirrorActiveItem, MirrorTTLSetting,
)
from services.mirror_service import MirrorService
from .auth import require_write
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_mirror_router(deps: RouterDeps, mirror_service: MirrorService) -> APIRouter:
    """Mirror pod deploy, status, delete, list, and TTL settings."""
    router = APIRouter()

    @router.post("/mirror/preview/{pod_id}", response_model=MirrorPreviewResponse, dependencies=[Depends(require_write)])
    async def preview_mirror_fix(pod_id: int):
        """Generate an AI-fixed manifest for a failing pod without deploying it."""
        try:
            fix_result = await mirror_service.generate_preview(pod_failure_id=pod_id)
            return MirrorPreviewResponse(
                fixed_manifest=fix_result["fixed_manifest"],
                explanation=fix_result["explanation"],
                is_fallback=fix_result["is_fallback"],
            )

        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            logger.error(f"Error generating mirror preview for pod_id={pod_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/mirror/deploy/{pod_id}", response_model=MirrorDeployResponse, dependencies=[Depends(require_write)])
    async def deploy_mirror_pod(pod_id: int, request: MirrorDeployRequest = MirrorDeployRequest()):
        """Deploy a mirror pod from a failing pod with an AI-generated fix applied."""
        try:
            mirror_info = await mirror_service.create_mirror(
                pod_failure_id=pod_id,
                ttl_seconds=request.ttl_seconds,
                manifest=request.manifest,
            )

            return MirrorDeployResponse(
                mirror_id=mirror_info["mirror_id"],
                mirror_pod_name=mirror_info["mirror_pod_name"],
                namespace=mirror_info["namespace"],
                status=mirror_info.get("phase", "Pending"),
                ttl_seconds=mirror_info["ttl_seconds"],
                created_at=mirror_info["created_at"],
                fixed_manifest=mirror_info.get("fixed_manifest"),
                explanation=mirror_info.get("explanation"),
            )

        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            logger.error(f"Error deploying mirror pod for pod_id={pod_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/mirror/status/{mirror_id}", response_model=MirrorStatusResponse)
    async def get_mirror_status(mirror_id: str):
        """Get the current status of a mirror pod."""
        try:
            status = await mirror_service.get_mirror_status(mirror_id)
            return MirrorStatusResponse(**status)

        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            logger.error(f"Error getting mirror status for {mirror_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/mirror/{mirror_id}", dependencies=[Depends(require_write)])
    async def delete_mirror_pod(mirror_id: str):
        """Manually delete a mirror pod."""
        try:
            await mirror_service.delete_mirror(mirror_id)
            return {"message": "Mirror pod deleted"}

        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            logger.error(f"Error deleting mirror pod {mirror_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/mirror/active", response_model=list[MirrorActiveItem])
    async def list_active_mirrors():
        """List all active mirror pods."""
        try:
            mirrors = mirror_service.list_active_mirrors()
            return [
                MirrorActiveItem(
                    mirror_id=m["mirror_id"],
                    mirror_pod_name=m["mirror_pod_name"],
                    namespace=m["namespace"],
                    source_pod_name=m["source_pod_name"],
                    pod_failure_id=m["pod_failure_id"],
                    phase=m.get("phase"),
                    ttl_seconds=m["ttl_seconds"],
                    created_at=m["created_at"],
                    expires_at=m["expires_at"],
                )
                for m in mirrors
            ]
        except Exception as e:
            logger.error(f"Error listing active mirrors: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/settings/mirror-ttl", response_model=MirrorTTLSetting)
    async def get_mirror_ttl():
        """Get the default mirror pod TTL setting."""
        try:
            ttl = await mirror_service.get_default_ttl()
            return MirrorTTLSetting(seconds=ttl)
        except Exception as e:
            logger.error(f"Error getting mirror TTL: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/admin/settings/mirror-ttl", response_model=MirrorTTLSetting, dependencies=[Depends(require_write)])
    async def set_mirror_ttl(request: MirrorTTLSetting):
        """Set the default mirror pod TTL (seconds). Min 30, max 3600."""
        try:
            if request.seconds < 30 or request.seconds > 3600:
                raise HTTPException(
                    status_code=400,
                    detail="TTL must be between 30 and 3600 seconds"
                )
            await mirror_service.set_default_ttl(request.seconds)
            logger.info(f"Mirror TTL set to {request.seconds} seconds")
            return MirrorTTLSetting(seconds=request.seconds)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error setting mirror TTL: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
