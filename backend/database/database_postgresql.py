import asyncpg
import logging
import os
import json
from typing import List
from datetime import datetime, timezone
from .database_base import DatabaseInterface
from models.models import PodFailureResponse

logger = logging.getLogger(__name__)


class PostgreSQLDatabase(DatabaseInterface):
    def __init__(self):
        self.pool = None
        self.connection_string = self._get_connection_string()
    
    def _normalize_timestamp(self, timestamp) -> datetime:
        """Convert timestamp to timezone-aware datetime object"""
        if isinstance(timestamp, datetime):
            # If it's already a datetime, ensure it has timezone info
            if timestamp.tzinfo is None:
                # Assume UTC if no timezone info
                return timestamp.replace(tzinfo=timezone.utc)
            return timestamp
        elif isinstance(timestamp, str):
            # Handle string timestamps
            try:
                # Replace 'Z' with '+00:00' for ISO format
                timestamp_str = timestamp.replace('Z', '+00:00')
                # Parse with timezone info
                dt = datetime.fromisoformat(timestamp_str)
                return dt
            except ValueError:
                # Fallback: try parsing as naive datetime and assume UTC
                try:
                    dt = datetime.fromisoformat(timestamp)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    # Last resort: use current time
                    logger.warning(f"Could not parse timestamp '{timestamp}', using current time")
                    return datetime.now(timezone.utc)
        else:
            # Fallback to current time
            logger.warning(f"Unknown timestamp type '{type(timestamp)}', using current time")
            return datetime.now(timezone.utc)

    def _get_connection_string(self) -> str:
        """Build PostgreSQL connection string from environment variables"""
        host = os.getenv("POSTGRES_HOST", "postgresql")
        port = os.getenv("POSTGRES_PORT", "5432")
        database = os.getenv("POSTGRES_DB", "kure")
        user = os.getenv("POSTGRES_USER", "kure_user")
        password = os.getenv("POSTGRES_PASSWORD", "kure_password_change_in_production")
        
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    async def init_database(self):
        """Initialize the PostgreSQL connection pool and create tables"""
        try:
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            
            # Create tables
            async with self.pool.acquire() as conn:
                # Drop existing table to ensure clean schema
                await conn.execute("DROP TABLE IF EXISTS pod_failures")
                
                await conn.execute("""
                    CREATE TABLE pod_failures (
                        id SERIAL PRIMARY KEY,
                        pod_name VARCHAR(255) NOT NULL,
                        namespace VARCHAR(255) NOT NULL,
                        node_name VARCHAR(255),
                        phase VARCHAR(50) NOT NULL,
                        creation_timestamp TIMESTAMPTZ NOT NULL,
                        failure_reason VARCHAR(255) NOT NULL,
                        failure_message TEXT,
                        container_statuses JSONB,
                        events JSONB,
                        logs TEXT,
                        manifest TEXT,
                        solution TEXT NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        dismissed BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes for better performance
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pod_failures_pod_namespace 
                    ON pod_failures(pod_name, namespace)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pod_failures_dismissed 
                    ON pod_failures(dismissed)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pod_failures_created_at 
                    ON pod_failures(created_at)
                """)
                
            logger.info("PostgreSQL database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")
            raise

    async def save_pod_failure(self, failure: PodFailureResponse) -> int:
        """Save a pod failure to database, updating existing record if pod already exists"""
        async with self.pool.acquire() as conn:
            # Check if pod already exists and is not dismissed
            existing = await conn.fetchrow("""
                SELECT id FROM pod_failures 
                WHERE pod_name = $1 AND namespace = $2 AND dismissed = FALSE
                ORDER BY created_at DESC LIMIT 1
            """, failure.pod_name, failure.namespace)
            
            # Convert datetime strings to proper datetime objects
            logger.info(f"Original timestamps - creation: {failure.creation_timestamp} (type: {type(failure.creation_timestamp)}), timestamp: {failure.timestamp} (type: {type(failure.timestamp)})")
            creation_timestamp = self._normalize_timestamp(failure.creation_timestamp)
            timestamp = self._normalize_timestamp(failure.timestamp)
            logger.info(f"Normalized timestamps - creation: {creation_timestamp} (tzinfo: {creation_timestamp.tzinfo}), timestamp: {timestamp} (tzinfo: {timestamp.tzinfo})")
            
            # Convert container statuses and events to JSON strings for JSONB
            container_statuses = json.dumps([status.dict() for status in failure.container_statuses])
            events = json.dumps([event.dict() for event in failure.events])
            
            if existing:
                # Update existing record
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
                # Insert new record
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

    async def get_pod_failures(self, include_dismissed: bool = False, dismissed_only: bool = False) -> List[PodFailureResponse]:
        """Get all pod failures from database (latest per pod)"""
        async with self.pool.acquire() as conn:
            # Get latest entry per pod (avoid duplicates) using PostgreSQL window functions
            query = """
                SELECT * FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (PARTITION BY pod_name, namespace ORDER BY created_at DESC) as rn
                    FROM pod_failures
                ) ranked
                WHERE rn = 1
            """
            
            if dismissed_only:
                query += " AND dismissed = TRUE"
            elif not include_dismissed:
                query += " AND dismissed = FALSE"
                
            query += " ORDER BY created_at DESC"

            rows = await conn.fetch(query)

            failures = []
            for row in rows:
                # Convert timestamps to ISO format strings
                creation_timestamp = row['creation_timestamp'].isoformat()
                timestamp = row['timestamp'].isoformat()
                
                failure = PodFailureResponse(
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
                    dismissed=bool(row['dismissed'])
                )
                failures.append(failure)

            return failures

    async def dismiss_pod_failure(self, failure_id: int):
        """Mark a pod failure as dismissed"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE pod_failures SET dismissed = TRUE WHERE id = $1",
                failure_id
            )

    async def restore_pod_failure(self, failure_id: int):
        """Restore a dismissed pod failure (unignore)"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE pod_failures SET dismissed = FALSE WHERE id = $1",
                failure_id
            )

    async def dismiss_deleted_pod(self, namespace: str, pod_name: str):
        """Mark all entries for a deleted pod as dismissed"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE pod_failures SET dismissed = TRUE WHERE pod_name = $1 AND namespace = $2",
                pod_name, namespace
            )

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()