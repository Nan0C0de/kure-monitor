import asyncpg
import logging
import os
import json
from typing import List
from datetime import datetime, timezone
from .database_base import DatabaseInterface
from models.models import PodFailureResponse, SecurityFindingResponse, ExcludedNamespaceResponse

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
        """Get PostgreSQL connection string from DATABASE_URL environment variable"""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")
        
        return database_url

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

                # Create security_findings table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS security_findings (
                        id SERIAL PRIMARY KEY,
                        resource_type VARCHAR(255) NOT NULL,
                        resource_name VARCHAR(255) NOT NULL,
                        namespace VARCHAR(255) NOT NULL,
                        severity VARCHAR(50) NOT NULL,
                        category VARCHAR(255) NOT NULL,
                        title VARCHAR(500) NOT NULL,
                        description TEXT NOT NULL,
                        remediation TEXT NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        dismissed BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create indexes for security findings
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_security_findings_resource
                    ON security_findings(resource_name, namespace)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_security_findings_severity
                    ON security_findings(severity)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_security_findings_dismissed
                    ON security_findings(dismissed)
                """)

                # Create excluded_namespaces table for admin settings
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS excluded_namespaces (
                        id SERIAL PRIMARY KEY,
                        namespace VARCHAR(255) NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_excluded_namespaces_namespace
                    ON excluded_namespaces(namespace)
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

    async def save_security_finding(self, finding: SecurityFindingResponse) -> tuple[int, bool]:
        """Save a security finding to database

        Returns:
            tuple[int, bool]: (finding_id, is_new) where is_new indicates if this is a new finding
        """
        async with self.pool.acquire() as conn:
            timestamp = self._normalize_timestamp(finding.timestamp)

            # Check if finding already exists (same resource, title, and not dismissed)
            existing = await conn.fetchrow("""
                SELECT id FROM security_findings
                WHERE resource_name = $1 AND namespace = $2 AND title = $3 AND dismissed = FALSE
                ORDER BY created_at DESC LIMIT 1
            """, finding.resource_name, finding.namespace, finding.title)

            if existing:
                # Update existing record - don't update created_at to preserve original creation time
                await conn.execute("""
                    UPDATE security_findings SET
                        resource_type = $1, severity = $2, category = $3,
                        description = $4, remediation = $5, timestamp = $6
                    WHERE id = $7
                """,
                    finding.resource_type, finding.severity, finding.category,
                    finding.description, finding.remediation, timestamp,
                    existing['id']
                )
                return existing['id'], False
            else:
                # Insert new record
                result = await conn.fetchrow("""
                    INSERT INTO security_findings (
                        resource_type, resource_name, namespace, severity, category,
                        title, description, remediation, timestamp, dismissed
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id
                """,
                    finding.resource_type, finding.resource_name, finding.namespace,
                    finding.severity, finding.category, finding.title,
                    finding.description, finding.remediation, timestamp, finding.dismissed
                )
                return result['id'], True

    async def get_security_findings(self, include_dismissed: bool = False, dismissed_only: bool = False) -> List[SecurityFindingResponse]:
        """Get all security findings from database"""
        async with self.pool.acquire() as conn:
            query = "SELECT * FROM security_findings WHERE 1=1"

            if dismissed_only:
                query += " AND dismissed = TRUE"
            elif not include_dismissed:
                query += " AND dismissed = FALSE"

            query += " ORDER BY created_at DESC"

            rows = await conn.fetch(query)

            findings = []
            for row in rows:
                timestamp = row['timestamp'].isoformat()

                finding = SecurityFindingResponse(
                    id=row['id'],
                    resource_type=row['resource_type'],
                    resource_name=row['resource_name'],
                    namespace=row['namespace'],
                    severity=row['severity'],
                    category=row['category'],
                    title=row['title'],
                    description=row['description'],
                    remediation=row['remediation'],
                    timestamp=timestamp,
                    dismissed=bool(row['dismissed'])
                )
                findings.append(finding)

            return findings

    async def dismiss_security_finding(self, finding_id: int):
        """Mark a security finding as dismissed"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE security_findings SET dismissed = TRUE WHERE id = $1",
                finding_id
            )

    async def restore_security_finding(self, finding_id: int):
        """Restore a dismissed security finding"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE security_findings SET dismissed = FALSE WHERE id = $1",
                finding_id
            )

    async def clear_security_findings(self):
        """Clear all security findings (for new scans)"""
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM security_findings WHERE dismissed = FALSE")

    async def delete_findings_by_resource(self, resource_type: str, namespace: str, resource_name: str) -> tuple[int, list]:
        """Delete all findings for a specific resource (when resource is deleted from cluster)

        Returns:
            tuple[int, list]: (count, deleted_findings) - count of deleted findings and their details
        """
        async with self.pool.acquire() as conn:
            # First get the findings that will be deleted (for broadcasting)
            rows = await conn.fetch(
                """SELECT resource_name, namespace, title FROM security_findings
                   WHERE resource_type = $1 AND namespace = $2 AND resource_name = $3""",
                resource_type, namespace, resource_name
            )
            deleted_findings = [
                {"resource_name": row['resource_name'], "namespace": row['namespace'], "title": row['title']}
                for row in rows
            ]

            # Now delete
            result = await conn.execute(
                """DELETE FROM security_findings
                   WHERE resource_type = $1 AND namespace = $2 AND resource_name = $3""",
                resource_type, namespace, resource_name
            )
            # Extract count from result string like "DELETE 5"
            count = int(result.split()[-1]) if result else 0
            return count, deleted_findings

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()

    # Excluded namespaces methods
    async def add_excluded_namespace(self, namespace: str) -> ExcludedNamespaceResponse:
        """Add a namespace to the exclusion list"""
        async with self.pool.acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """INSERT INTO excluded_namespaces (namespace)
                       VALUES ($1)
                       ON CONFLICT (namespace) DO NOTHING
                       RETURNING id, namespace, created_at""",
                    namespace
                )
                if result:
                    return ExcludedNamespaceResponse(
                        id=result['id'],
                        namespace=result['namespace'],
                        created_at=result['created_at'].isoformat()
                    )
                # If no result, namespace already exists - fetch it
                existing = await conn.fetchrow(
                    "SELECT id, namespace, created_at FROM excluded_namespaces WHERE namespace = $1",
                    namespace
                )
                return ExcludedNamespaceResponse(
                    id=existing['id'],
                    namespace=existing['namespace'],
                    created_at=existing['created_at'].isoformat()
                )
            except Exception as e:
                logger.error(f"Error adding excluded namespace: {e}")
                raise

    async def remove_excluded_namespace(self, namespace: str) -> bool:
        """Remove a namespace from the exclusion list"""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM excluded_namespaces WHERE namespace = $1",
                namespace
            )
            # Extract count from result string like "DELETE 1"
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_excluded_namespaces(self) -> List[ExcludedNamespaceResponse]:
        """Get all excluded namespaces"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, namespace, created_at FROM excluded_namespaces ORDER BY namespace"
            )
            return [
                ExcludedNamespaceResponse(
                    id=row['id'],
                    namespace=row['namespace'],
                    created_at=row['created_at'].isoformat()
                )
                for row in rows
            ]

    async def is_namespace_excluded(self, namespace: str) -> bool:
        """Check if a namespace is in the exclusion list"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT 1 FROM excluded_namespaces WHERE namespace = $1",
                namespace
            )
            return result is not None

    async def get_all_namespaces(self) -> List[str]:
        """Get all unique namespaces from security findings and pod failures"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT namespace FROM (
                    SELECT namespace FROM security_findings WHERE dismissed = FALSE
                    UNION
                    SELECT namespace FROM pod_failures WHERE dismissed = FALSE
                ) AS all_namespaces
                ORDER BY namespace
            """)
            return [row['namespace'] for row in rows]

    async def delete_findings_by_namespace(self, namespace: str) -> tuple[int, list]:
        """Delete all security findings for a namespace and return deleted findings"""
        async with self.pool.acquire() as conn:
            # First get the findings to return them for WebSocket broadcast
            rows = await conn.fetch(
                """SELECT id, resource_type, resource_name, namespace, severity, category,
                          title, description, remediation, timestamp
                   FROM security_findings WHERE namespace = $1 AND dismissed = FALSE""",
                namespace
            )
            deleted_findings = [
                {
                    'id': row['id'],
                    'resource_type': row['resource_type'],
                    'resource_name': row['resource_name'],
                    'namespace': row['namespace'],
                    'severity': row['severity'],
                    'category': row['category'],
                    'title': row['title'],
                    'description': row['description'],
                    'remediation': row['remediation'],
                    'timestamp': row['timestamp'].isoformat() if row['timestamp'] else None
                }
                for row in rows
            ]

            # Delete (or mark as dismissed) the findings
            result = await conn.execute(
                "DELETE FROM security_findings WHERE namespace = $1",
                namespace
            )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_findings

    async def delete_pod_failures_by_namespace(self, namespace: str) -> tuple[int, list]:
        """Delete all pod failures for a namespace and return deleted pods"""
        async with self.pool.acquire() as conn:
            # First get the pods to return them for WebSocket broadcast
            rows = await conn.fetch(
                """SELECT id, pod_name, namespace FROM pod_failures
                   WHERE namespace = $1 AND dismissed = FALSE""",
                namespace
            )
            deleted_pods = [
                {
                    'pod_name': row['pod_name'],
                    'namespace': row['namespace']
                }
                for row in rows
            ]

            # Delete the pod failures
            result = await conn.execute(
                "DELETE FROM pod_failures WHERE namespace = $1",
                namespace
            )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_pods