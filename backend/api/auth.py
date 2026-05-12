"""Authentication and authorization for Kure Monitor.

Uses a two-tier auth model:

1. User sessions (JWT in httpOnly `kure_session` cookie):
   - Users authenticate with username/password and receive a signed JWT cookie.
   - Two roles: 'admin', 'member'.
   - Used for the dashboard/frontend and all user-facing endpoints.

2. Service token (X-Service-Token header or ?token= query param):
   - Shared secret stored in app_settings (auto-generated on first boot).
   - Used by the agent and security-scanner to POST ingest data.
"""

import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response

logger = logging.getLogger(__name__)

# --- Constants ---

SESSION_COOKIE_NAME = "kure_session"
SESSION_TTL_DAYS = 7
SESSION_SECRET_SETTING_KEY = "session_secret"
SERVICE_TOKEN_SETTING_KEY = "service_token"

# Login rate limiter: 5 attempts per IP, 30-second window.
# Backed by the `login_attempts` DB table so multi-replica backends share state.
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_COOLDOWN_SECONDS = 30


# --- Password hashing ---


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    if not password:
        raise ValueError("Password is required")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# --- Session secret ---


async def get_session_secret(db) -> str:
    """Resolve session secret with precedence: env var > app_settings > generated.

    No process-local cache: every call hits the DB so admin rotations from
    other backend replicas take effect immediately. The `app_settings` lookup
    is an indexed PK read (microseconds).

    If `SESSION_SECRET` env var is set, it is the source of truth: the
    `app_settings.session_secret` row is seeded (if missing) or overwritten
    (if it differs) so that other code paths reading from the DB stay in sync.
    """
    env_secret = os.environ.get("SESSION_SECRET")
    if env_secret:
        stored = await db.get_app_setting(SESSION_SECRET_SETTING_KEY)
        if stored != env_secret:
            await db.set_app_setting(SESSION_SECRET_SETTING_KEY, env_secret)
            if stored is None:
                logger.info("Seeded session secret from SESSION_SECRET env var")
            else:
                logger.info(
                    "Overwrote session secret in app_settings from SESSION_SECRET env var"
                )
        return env_secret

    stored = await db.get_app_setting(SESSION_SECRET_SETTING_KEY)
    if not stored:
        stored = secrets.token_hex(32)
        await db.set_app_setting(SESSION_SECRET_SETTING_KEY, stored)
        logger.info("Generated new session secret and stored in app_settings")
    return stored


# --- Service token ---


async def get_service_token(db) -> str:
    """Resolve service token with precedence: env var > app_settings > generated.

    No process-local cache: every call hits the DB so admin rotations from
    other backend replicas take effect immediately. The `app_settings` lookup
    is an indexed PK read (microseconds).

    If `SERVICE_TOKEN` env var is set, it is the source of truth: the
    `app_settings.service_token` row is seeded (if missing) or overwritten
    (if it differs). This lets Helm pre-provision the token via a shared
    Kubernetes Secret and share the same value across agent/scanner/backend.
    """
    env_token = os.environ.get("SERVICE_TOKEN")
    if env_token:
        stored = await db.get_app_setting(SERVICE_TOKEN_SETTING_KEY)
        if stored != env_token:
            await db.set_app_setting(SERVICE_TOKEN_SETTING_KEY, env_token)
            if stored is None:
                logger.info("Seeded service token from SERVICE_TOKEN env var")
            else:
                logger.info(
                    "Overwrote service token in app_settings from SERVICE_TOKEN env var"
                )
        return env_token

    stored = await db.get_app_setting(SERVICE_TOKEN_SETTING_KEY)
    if not stored:
        stored = secrets.token_hex(32)
        await db.set_app_setting(SERVICE_TOKEN_SETTING_KEY, stored)
        logger.info("Generated new service token and stored in app_settings")
    return stored


def reset_auth_cache():
    """Deprecated test helper. Auth resolvers no longer cache; this is a no-op
    kept for backwards compatibility with existing test fixtures."""
    return None


# --- JWT encode/decode ---


