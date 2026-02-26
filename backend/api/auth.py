import hashlib
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


def _hash_key(key: str) -> str:
    """SHA-256 hash of a key for DB lookup."""
    return hashlib.sha256(key.encode()).hexdigest()


def get_api_key(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def _resolve_token(token: str, db) -> Optional[str]:
    """Check a token against bootstrap key, then DB keys. Returns role or None."""
    # Check bootstrap admin key first
    if AUTH_API_KEY and hmac.compare_digest(token, AUTH_API_KEY):
        return "admin"

    # Check DB-managed keys
    if db is not None:
        role = await db.validate_api_key(_hash_key(token))
        if role:
            return role

    return None


async def require_auth(request: Request):
    """FastAPI dependency - raises 401 if auth is enabled and key is wrong.

    Automatically exempts ingest endpoints (agent/scanner traffic) and
    SSE streaming endpoints (which use query param token instead).

    Sets request.state.role to the authenticated role ("admin" or "viewer").
    """
    if not AUTH_API_KEY:
        request.state.role = "admin"  # No auth = full access
        return

    method = request.method
    path = request.url.path

    # Exempt exact-match routes
    if (method, path) in _EXEMPT_ROUTES:
        request.state.role = "admin"
        return

    # Exempt prefix-match routes
    for exempt_method, prefix in _EXEMPT_PREFIXES:
        if method == exempt_method and path.startswith(prefix):
            request.state.role = "admin"
            return

    # Get db from app state (set during startup)
    db = getattr(request.app.state, "db", None)

    # SSE streaming endpoints authenticate via ?token= query param
    # (EventSource API cannot set custom headers)
    for suffix in _TOKEN_PARAM_PATHS:
        if path.endswith(suffix):
            token = request.query_params.get("token")
            if not token:
                raise HTTPException(status_code=401, detail="Invalid or missing auth token")
            role = await _resolve_token(token, db)
            if not role:
                raise HTTPException(status_code=401, detail="Invalid or missing auth token")
            request.state.role = role
            return

    # Standard header auth
    token = get_api_key(request)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    role = await _resolve_token(token, db)
    if not role:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    request.state.role = role


async def validate_ws_token(token: Optional[str], db=None) -> Optional[str]:
    """Validate a WebSocket/SSE query param token. Returns role or None."""
    if not AUTH_API_KEY:
        return "admin"
    if token is None:
        return None
    return await _resolve_token(token, db)


def require_admin(request: Request):
    """FastAPI dependency - raises 403 if user is not admin."""
    role = getattr(request.state, "role", None)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


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
    async def auth_status(request: Request):
        """Check if authentication is enabled. If a valid key is in the header, also return the role."""
        result = {"enabled": AUTH_API_KEY is not None}

        # If auth is disabled, everyone is admin
        if not AUTH_API_KEY:
            result["role"] = "admin"
            return result

        # If a valid token is provided, return its role
        token = get_api_key(request)
        if token:
            db = getattr(request.app.state, "db", None)
            role = await _resolve_token(token, db)
            if role:
                result["role"] = role

        return result

    @router.post("/auth/login")
    async def auth_login(body: LoginRequest, request: Request):
        """Validate an API key."""
        if not AUTH_API_KEY:
            return {"valid": True, "role": "admin"}

        client_ip = request.client.host if request.client else "unknown"
        _check_rate_limit(client_ip)

        db = getattr(request.app.state, "db", None)
        role = await _resolve_token(body.api_key, db)

        if not role:
            _record_attempt(client_ip)
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Successful login clears the attempts for this IP
        _login_attempts.pop(client_ip, None)
        return {"valid": True, "role": role}

    return router
