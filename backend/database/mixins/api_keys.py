import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ApiKeyMixin:
    """API key management. Requires self._acquire()."""

    async def create_api_key(self, name: str, key_hash: str, role: str) -> dict:
        """Insert a new API key (hashed) and return its metadata."""
        async with self._acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO api_keys (name, key_hash, role)
                VALUES ($1, $2, $3)
                RETURNING id, name, role, created_at
            """, name, key_hash, role)
            return {
                'id': row['id'],
                'name': row['name'],
                'role': row['role'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            }

    async def list_api_keys(self) -> list[dict]:
        """Return all non-revoked API keys (metadata only, no hash)."""
        async with self._acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, role, created_at
                FROM api_keys
                WHERE revoked_at IS NULL
                ORDER BY created_at DESC
            """)
            return [
                {
                    'id': row['id'],
                    'name': row['name'],
                    'role': row['role'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                }
                for row in rows
            ]

    async def revoke_api_key(self, key_id: int) -> bool:
        """Revoke an API key by setting revoked_at. Returns True if a row was updated."""
        async with self._acquire() as conn:
            result = await conn.execute("""
                UPDATE api_keys
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND revoked_at IS NULL
            """, key_id)
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def validate_api_key(self, key_hash: str) -> Optional[str]:
        """Look up a key hash and return its role if valid (non-revoked), else None."""
        async with self._acquire() as conn:
            row = await conn.fetchrow("""
                SELECT role FROM api_keys
                WHERE key_hash = $1 AND revoked_at IS NULL
            """, key_hash)
            return row['role'] if row else None
