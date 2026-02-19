import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMConfigMixin:
    """LLM config + app settings. Requires self._acquire()."""

    async def save_llm_config(self, provider: str, api_key: str, model: Optional[str] = None) -> dict:
        """Save or update LLM configuration (only one config allowed)"""
        async with self._acquire() as conn:
            await conn.execute("DELETE FROM llm_config")

            result = await conn.fetchrow("""
                INSERT INTO llm_config (provider, api_key_encrypted, model)
                VALUES ($1, $2, $3)
                RETURNING id, provider, model, created_at, updated_at
            """, provider, api_key, model)

            return {
                'id': result['id'],
                'provider': result['provider'],
                'model': result['model'],
                'configured': True,
                'created_at': result['created_at'].isoformat() if result['created_at'] else None,
                'updated_at': result['updated_at'].isoformat() if result['updated_at'] else None
            }

    async def get_llm_config(self) -> Optional[dict]:
        """Get the LLM configuration (returns None if not configured)"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, provider, api_key_encrypted, model, created_at, updated_at FROM llm_config LIMIT 1"
            )
            if not row:
                return None

            return {
                'id': row['id'],
                'provider': row['provider'],
                'api_key': row['api_key_encrypted'],
                'model': row['model'],
                'configured': True,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
            }

    async def delete_llm_config(self) -> bool:
        """Delete the LLM configuration"""
        async with self._acquire() as conn:
            result = await conn.execute("DELETE FROM llm_config")
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_app_setting(self, key: str) -> Optional[str]:
        """Get an app setting value by key"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM app_settings WHERE key = $1", key
            )
            return row['value'] if row else None

    async def set_app_setting(self, key: str, value: str):
        """Set an app setting (upsert)"""
        async with self._acquire() as conn:
            await conn.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP
            """, key, value)
