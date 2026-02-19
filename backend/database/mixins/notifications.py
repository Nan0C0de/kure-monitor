import json
import logging
from typing import List, Optional
from models.models import NotificationSettingResponse

logger = logging.getLogger(__name__)


class NotificationMixin:
    """Notification settings CRUD. Requires self._acquire()."""

    async def save_notification_setting(self, setting) -> NotificationSettingResponse:
        """Create or update notification setting for a provider"""
        async with self._acquire() as conn:
            config_json = json.dumps(setting.config)

            result = await conn.fetchrow("""
                INSERT INTO notification_settings (provider, enabled, config, updated_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                ON CONFLICT (provider) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    config = EXCLUDED.config,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, provider, enabled, config, created_at, updated_at
            """, setting.provider, setting.enabled, config_json)

            return NotificationSettingResponse(
                id=result['id'],
                provider=result['provider'],
                enabled=result['enabled'],
                config=json.loads(result['config']),
                created_at=result['created_at'].isoformat() if result['created_at'] else None,
                updated_at=result['updated_at'].isoformat() if result['updated_at'] else None
            )

    async def get_notification_settings(self) -> List[NotificationSettingResponse]:
        """Get all notification settings"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, provider, enabled, config, created_at, updated_at FROM notification_settings ORDER BY provider"
            )
            return [
                NotificationSettingResponse(
                    id=row['id'],
                    provider=row['provider'],
                    enabled=row['enabled'],
                    config=json.loads(row['config']),
                    created_at=row['created_at'].isoformat() if row['created_at'] else None,
                    updated_at=row['updated_at'].isoformat() if row['updated_at'] else None
                )
                for row in rows
            ]

    async def get_notification_setting(self, provider: str) -> Optional[NotificationSettingResponse]:
        """Get notification setting for a specific provider"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, provider, enabled, config, created_at, updated_at FROM notification_settings WHERE provider = $1",
                provider
            )
            if not row:
                return None

            return NotificationSettingResponse(
                id=row['id'],
                provider=row['provider'],
                enabled=row['enabled'],
                config=json.loads(row['config']),
                created_at=row['created_at'].isoformat() if row['created_at'] else None,
                updated_at=row['updated_at'].isoformat() if row['updated_at'] else None
            )

    async def get_enabled_notification_settings(self) -> List[NotificationSettingResponse]:
        """Get all enabled notification settings"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, provider, enabled, config, created_at, updated_at FROM notification_settings WHERE enabled = TRUE"
            )
            return [
                NotificationSettingResponse(
                    id=row['id'],
                    provider=row['provider'],
                    enabled=row['enabled'],
                    config=json.loads(row['config']),
                    created_at=row['created_at'].isoformat() if row['created_at'] else None,
                    updated_at=row['updated_at'].isoformat() if row['updated_at'] else None
                )
                for row in rows
            ]

    async def update_notification_setting(self, provider: str, setting) -> Optional[NotificationSettingResponse]:
        """Update notification setting for a provider"""
        async with self._acquire() as conn:
            config_json = json.dumps(setting.config)

            result = await conn.fetchrow("""
                UPDATE notification_settings SET
                    enabled = $1,
                    config = $2,
                    updated_at = CURRENT_TIMESTAMP
                WHERE provider = $3
                RETURNING id, provider, enabled, config, created_at, updated_at
            """, setting.enabled, config_json, provider)

            if not result:
                return None

            return NotificationSettingResponse(
                id=result['id'],
                provider=result['provider'],
                enabled=result['enabled'],
                config=json.loads(result['config']),
                created_at=result['created_at'].isoformat() if result['created_at'] else None,
                updated_at=result['updated_at'].isoformat() if result['updated_at'] else None
            )

    async def delete_notification_setting(self, provider: str) -> bool:
        """Delete notification setting for a provider"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM notification_settings WHERE provider = $1",
                provider
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0
