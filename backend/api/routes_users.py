"""Admin-only user + invitation management routes."""
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import require_admin
from .deps import RouterDeps

logger = logging.getLogger(__name__)


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., description="One of 'admin', 'write', 'read'")


class CreateInvitationRequest(BaseModel):
    role: str = Field(..., description="One of 'write', 'read'")
    # None means the invitation never expires (still revocable by admin).
    expires_in_hours: Optional[int] = Field(72, ge=1)


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
        "role": user["role"],
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }


def create_users_router(deps: RouterDeps) -> APIRouter:
    """Admin-only user and invitation routes."""
    router = APIRouter(dependencies=[Depends(require_admin)])
    db = deps.db

    # --- Users ---

    @router.get("/admin/users")
    async def list_users():
        users = await db.list_users()
        return [_public_user(u) for u in users]

    @router.patch("/admin/users/{user_id}")
    async def update_user_role(
        user_id: int,
        body: UpdateRoleRequest,
        current: dict = Depends(require_admin),
    ):
        if body.role not in ("admin", "write", "read"):
            raise HTTPException(status_code=400, detail="Invalid role")

        if user_id == current["id"]:
            raise HTTPException(status_code=400, detail="Cannot change your own role")

        target = await db.get_user_by_id(user_id)
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        # If we're demoting an admin, make sure at least one admin remains.
        if target["role"] == "admin" and body.role != "admin":
            admin_count = await db.count_admins()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot demote the last admin",
                )

        updated = await db.update_user_role(user_id, body.role)
        if not updated:
            raise HTTPException(status_code=404, detail="User not found")
        return _public_user(updated)

    @router.delete("/admin/users/{user_id}")
    async def delete_user(
        user_id: int,
        current: dict = Depends(require_admin),
    ):
        if user_id == current["id"]:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")

        target = await db.get_user_by_id(user_id)
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        if target["role"] == "admin":
            admin_count = await db.count_admins()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete the last admin",
                )

        deleted = await db.delete_user(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        return {"message": "User deleted"}

    # --- Invitations ---

    @router.post("/admin/invitations")
    async def create_invitation(
        body: CreateInvitationRequest,
        current: dict = Depends(require_admin),
    ):
        if body.role not in ("write", "read"):
            raise HTTPException(
                status_code=400,
                detail="Invitation role must be 'write' or 'read'",
            )

        token = secrets.token_urlsafe(32)
        inv = await db.create_invitation(
            token=token,
            role=body.role,
            created_by=current["id"],
            expires_in_hours=body.expires_in_hours,
        )
        return {
            "id": inv["id"],
            "token": inv["token"],
            "role": inv["role"],
            "expires_at": inv["expires_at"],
            "created_at": inv["created_at"],
            "invite_url_path": f"/invite/{inv['token']}",
        }

    @router.get("/admin/invitations")
    async def list_invitations():
        invites = await db.list_active_invitations()
        return [
            {
                "id": inv["id"],
                "token": inv["token"],
                "role": inv["role"],
                "expires_at": inv["expires_at"],
                "created_at": inv["created_at"],
                "created_by": inv["created_by"],
                "invite_url_path": f"/invite/{inv['token']}",
            }
            for inv in invites
        ]

    @router.delete("/admin/invitations/{invitation_id}")
    async def revoke_invitation(invitation_id: int):
        deleted = await db.delete_invitation(invitation_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Invitation not found")
        return {"message": "Invitation revoked"}

    return router
