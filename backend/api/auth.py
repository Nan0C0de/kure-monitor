import hmac
import logging
import os
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# In-memory login rate limiter: 5 attempts per IP, 30-second cooldown
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_COOLDOWN_SECONDS = 30
_login_attempts: dict[str, list[float]] = defaultdict(list)

AUTH_API_KEY: Optional[str] = os.environ.get("AUTH_API_KEY")

if AUTH_API_KEY:
    logger.info("Authentication is ENABLED (AUTH_API_KEY is set)")
else:
    logger.warning("Authentication is DISABLED (AUTH_API_KEY not set) - all endpoints are open")

# Endpoints exempt from auth (agent/scanner ingest + auth endpoints)
_EXEMPT_ROUTES = {
    ("POST", "/api/pods/failed"),
    ("POST", "/api/pods/dismiss-deleted"),
    ("POST", "/api/security/findings"),
    ("POST", "/api/security/scan/clear"),
    ("POST", "/api/security/rescan-status"),
    ("POST", "/api/metrics/cluster"),
    ("POST", "/api/metrics/security-scan-duration"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/login"),
}

# Path prefixes exempt from auth
_EXEMPT_PREFIXES = [
    ("DELETE", "/api/security/findings/resource/"),
]

# SSE streaming - uses query param token instead of header
_TOKEN_PARAM_PATHS = [
    "/logs/stream",
]


def get_api_key(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def require_auth(request: Request):
    """FastAPI dependency - raises 401 if auth is enabled and key is wrong.

    Automatically exempts ingest endpoints (agent/scanner traffic) and
    SSE streaming endpoints (which use query param token instead).
    """
    if not AUTH_API_KEY:
        return

    method = request.method
    path = request.url.path

    # Exempt exact-match routes
    if (method, path) in _EXEMPT_ROUTES:
        return

    # Exempt prefix-match routes
    for exempt_method, prefix in _EXEMPT_PREFIXES:
        if method == exempt_method and path.startswith(prefix):
            return

    # SSE streaming endpoints authenticate via ?token= query param
    # (EventSource API cannot set custom headers)
    for suffix in _TOKEN_PARAM_PATHS:
        if path.endswith(suffix):
            token = request.query_params.get("token")
            if not validate_ws_token(token):
                raise HTTPException(status_code=401, detail="Invalid or missing auth token")
            return

    # Standard header auth
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


def _check_rate_limit(client_ip: str) -> None:
    """Raise 429 if the client has exceeded the login attempt limit."""
    now = time.monotonic()
    # Discard attempts older than the cooldown window
    _login_attempts[client_ip] = [
        t for t in _login_attempts[client_ip]
        if now - t < _LOGIN_COOLDOWN_SECONDS
    ]
    if len(_login_attempts[client_ip]) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again in 30 seconds.",
        )


def _record_attempt(client_ip: str) -> None:
    """Record a failed login attempt."""
    _login_attempts[client_ip].append(time.monotonic())


def create_auth_router() -> APIRouter:
    """Create auth status and login endpoints (always public)."""
    router = APIRouter()

    @router.get("/auth/status")
    async def auth_status():
        """Check if authentication is enabled."""
        return {"enabled": AUTH_API_KEY is not None}

    @router.post("/auth/login")
    async def auth_login(body: LoginRequest, request: Request):
        """Validate an API key."""
        if not AUTH_API_KEY:
            return {"valid": True}

        client_ip = request.client.host if request.client else "unknown"
        _check_rate_limit(client_ip)

        valid = hmac.compare_digest(body.api_key, AUTH_API_KEY)
        if not valid:
            _record_attempt(client_ip)
            raise HTTPException(status_code=401, detail="Invalid API key")
        # Successful login clears the attempts for this IP
        _login_attempts.pop(client_ip, None)
        return {"valid": True}

    return router
