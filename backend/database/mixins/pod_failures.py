import json
import logging
from typing import List, Optional
from models.models import PodFailureResponse

logger = logging.getLogger(__name__)


class PodFailureMixin:
    """Pod failure CRUD and cleanup methods. Requires self.pool and self._acquire()."""

    def _row_to_pod_failure(self, row) -> PodFailureResponse:
        """Convert a database row to a PodFailureResponse"""
        creation_timestamp = row['creation_timestamp'].isoformat()
        timestamp = row['timestamp'].isoformat()
        resolved_at = row['resolved_at'].isoformat() if row.get('resolved_at') else None
        status = row.get('status', 'new')
        dismissed = status in ('resolved', 'ignored') or bool(row.get('dismissed', False))

        return PodFailureResponse(
            id=row['id'],
            pod_name=row['pod_name'],
            namespace=row['namespace'],
            node_name=row['node_name'],
            phase=row['phase'],
            creation_timestamp=creation_timestamp,
            failure_reason=row['failure_reason'],
            failure_message=row['failure_message'],
            container_statuses=json.loads(row['container_statuses']) if row['container_statuses'] else [],
            events=json.loads(row['events']) if row['events'] else [],
            logs=row['logs'],
            manifest=row['manifest'] or '',
            solution=row['solution'],
            timestamp=timestamp,
            dismissed=dismissed,
            status=status,
            resolved_at=resolved_at,
            resolution_note=row.get('resolution_note'),
        )

    async def save_pod_failure(self, failure: PodFailureResponse) -> int:
        """Save a pod failure to database, updating existing record if pod already exists"""
        async with self._acquire() as conn:
            existing = await conn.fetchrow("""
                SELECT id FROM pod_failures
                WHERE pod_name = $1 AND namespace = $2 AND status IN ('new', 'investigating')
                ORDER BY created_at DESC LIMIT 1
            """, failure.pod_name, failure.namespace)

            logger.info(f"Original timestamps - creation: {failure.creation_timestamp} (type: {type(failure.creation_timestamp)}), timestamp: {failure.timestamp} (type: {type(failure.timestamp)})")
            creation_timestamp = self._normalize_timestamp(failure.creation_timestamp)
            timestamp = self._normalize_timestamp(failure.timestamp)
            logger.info(f"Normalized timestamps - creation: {creation_timestamp} (tzinfo: {creation_timestamp.tzinfo}), timestamp: {timestamp} (tzinfo: {timestamp.tzinfo})")

            container_statuses = json.dumps([status.dict() for status in failure.container_statuses])
            events = json.dumps([event.dict() for event in failure.events])

            if existing:
                await conn.execute("""
                    UPDATE pod_failures SET
                        node_name = $1, phase = $2, creation_timestamp = $3,
                        failure_reason = $4, failure_message = $5, container_statuses = $6,
                        events = $7, logs = $8, manifest = $9, solution = $10, timestamp = $11,
                        created_at = CURRENT_TIMESTAMP
                    WHERE id = $12
                """,
                    failure.node_name, failure.phase, creation_timestamp,
                    failure.failure_reason, failure.failure_message, container_statuses,
                    events, failure.logs, failure.manifest, failure.solution, timestamp,
                    existing['id']
                )
                return existing['id']
            else:
                result = await conn.fetchrow("""
                    INSERT INTO pod_failures (
                        pod_name, namespace, node_name, phase, creation_timestamp,
                        failure_reason, failure_message, container_statuses, events,
                        logs, manifest, solution, timestamp, dismissed
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    RETURNING id
                """,
                    failure.pod_name, failure.namespace, failure.node_name, failure.phase,
                    creation_timestamp, failure.failure_reason, failure.failure_message,
                    container_statuses, events, failure.logs, failure.manifest,
                    failure.solution, timestamp, failure.dismissed
                )
                return result['id']

    async def get_pod_failures(self, status_filter: list = None, include_dismissed: bool = False, dismissed_only: bool = False) -> List[PodFailureResponse]:
        """Get all pod failures from database (latest per pod)"""
        async with self._acquire() as conn:
            query = """
                SELECT * FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (PARTITION BY pod_name, namespace ORDER BY created_at DESC) as rn
                    FROM pod_failures
                ) ranked
                WHERE rn = 1
            """

            params = []
            if status_filter:
                placeholders = ', '.join(f'${i+1}' for i in range(len(status_filter)))
                query += f" AND status IN ({placeholders})"
                params = list(status_filter)
            elif dismissed_only:
                query += " AND status = 'ignored'"
            elif not include_dismissed:
                query += " AND status IN ('new', 'investigating')"

            query += " ORDER BY created_at DESC"

            rows = await conn.fetch(query, *params)
            return [self._row_to_pod_failure(row) for row in rows]

    async def get_pod_failure_by_id(self, failure_id: int) -> Optional[PodFailureResponse]:
        """Get a single pod failure by ID"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM pod_failures WHERE id = $1",
                failure_id
            )
            if not row:
                return None
            return self._row_to_pod_failure(row)

    async def update_pod_solution(self, failure_id: int, solution: str):
        """Update just the solution for a pod failure"""
        async with self._acquire() as conn:
            await conn.execute(
                "UPDATE pod_failures SET solution = $1 WHERE id = $2",
                solution, failure_id
            )

    async def update_pod_status(self, failure_id: int, status: str, resolution_note: str = None) -> Optional[PodFailureResponse]:
        """Update the status of a pod failure and return the updated record"""
        async with self._acquire() as conn:
            dismissed = status in ('resolved', 'ignored')
            if status == 'resolved':
                await conn.execute(
                    """UPDATE pod_failures
                       SET status = $1, dismissed = $2, resolved_at = CURRENT_TIMESTAMP, resolution_note = $3
                       WHERE id = $4""",
                    status, dismissed, resolution_note, failure_id
                )
            else:
                await conn.execute(
                    """UPDATE pod_failures
                       SET status = $1, dismissed = $2, resolved_at = NULL, resolution_note = NULL
                       WHERE id = $3""",
                    status, dismissed, failure_id
                )
            row = await conn.fetchrow("SELECT * FROM pod_failures WHERE id = $1", failure_id)
            if not row:
                return None
            return self._row_to_pod_failure(row)

    async def dismiss_pod_failure(self, failure_id: int):
        """Mark a pod failure as ignored (backward compat)"""
        await self.update_pod_status(failure_id, 'ignored')

    async def restore_pod_failure(self, failure_id: int):
        """Restore a pod failure back to new (backward compat)"""
        await self.update_pod_status(failure_id, 'new')

    async def dismiss_deleted_pod(self, namespace: str, pod_name: str):
        """Auto-resolve all active entries for a recovered/deleted pod"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """UPDATE pod_failures
                   SET status = 'resolved', dismissed = TRUE,
                       resolved_at = CURRENT_TIMESTAMP,
                       resolution_note = 'Auto-resolved: pod recovered'
                   WHERE pod_name = $1 AND namespace = $2 AND status IN ('new', 'investigating')
                   RETURNING *""",
                pod_name, namespace
            )
            return [self._row_to_pod_failure(row) for row in rows]

    async def delete_pod_failure(self, failure_id: int) -> bool:
        """Hard delete a resolved or ignored pod failure record"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM pod_failures WHERE id = $1 AND status IN ('resolved', 'ignored')",
                failure_id
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def cleanup_old_resolved_pods(self, retention_minutes: int) -> int:
        """Delete resolved pods older than the retention period (in minutes)."""
        async with self._acquire() as conn:
            result = await conn.execute(
                """DELETE FROM pod_failures
                   WHERE status = 'resolved'
                   AND resolved_at < NOW() - INTERVAL '1 minute' * $1""",
                retention_minutes
            )
            count = int(result.split()[-1]) if result else 0
            return count

    async def cleanup_old_ignored_pods(self, retention_minutes: int) -> int:
        """Delete ignored pods older than the retention period (in minutes)."""
        async with self._acquire() as conn:
            result = await conn.execute(
                """DELETE FROM pod_failures
                   WHERE status = 'ignored'
                   AND created_at < NOW() - INTERVAL '1 minute' * $1""",
                retention_minutes
            )
            count = int(result.split()[-1]) if result else 0
            return count
