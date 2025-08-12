import aiosqlite
import json
import logging
from typing import List
from datetime import datetime
from .database_base import DatabaseInterface
from models.models import PodFailureResponse

logger = logging.getLogger(__name__)


class SQLiteDatabase(DatabaseInterface):
    def __init__(self, db_path: str = "kure.db"):
        self.db_path = db_path

    async def init_database(self):
        """Initialize the SQLite database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS pod_failures (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pod_name TEXT NOT NULL,
                        namespace TEXT NOT NULL,
                        node_name TEXT,
                        phase TEXT NOT NULL,
                        creation_timestamp TEXT NOT NULL,
                        failure_reason TEXT NOT NULL,
                        failure_message TEXT,
                        container_statuses TEXT,
                        events TEXT,
                        logs TEXT,
                        manifest TEXT,
                        solution TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        dismissed BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes for better performance
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pod_failures_pod_namespace 
                    ON pod_failures(pod_name, namespace)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pod_failures_dismissed 
                    ON pod_failures(dismissed)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pod_failures_created_at 
                    ON pod_failures(created_at)
                """)
                
                await db.commit()
                
            logger.info(f"SQLite database initialized successfully at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")
            raise

    async def save_pod_failure(self, failure: PodFailureResponse) -> int:
        """Save a pod failure to database, updating existing record if pod already exists"""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if pod already exists and is not dismissed
            cursor = await db.execute("""
                SELECT id FROM pod_failures 
                WHERE pod_name = ? AND namespace = ? AND dismissed = FALSE
                ORDER BY created_at DESC LIMIT 1
            """, (failure.pod_name, failure.namespace))
            existing = await cursor.fetchone()
            
            if existing:
                # Update existing record
                await db.execute("""
                    UPDATE pod_failures SET
                        node_name = ?, phase = ?, creation_timestamp = ?,
                        failure_reason = ?, failure_message = ?, container_statuses = ?,
                        events = ?, logs = ?, manifest = ?, solution = ?, timestamp = ?,
                        created_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    failure.node_name,
                    failure.phase,
                    failure.creation_timestamp,
                    failure.failure_reason,
                    failure.failure_message,
                    json.dumps([status.dict() for status in failure.container_statuses]),
                    json.dumps([event.dict() for event in failure.events]),
                    failure.logs,
                    failure.manifest,
                    failure.solution,
                    failure.timestamp,
                    existing[0]
                ))
                await db.commit()
                return existing[0]
            else:
                # Insert new record
                cursor = await db.execute("""
                    INSERT INTO pod_failures (
                        pod_name, namespace, node_name, phase, creation_timestamp,
                        failure_reason, failure_message, container_statuses, events,
                        logs, manifest, solution, timestamp, dismissed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    failure.pod_name,
                    failure.namespace,
                    failure.node_name,
                    failure.phase,
                    failure.creation_timestamp,
                    failure.failure_reason,
                    failure.failure_message,
                    json.dumps([status.dict() for status in failure.container_statuses]),
                    json.dumps([event.dict() for event in failure.events]),
                    failure.logs,
                    failure.manifest,
                    failure.solution,
                    failure.timestamp,
                    failure.dismissed
                ))
                await db.commit()
                return cursor.lastrowid

    async def get_pod_failures(self, include_dismissed: bool = False, dismissed_only: bool = False) -> List[PodFailureResponse]:
        """Get all pod failures from database (latest per pod)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get latest entry per pod (avoid duplicates)
            query = """
                SELECT * FROM pod_failures pf1
                WHERE pf1.id = (
                    SELECT MAX(pf2.id) FROM pod_failures pf2 
                    WHERE pf2.pod_name = pf1.pod_name 
                    AND pf2.namespace = pf1.namespace
                )
            """
            if dismissed_only:
                query += " AND pf1.dismissed = TRUE"
            elif not include_dismissed:
                query += " AND pf1.dismissed = FALSE"
            query += " ORDER BY pf1.created_at DESC"

            cursor = await db.execute(query)
            rows = await cursor.fetchall()

            failures = []
            for row in rows:
                failure = PodFailureResponse(
                    id=row['id'],
                    pod_name=row['pod_name'],
                    namespace=row['namespace'],
                    node_name=row['node_name'],
                    phase=row['phase'],
                    creation_timestamp=row['creation_timestamp'],
                    failure_reason=row['failure_reason'],
                    failure_message=row['failure_message'],
                    container_statuses=json.loads(row['container_statuses']) if row['container_statuses'] else [],
                    events=json.loads(row['events']) if row['events'] else [],
                    logs=row['logs'],
                    manifest=row['manifest'] or '',
                    solution=row['solution'],
                    timestamp=row['timestamp'],
                    dismissed=bool(row['dismissed'])
                )
                failures.append(failure)

            return failures

    async def dismiss_pod_failure(self, failure_id: int):
        """Mark a pod failure as dismissed"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE pod_failures SET dismissed = TRUE WHERE id = ?",
                (failure_id,)
            )
            await db.commit()

    async def restore_pod_failure(self, failure_id: int):
        """Restore a dismissed pod failure (unignore)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE pod_failures SET dismissed = FALSE WHERE id = ?",
                (failure_id,)
            )
            await db.commit()

    async def dismiss_deleted_pod(self, namespace: str, pod_name: str):
        """Mark all entries for a deleted pod as dismissed"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE pod_failures SET dismissed = TRUE WHERE pod_name = ? AND namespace = ?",
                (pod_name, namespace)
            )
            await db.commit()

    async def close(self):
        """Close database connection"""
        # SQLite connections are closed automatically with async context managers
        pass