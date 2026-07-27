import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class ChatOpsMixin:
    async def save_chatops_message(
        self,
        pod_failure_id: int,
        provider: str,
        channel_id: str,
        message_id: str,
    ) -> int:
        """Save a mapping between a pod failure and a chat notification message."""
        try:
            async with self._acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO chatops_messages (
                        pod_failure_id, provider, channel_id, message_id
                    )
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    pod_failure_id,
                    provider,
                    channel_id,
                    message_id,
                )
                return row["id"]
        except Exception as e:
            logger.error(f"Error saving chatops message: {e}")
            raise

    async def get_chatops_message(
        self, pod_failure_id: int, provider: str
    ) -> Optional[Dict]:
        """Get the chatops message mapping for a pod failure and provider."""
        try:
            async with self._acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, pod_failure_id, provider, channel_id, message_id, created_at
                    FROM chatops_messages
                    WHERE pod_failure_id = $1 AND provider = $2
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    pod_failure_id,
                    provider,
                )
                if not row:
                    return None
                return dict(row)
        except Exception as e:
            logger.error(f"Error getting chatops message: {e}")
            raise

    async def get_chatops_message_by_message_id(
        self, provider: str, message_id: str
    ) -> Optional[Dict]:
        """Get the chatops message mapping by message ID."""
        try:
            async with self._acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, pod_failure_id, provider, channel_id, message_id, created_at
                    FROM chatops_messages
                    WHERE provider = $1 AND message_id = $2
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    provider,
                    message_id,
                )
                if not row:
                    return None
                return dict(row)
        except Exception as e:
            logger.error(f"Error getting chatops message by message id: {e}")
            raise
