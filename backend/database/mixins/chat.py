import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class ChatMixin:
    async def save_chat_message(self, pod_name: str, namespace: str, user_id: str, role: str, text: str):
        try:
            async with self._acquire() as conn:
                await conn.execute("""
                    INSERT INTO chat_history (pod_name, namespace, user_id, role, text)
                    VALUES ($1, $2, $3, $4, $5)
                """, pod_name, namespace, user_id, role, text)
        except Exception as e:
            logger.error(f"Error saving chat message: {e}")
            raise

    async def get_chat_history(self, pod_name: str, namespace: str, user_id: str) -> List[Dict]:
        try:
            async with self._acquire() as conn:
                rows = await conn.fetch("""
                    SELECT role, text
                    FROM chat_history
                    WHERE pod_name = $1 AND namespace = $2 AND user_id = $3
                    ORDER BY created_at ASC
                """, pod_name, namespace, user_id)
                return [{"role": r["role"], "text": r["text"]} for r in rows]
        except Exception as e:
            logger.error(f"Error getting chat history: {e}")
            raise

    async def get_chat_sessions(self, user_id: str) -> List[Dict]:
        try:
            async with self._acquire() as conn:
                rows = await conn.fetch("""
                    SELECT pod_name, namespace, COUNT(*) as message_count
                    FROM chat_history
                    WHERE user_id = $1
                    GROUP BY pod_name, namespace
                """, user_id)
                return [{"pod_name": r["pod_name"], "namespace": r["namespace"], "message_count": r["message_count"]} for r in rows]
        except Exception as e:
            logger.error(f"Error getting chat sessions: {e}")
            raise

    async def delete_chat_history(self, pod_name: str, namespace: str, user_id: str):
        try:
            async with self._acquire() as conn:
                await conn.execute("""
                    DELETE FROM chat_history
                    WHERE pod_name = $1 AND namespace = $2 AND user_id = $3
                """, pod_name, namespace, user_id)
        except Exception as e:
            logger.error(f"Error deleting chat history: {e}")
            raise
