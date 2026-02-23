import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

AUTH_API_KEY: Optional[str] = os.environ.get("AUTH_API_KEY")

if AUTH_API_KEY:
    logger.info("Authentication is ENABLED (AUTH_API_KEY is set)")
else:
    logger.warning("Authentication is DISABLED (AUTH_API_KEY not set) - all endpoints are open")


def get_api_key(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def require_auth(request: Request):
    """FastAPI dependency - raises 401 if auth is enabled and key is wrong."""
    if not AUTH_API_KEY:
        return
    token = get_api_key(request)
    if not token or not hmac.compare_digest(token, AUTH_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def validate_ws_token(token: Optional[str]) -> bool:
    """Validate a WebSocket/SSE query param token."""
    if not AUTH_API_KEY:
        return True
    return token is not None and hmac.compare_digest(token, AUTH_API_KEY)


class LoginRequest(BaseModel):
    api_key: str


def create_auth_router() -> APIRouter:
    """Create auth status and login endpoints (always public)."""
    router = APIRouter()

    @router.get("/auth/status")
    async def auth_status():
        """Check if authentication is enabled."""
        return {"enabled": AUTH_API_KEY is not None}

    @router.post("/auth/login")
    async def auth_login(request: LoginRequest):
        """Validate an API key."""
        if not AUTH_API_KEY:
            return {"valid": True}
        valid = hmac.compare_digest(request.api_key, AUTH_API_KEY)
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return {"valid": True}

    return router