def _encode_session_jwt(user: dict, secret: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=SESSION_TTL_DAYS)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _decode_session_jwt(token: str, secret: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError as e:
        logger.debug(f"Invalid session JWT: {e}")
        return None


async def issue_session_cookie(response: Response, request: Request, user: dict) -> str:
    """Sign a JWT for the user and set it as an httpOnly cookie on the response."""
    db = request.app.state.db
    secret = await get_session_secret(db)
    token = _encode_session_jwt(user, secret)
    secure = request.url.scheme == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return token


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


# --- Rate limiting (login) ---
#
# Backed by the `login_attempts` DB table so all backend replicas share state
# and the attacker can't bypass the limit by hitting different pods. Bounded
# growth: each IP is one row, and `cleanup_old_login_attempts` can be wired
# up to sweep stale rows periodically.


async def check_login_rate_limit(db, client_ip: str) -> None:
    """Raise 429 if the IP has exhausted its attempts in the current window."""
    count = await db.get_login_attempt_count(client_ip, _LOGIN_COOLDOWN_SECONDS)
    if count >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again in 30 seconds.",
        )


async def record_failed_login(db, client_ip: str) -> int:
    """Record a failed login attempt for this IP. Returns new count in window."""
    return await db.record_failed_login(client_ip, _LOGIN_COOLDOWN_SECONDS)


async def clear_login_attempts(db, client_ip: str) -> None:
    """Clear all recorded attempts for this IP (called after successful login)."""
    await db.clear_login_attempts(client_ip)


# --- Current user resolution ---


async def _resolve_user_from_cookie(request: Request) -> Optional[dict]:
    """Decode the session cookie and return the user dict (from JWT claims).

    Does not hit the database. For fresh role info, callers that need it
    should fetch by id.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    db = getattr(request.app.state, "db", None)
    if db is None:
        return None
    secret = await get_session_secret(db)
    payload = _decode_session_jwt(token, secret)
    if not payload:
        return None
    try:
        return {
            "id": int(payload["sub"]),
            "username": payload["username"],
            "role": payload["role"],
        }
    except (KeyError, ValueError):
        return None


# --- FastAPI dependencies ---


async def require_authenticated(request: Request) -> dict:
    """Require any authenticated user (admin or member). Returns user dict."""
    user = await _resolve_user_from_cookie(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    request.state.user = user
    return user


# Legacy aliases. With the 2-role system, the only meaningful distinction is
# admin vs. member, so every non-admin authenticated check collapses to
# require_authenticated. These names are kept so existing route registrations
# and test fixtures (dependency_overrides) keep working without churn.
require_user = require_authenticated
require_read = require_authenticated
require_write = require_authenticated


async def require_admin(user: dict = Depends(require_authenticated)) -> dict:
    """Require role == 'admin'."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_service_token(request: Request) -> None:
    """Validate service token from X-Service-Token header.

    Used by agent/scanner ingest endpoints.
    """
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not ready")

    provided = request.headers.get("X-Service-Token")
    if not provided:
        raise HTTPException(status_code=401, detail="Missing service token")

    expected = await get_service_token(db)
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid service token")


async def require_user_or_service(request: Request) -> dict:
    """Accept either a user session cookie OR a valid service token.

    Used by endpoints that can be called both by the dashboard and by
    the agent/scanner (e.g. status queries).
    """
    user = await _resolve_user_from_cookie(request)
    if user:
        request.state.user = user
        return user

    # Fall back to service token
    db = getattr(request.app.state, "db", None)
    if db is not None:
        provided = request.headers.get("X-Service-Token")
        if provided:
            expected = await get_service_token(db)
            if hmac.compare_digest(provided, expected):
                return {"id": 0, "username": "service", "role": "service"}

    raise HTTPException(status_code=401, detail="Authentication required")


# --- WebSocket helpers ---


async def validate_ws_auth(
    *, cookie_token: Optional[str], query_token: Optional[str], db
) -> Optional[dict]:
    """Validate a WebSocket connection.

    Returns a dict describing the principal on success:
      - {"kind": "user", "id", "username", "role"} for a user
      - {"kind": "service"} for the agent/scanner
    Returns None on failure.
    """
    # Try user session cookie first
    if cookie_token:
        secret = await get_session_secret(db)
        payload = _decode_session_jwt(cookie_token, secret)
        if payload:
            try:
                return {
                    "kind": "user",
                    "id": int(payload["sub"]),
                    "username": payload["username"],
                    "role": payload["role"],
                }
            except (KeyError, ValueError):
                pass

    # Try service token via ?token= query param
    if query_token:
        expected = await get_service_token(db)
        if hmac.compare_digest(query_token, expected):
            return {"kind": "service"}

    return None
