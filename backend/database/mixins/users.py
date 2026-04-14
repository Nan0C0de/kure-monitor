"""User and invitation database operations."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class UserMixin:
    """User account + invitation management. Requires self._acquire()."""

    # --- Users ---

    async def count_users(self) -> int:
        """Count total users."""
        async with self._acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM users")

    async def count_admins(self) -> int:
        """Count admins."""
        async with self._acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM users WHERE role = 'admin'")

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role: str,
        email: Optional[str] = None,
    ) -> dict:
        """Insert a new user. Returns {id, username, email, role, created_at}."""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (username, password_hash, email, role)
                VALUES ($1, $2, $3, $4)
                RETURNING id, username, email, role, created_at, updated_at
                """,
                username,
                password_hash,
                email,
                role,
            )
            return _user_row_to_dict(row)

    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, role, password_hash, created_at, updated_at
                FROM users WHERE id = $1
                """,
                user_id,
            )
            return _user_row_to_dict(row, include_hash=True) if row else None

    async def get_user_by_username(self, username: str) -> Optional[dict]:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, role, password_hash, created_at, updated_at
                FROM users WHERE username = $1
                """,
                username,
            )
            return _user_row_to_dict(row, include_hash=True) if row else None

    async def list_users(self) -> list[dict]:
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, username, email, role, created_at, updated_at
                FROM users ORDER BY created_at ASC
                """
            )
            return [_user_row_to_dict(r) for r in rows]

    async def update_user_role(self, user_id: int, role: str) -> Optional[dict]:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE users
                SET role = $1, updated_at = now()
                WHERE id = $2
                RETURNING id, username, email, role, created_at, updated_at
                """,
                role,
                user_id,
            )
            return _user_row_to_dict(row) if row else None

    async def delete_user(self, user_id: int) -> bool:
        async with self._acquire() as conn:
            result = await conn.execute("DELETE FROM users WHERE id = $1", user_id)
            count = int(result.split()[-1]) if result else 0
            return count > 0

    # --- Invitations ---

    async def create_invitation(
        self,
        token: str,
        role: str,
        created_by: Optional[int],
        expires_in_hours: int = 72,
    ) -> dict:
        """Insert a new invitation. Returns {id, token, role, expires_at, created_at}."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO invitations (token, role, created_by, expires_at)
                VALUES ($1, $2, $3, $4)
                RETURNING id, token, role, created_by, expires_at, used_at, used_by, created_at
                """,
                token,
                role,
                created_by,
                expires_at,
            )
            return _invitation_row_to_dict(row)

    async def get_invitation_by_token(self, token: str) -> Optional[dict]:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, token, role, created_by, expires_at, used_at, used_by, created_at
                FROM invitations WHERE token = $1
                """,
                token,
            )
            return _invitation_row_to_dict(row) if row else None

    async def get_invitation_by_id(self, invitation_id: int) -> Optional[dict]:
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, token, role, created_by, expires_at, used_at, used_by, created_at
                FROM invitations WHERE id = $1
                """,
                invitation_id,
            )
            return _invitation_row_to_dict(row) if row else None

    async def list_active_invitations(self) -> list[dict]:
        """List invitations that are not used and not expired."""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, token, role, created_by, expires_at, used_at, used_by, created_at
                FROM invitations
                WHERE used_at IS NULL AND expires_at > now()
                ORDER BY created_at DESC
                """
            )
            return [_invitation_row_to_dict(r) for r in rows]

    async def mark_invitation_used(self, invitation_id: int, used_by: int) -> bool:
        async with self._acquire() as conn:
            result = await conn.execute(
                """
                UPDATE invitations
                SET used_at = now(), used_by = $1
                WHERE id = $2 AND used_at IS NULL
                """,
                used_by,
                invitation_id,
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def delete_invitation(self, invitation_id: int) -> bool:
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM invitations WHERE id = $1",
                invitation_id,
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0


def _iso(value) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else value


def _user_row_to_dict(row, include_hash: bool = False) -> Optional[dict]:
    if row is None:
        return None
    d = {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }
    if include_hash:
        d["password_hash"] = row["password_hash"]
    return d


def _invitation_row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return {
        "id": row["id"],
        "token": row["token"],
        "role": row["role"],
        "created_by": row["created_by"],
        "expires_at": _iso(row["expires_at"]),
        "used_at": _iso(row["used_at"]),
        "used_by": row["used_by"],
        "created_at": _iso(row["created_at"]),
    }
