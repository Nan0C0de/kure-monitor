import logging
from typing import Optional

from services.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)


class LLMConfigMixin:
    """LLM config + app settings. Requires self._acquire()."""

    # --- Multi-LLM Config Methods (llm_configs table) ---

    async def get_all_llm_configs(self, active_only: bool = False) -> list[dict]:
        """Get all registered LLM configs from llm_configs table"""
        async with self._acquire() as conn:
            query = """
                SELECT id, name, provider, api_key_encrypted, model, base_url, is_default, is_active, priority, created_at, updated_at
                FROM llm_configs
            """
            if active_only:
                query += " WHERE is_active = TRUE"
            query += " ORDER BY is_default DESC, priority ASC, id ASC"

            rows = await conn.fetch(query)
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "provider": r["provider"],
                    "api_key": decrypt(r["api_key_encrypted"]),
                    "model": r["model"],
                    "base_url": r["base_url"],
                    "is_default": r["is_default"],
                    "is_active": r["is_active"],
                    "priority": r["priority"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                }
                for r in rows
            ]

    async def get_llm_config_by_id(self, config_id: int) -> Optional[dict]:
        """Get single registered LLM config by ID"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, provider, api_key_encrypted, model, base_url, is_default, is_active, priority, created_at, updated_at
                FROM llm_configs WHERE id = $1
                """,
                config_id,
            )
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "provider": row["provider"],
                "api_key": decrypt(row["api_key_encrypted"]),
                "model": row["model"],
                "base_url": row["base_url"],
                "is_default": row["is_default"],
                "is_active": row["is_active"],
                "priority": row["priority"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }

    async def get_default_llm_config(self) -> Optional[dict]:
        """Get the default LLM config, or the first active one if none marked default"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, provider, api_key_encrypted, model, base_url, is_default, is_active, priority, created_at, updated_at
                FROM llm_configs
                WHERE is_active = TRUE
                ORDER BY is_default DESC, priority ASC, id ASC
                LIMIT 1
                """
            )
            if not row:
                return None
            return {
                "id": row["id"],
                "name": row["name"],
                "provider": row["provider"],
                "api_key": decrypt(row["api_key_encrypted"]),
                "model": row["model"],
                "base_url": row["base_url"],
                "is_default": row["is_default"],
                "is_active": row["is_active"],
                "priority": row["priority"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }

    async def save_llm_config_item(
        self,
        name: str,
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        is_default: bool = False,
    ) -> dict:
        """Register a new LLM configuration. If first one or is_default=True, sets as default."""
        encrypted_key = encrypt(api_key)

        async with self._acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM llm_configs")
            make_default = is_default or (count == 0)

            if make_default:
                await conn.execute("UPDATE llm_configs SET is_default = FALSE")

            result = await conn.fetchrow(
                """
                INSERT INTO llm_configs (name, provider, api_key_encrypted, model, base_url, is_default, is_active, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id, name, provider, model, base_url, is_default, is_active, created_at, updated_at
                """,
                name,
                provider,
                encrypted_key,
                model,
                base_url,
                make_default,
            )

            # Also sync to legacy single-provider table so old queries continue to function
            if make_default:
                await conn.execute("DELETE FROM llm_config")
                await conn.execute(
                    """
                    INSERT INTO llm_config (provider, api_key_encrypted, model, base_url)
                    VALUES ($1, $2, $3, $4)
                    """,
                    provider,
                    encrypted_key,
                    model,
                    base_url,
                )

            return {
                "id": result["id"],
                "name": result["name"],
                "provider": result["provider"],
                "model": result["model"],
                "base_url": result["base_url"],
                "is_default": result["is_default"],
                "is_active": result["is_active"],
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
            }

    async def update_llm_config_item(
        self,
        config_id: int,
        name: Optional[str] = None,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        is_default: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[dict]:
        """Update an existing LLM configuration by ID"""
        async with self._acquire() as conn:
            existing = await conn.fetchrow("SELECT * FROM llm_configs WHERE id = $1", config_id)
            if not existing:
                return None

            new_name = name if name is not None else existing["name"]
            new_provider = provider if provider is not None else existing["provider"]
            new_encrypted_key = encrypt(api_key) if (api_key and api_key.strip()) else existing["api_key_encrypted"]
            new_model = model if model is not None else existing["model"]
            new_base_url = base_url if base_url is not None else existing["base_url"]
            new_active = is_active if is_active is not None else existing["is_active"]
            new_default = is_default if is_default is not None else existing["is_default"]

            if new_default and not existing["is_default"]:
                await conn.execute("UPDATE llm_configs SET is_default = FALSE")

            result = await conn.fetchrow(
                """
                UPDATE llm_configs
                SET name = $1, provider = $2, api_key_encrypted = $3, model = $4,
                    base_url = $5, is_default = $6, is_active = $7, updated_at = CURRENT_TIMESTAMP
                WHERE id = $8
                RETURNING id, name, provider, model, base_url, is_default, is_active, created_at, updated_at
                """,
                new_name,
                new_provider,
                new_encrypted_key,
                new_model,
                new_base_url,
                new_default,
                new_active,
                config_id,
            )

            # If this is default, update legacy table
            if new_default:
                await conn.execute("DELETE FROM llm_config")
                await conn.execute(
                    """
                    INSERT INTO llm_config (provider, api_key_encrypted, model, base_url)
                    VALUES ($1, $2, $3, $4)
                    """,
                    new_provider,
                    new_encrypted_key,
                    new_model,
                    new_base_url,
                )

            return {
                "id": result["id"],
                "name": result["name"],
                "provider": result["provider"],
                "model": result["model"],
                "base_url": result["base_url"],
                "is_default": result["is_default"],
                "is_active": result["is_active"],
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
            }

    async def set_default_llm_config(self, config_id: int) -> bool:
        """Set a registered LLM as the default and sync to legacy table"""
        async with self._acquire() as conn:
            target = await conn.fetchrow("SELECT * FROM llm_configs WHERE id = $1", config_id)
            if not target:
                return False

            await conn.execute("UPDATE llm_configs SET is_default = FALSE")
            await conn.execute(
                "UPDATE llm_configs SET is_default = TRUE, is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                config_id,
            )

            # Sync to legacy table
            await conn.execute("DELETE FROM llm_config")
            await conn.execute(
                """
                INSERT INTO llm_config (provider, api_key_encrypted, model, base_url)
                VALUES ($1, $2, $3, $4)
                """,
                target["provider"],
                target["api_key_encrypted"],
                target["model"],
                target["base_url"],
            )
            return True

    async def delete_llm_config_item(self, config_id: int) -> bool:
        """Delete an LLM config. If it was default, assign default to the next available config."""
        async with self._acquire() as conn:
            target = await conn.fetchrow("SELECT is_default FROM llm_configs WHERE id = $1", config_id)
            if not target:
                return False

            was_default = target["is_default"]
            await conn.execute("DELETE FROM llm_configs WHERE id = $1", config_id)

            if was_default:
                next_active = await conn.fetchrow(
                    "SELECT id, provider, api_key_encrypted, model, base_url FROM llm_configs WHERE is_active = TRUE ORDER BY priority ASC, id ASC LIMIT 1"
                )
                if next_active:
                    await conn.execute("UPDATE llm_configs SET is_default = TRUE WHERE id = $1", next_active["id"])
                    await conn.execute("DELETE FROM llm_config")
                    await conn.execute(
                        """
                        INSERT INTO llm_config (provider, api_key_encrypted, model, base_url)
                        VALUES ($1, $2, $3, $4)
                        """,
                        next_active["provider"],
                        next_active["api_key_encrypted"],
                        next_active["model"],
                        next_active["base_url"],
                    )
                else:
                    await conn.execute("DELETE FROM llm_config")

            return True

    # --- Legacy Single-Config Methods for Backward Compatibility ---

    async def save_llm_config(self, provider: str, api_key: str, model: Optional[str] = None, base_url: Optional[str] = None) -> dict:
        """Save or update LLM configuration (creates or updates default in llm_configs)"""
        name = f"{provider.capitalize()} (Default)"
        return await self.save_llm_config_item(
            name=name,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            is_default=True,
        )

    async def get_llm_config(self) -> Optional[dict]:
        """Get the default LLM configuration (returns None if not configured)"""
        default_item = await self.get_default_llm_config()
        if default_item:
            return default_item

        # Fallback to legacy single-provider table
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, provider, api_key_encrypted, model, base_url, created_at, updated_at FROM llm_config LIMIT 1"
            )
            if not row:
                return None

            return {
                'id': row['id'],
                'provider': row['provider'],
                'api_key': decrypt(row['api_key_encrypted']),
                'model': row['model'],
                'base_url': row['base_url'],
                'configured': True,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
            }

    async def delete_llm_config(self) -> bool:
        """Delete all LLM configurations"""
        async with self._acquire() as conn:
            await conn.execute("DELETE FROM llm_configs")
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
