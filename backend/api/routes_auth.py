"""Auth routes: setup, login, logout, invitations, me."""
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from .auth import (
    check_login_rate_limit,
    clear_login_attempts,
    clear_session_cookie,
    hash_password,
    issue_session_cookie,
    record_failed_login,
    require_user,
    verify_password,
)
from .deps import RouterDeps

logger = logging.getLogger(__name__)


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8)
    email: Optional[str] = Field(None, max_length=255)


class LoginRequest(BaseModel):
    username: str
    password: str


class AcceptInvitationRequest(BaseModel):
    token: str
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8)
    email: Optional[str] = Field(None, max_length=255)


def _public_user(user: dict) -> dict:
    """Return only the public-safe subset of a user row."""
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
        "role": user["role"],
    }


def create_auth_router(deps: RouterDeps) -> APIRouter:
    """Public auth endpoints (no auth required)."""
    router = APIRouter()
    db = deps.db

    @router.get("/auth/setup-required")
    async def setup_required():
        """Return whether initial admin setup is required (no users exist)."""
        count = await db.count_users()
        return {"setup_required": count == 0}

    @router.post("/auth/setup")
    async def setup_first_admin(body: SetupRequest, request: Request, response: Response):
        """Create the first admin account. Rejected if any users already exist."""
        count = await db.count_users()
        if count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Setup already completed",
            )

        try:
            user = await db.create_user(
                username=body.username.strip(),
                password_hash=hash_password(body.password),
                role="admin",
                email=body.email,
            )
        except Exception as e:
            logger.error(f"Failed to create first admin: {e}")
            raise HTTPException(status_code=400, detail="Could not create user")

        await issue_session_cookie(response, request, user)
        logger.info(f"Initial admin account created: {user['username']}")
        return {"user": _public_user(user)}

    @router.post("/auth/login")
    async def login(body: LoginRequest, request: Request, response: Response):
        """Authenticate with username/password. Sets session cookie."""
        client_ip = request.client.host if request.client else "unknown"
        check_login_rate_limit(client_ip)

        user = await db.get_user_by_username(body.username.strip())
        if not user or not verify_password(body.password, user.get("password_hash", "")):
            record_failed_login(client_ip)
            raise HTTPException(status_code=401, detail="Invalid username or password")

        clear_login_attempts(client_ip)
        await issue_session_cookie(response, request, user)
        return {"user": _public_user(user)}

    @router.post("/auth/logout", status_code=204)
    async def logout(response: Response):
        """Clear session cookie."""
        clear_session_cookie(response)
        return Response(status_code=204)

    @router.get("/auth/me")
    async def get_me(user: dict = Depends(require_user)):
        """Return the current authenticated user (fresh from DB)."""
        fresh = await db.get_user_by_id(user["id"])
        if not fresh:
            raise HTTPException(status_code=401, detail="User not found")
        return {"user": _public_user(fresh)}

    @router.get("/auth/invitation/{token}")
    async def get_invitation(token: str):
        """Return invitation metadata if valid and unused."""
        inv = await db.get_invitation_by_token(token)
        if not inv:
            raise HTTPException(status_code=404, detail="Invitation not found")
        if inv.get("used_at"):
            raise HTTPException(status_code=410, detail="Invitation already used")
        expires_at = _parse_iso(inv.get("expires_at"))
        if expires_at and expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Invitation expired")
        return {"role": inv["role"], "expires_at": inv["expires_at"]}

    @router.post("/auth/accept-invitation")
    async def accept_invitation(
        body: AcceptInvitationRequest, request: Request, response: Response
    ):
        """Consume an invitation to create a new user account."""
        inv = await db.get_invitation_by_token(body.token)
        if not inv:
            raise HTTPException(status_code=404, detail="Invitation not found")
        if inv.get("used_at"):
            raise HTTPException(status_code=410, detail="Invitation already used")
        expires_at = _parse_iso(inv.get("expires_at"))
        if expires_at and expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Invitation expired")

        username = body.username.strip()
        existing = await db.get_user_by_username(username)
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")

        try:
            user = await db.create_user(
                username=username,
                password_hash=hash_password(body.password),
                role=inv["role"],
                email=body.email,
            )
        except Exception as e:
            logger.error(f"Failed to create user from invitation: {e}")
            raise HTTPException(status_code=400, detail="Could not create user")

        marked = await db.mark_invitation_used(inv["id"], user["id"])
        if not marked:
            # Race: someone else consumed the invitation between check and mark.
            # Roll back the user we just created so they can't log in with a
            # "used" invitation bypassed.
            await db.delete_user(user["id"])
            raise HTTPException(status_code=410, detail="Invitation already used")

        await issue_session_cookie(response, request, user)
        logger.info(f"User '{user['username']}' created via invitation (role={user['role']})")
        return {"user": _public_user(user)}

    return router


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None
