"""DB-backed login rate limiter.

Persists failed-login counts per client IP in the `login_attempts` table so
all backend replicas share the same view. The window is sliding: if the
oldest tracked attempt for an IP is older than `window_seconds`, the count
is reset before incrementing.
"""

import logging

logger = logging.getLogger(__name__)


class LoginAttemptsMixin:
    """Login rate-limit storage. Requires self._acquire()."""

    async def record_failed_login(self, ip: str, window_seconds: int) -> int:
        """Record a failed login for `ip`. Resets the count if the first
        attempt in the current row is older than `window_seconds`.

        Returns the new in-window attempt count.
        """
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO login_attempts (ip, count, first_attempt_at, last_attempt_at)
                VALUES ($1, 1, NOW(), NOW())
                ON CONFLICT (ip) DO UPDATE SET
                    count = CASE
                        WHEN login_attempts.first_attempt_at < NOW() - make_interval(secs => $2)
                            THEN 1
                        ELSE login_attempts.count + 1
                    END,
                    first_attempt_at = CASE
                        WHEN login_attempts.first_attempt_at < NOW() - make_interval(secs => $2)
                            THEN NOW()
                        ELSE login_attempts.first_attempt_at
                    END,
                    last_attempt_at = NOW()
                RETURNING count
                """,
                ip,
                window_seconds,
            )
            return int(row["count"]) if row else 0

    async def get_login_attempt_count(self, ip: str, window_seconds: int) -> int:
        """Return the current in-window failed-login count for `ip`.

        If the existing row's first_attempt_at is older than `window_seconds`,
        the count is considered stale and 0 is returned.
        """
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT count, first_attempt_at
                FROM login_attempts
                WHERE ip = $1
                  AND first_attempt_at >= NOW() - make_interval(secs => $2)
                """,
                ip,
                window_seconds,
            )
            return int(row["count"]) if row else 0

    async def clear_login_attempts(self, ip: str) -> None:
        """Remove the row for `ip` (called after a successful login)."""
        async with self._acquire() as conn:
            await conn.execute("DELETE FROM login_attempts WHERE ip = $1", ip)

    async def cleanup_old_login_attempts(self, older_than_seconds: int) -> int:
        """Sweep rows whose last_attempt_at is older than `older_than_seconds`.

        Not wired up to a periodic task by default — admin can schedule this
        helper if desired. Returns the number of rows deleted.
        """
        async with self._acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM login_attempts
                WHERE last_attempt_at < NOW() - make_interval(secs => $1)
                """,
                older_than_seconds,
            )
            # asyncpg returns 'DELETE <n>' for execute()
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0
