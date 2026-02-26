import hashlib
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require_admin
from .deps import RouterDeps

logger = logging.getLogger(__name__)


class CreateApiKeyRequest(BaseModel):
    name: str
    role: str = "viewer"


def create_api_keys_router(deps: RouterDeps) -> APIRouter:
    """API key management routes (admin only)."""
    router = APIRouter(dependencies=[Depends(require_admin)])
    db = deps.db

    @router.get("/admin/api-keys")
    async def list_api_keys():
        """List all non-revoked API keys (metadata only)."""
        try:
            return await db.list_api_keys()
        except Exception as e:
            logger.error(f"Error listing API keys: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/api-keys")
    async def create_api_key(body: CreateApiKeyRequest):
        """Create a new API key. Returns the plain-text key once."""
        if not body.name or not body.name.strip():
            raise HTTPException(status_code=400, detail="Key name is required")
        if body.role not in ("admin", "viewer"):
            raise HTTPException(status_code=400, detail="Role must be 'admin' or 'viewer'")

        try:
            plain_key = secrets.token_hex(32)
            key_hash = hashlib.sha256(plain_key.encode()).hexdigest()

            result = await db.create_api_key(body.name.strip(), key_hash, body.role)
            logger.info(f"Created API key '{body.name}' with role '{body.role}'")

            return {
                **result,
                "key": plain_key,
            }
        except Exception as e:
            logger.error(f"Error creating API key: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/admin/api-keys/{key_id}")
    async def revoke_api_key(key_id: int):
        """Revoke an API key."""
        try:
            revoked = await db.revoke_api_key(key_id)
            if not revoked:
                raise HTTPException(status_code=404, detail="API key not found or already revoked")
            logger.info(f"Revoked API key id={key_id}")
            return {"message": "API key revoked"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error revoking API key: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
