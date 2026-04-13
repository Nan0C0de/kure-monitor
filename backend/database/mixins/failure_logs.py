"""Database mixin for captured pod failure logs and on-demand troubleshoot solutions."""

import base64
import gzip
import logging
from typing import List, Optional

from core.config import FAILURE_LOGS_MAX_BYTES
from models.models import FailureLogsPayload

logger = logging.getLogger(__name__)


class FailureLogsMixin:
    """Persistence for gzipped container logs plus log-aware troubleshoot caching.

    Requires self.pool and self._acquire() from the host class.
    """

    async def save_pod_failure_logs(
        self,
        pod_failure_id: int,
        payload: FailureLogsPayload,
    ) -> int:
        """Persist all non-null container log captures for a pod failure.

        The agent sends base64-of-gzip; we store the gzipped bytes as-is
        in BYTEA.  Returns the number of rows upserted.
        """
        if not payload or not payload.containers:
            return 0

        rows_written = 0
        async with self._acquire() as conn:
            for container_name, container_logs in payload.containers.items():
                for source in ("previous", "current"):
                    entry = getattr(container_logs, source, None)
                    if entry is None or not entry.data:
                        continue

                    try:
                        gzipped_bytes = base64.b64decode(entry.data)
                    except Exception as e:
                        logger.warning(
                            f"Failed to base64-decode logs for {container_name}/{source}: {e}"
                        )
                        continue

                    raw_size = int(entry.original_size or 0)
                    truncated = bool(entry.truncated)
                    if raw_size > FAILURE_LOGS_MAX_BYTES:
                        truncated = True

                    await conn.execute(
                        """
                        INSERT INTO pod_failure_logs (
                            pod_failure_id, container_name, logs_gzip,
                            raw_size_bytes, line_count, truncated, source
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (pod_failure_id, container_name, source) DO UPDATE SET
                            logs_gzip = EXCLUDED.logs_gzip,
                            raw_size_bytes = EXCLUDED.raw_size_bytes,
                            line_count = EXCLUDED.line_count,
                            truncated = EXCLUDED.truncated,
                            captured_at = CURRENT_TIMESTAMP
                        """,
                        pod_failure_id,
                        container_name,
                        gzipped_bytes,
                        raw_size,
                        int(entry.lines or 0),
                        truncated,
                        source,
                    )
                    rows_written += 1
        return rows_written

    async def get_pod_failure_logs(self, pod_failure_id: int) -> List[dict]:
        """Return decoded logs for a pod failure.

        Each item: {container_name, source, logs (str), truncated, line_count}.
        """
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT container_name, source, logs_gzip, truncated, line_count
                FROM pod_failure_logs
                WHERE pod_failure_id = $1
                ORDER BY container_name, source
                """,
                pod_failure_id,
            )

        results: List[dict] = []
        for row in rows:
            try:
                decompressed = gzip.decompress(row["logs_gzip"]).decode(
                    "utf-8", errors="replace"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to gzip-decompress logs for failure {pod_failure_id} "
                    f"{row['container_name']}/{row['source']}: {e}"
                )
                decompressed = ""
            results.append({
                "container_name": row["container_name"],
                "source": row["source"],
                "logs": decompressed,
                "truncated": row["truncated"],
                "line_count": row["line_count"],
            })
        return results

    async def has_captured_logs(self, pod_failure_id: int) -> bool:
        """Return True if any logs exist for this pod failure."""
        async with self._acquire() as conn:
            return bool(await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pod_failure_logs WHERE pod_failure_id = $1)",
                pod_failure_id,
            ))

    async def update_pod_troubleshoot_solution(
        self,
        pod_failure_id: int,
        solution: str,
    ) -> Optional[str]:
        """Persist a log-aware troubleshoot solution and return the ISO timestamp."""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE pod_failures
                SET troubleshoot_solution = $1,
                    troubleshoot_generated_at = CURRENT_TIMESTAMP
                WHERE id = $2
                RETURNING troubleshoot_generated_at
                """,
                solution,
                pod_failure_id,
            )
            if not row or not row["troubleshoot_generated_at"]:
                return None
            return row["troubleshoot_generated_at"].isoformat()
