import asyncpg
import logging
import os
import json
from typing import List, Optional
from datetime import datetime, timezone
from .database_base import DatabaseInterface
from models.models import PodFailureResponse, SecurityFindingResponse, ExcludedNamespaceResponse, TrustedRegistryResponse, NotificationSettingResponse
from services.prometheus_metrics import DATABASE_QUERIES_TOTAL

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

    def _acquire(self):
        """Acquire a database connection and increment the query counter"""
        DATABASE_QUERIES_TOTAL.inc()
        return self.pool.acquire()

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
            async with self._acquire() as conn:
                # Create pod_failures table if it doesn't exist
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS pod_failures (
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
                        status VARCHAR(20) NOT NULL DEFAULT 'new',
                        resolved_at TIMESTAMPTZ,
                        resolution_note TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Migration: add status workflow columns if they don't exist (for existing deployments)
                status_col_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'pod_failures' AND column_name = 'status'
                    )
                """)
                if not status_col_exists:
                    await conn.execute("ALTER TABLE pod_failures ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'new'")
                    await conn.execute("ALTER TABLE pod_failures ADD COLUMN resolved_at TIMESTAMPTZ")
                    await conn.execute("ALTER TABLE pod_failures ADD COLUMN resolution_note TEXT")
                    await conn.execute("UPDATE pod_failures SET status = CASE WHEN dismissed = TRUE THEN 'ignored' ELSE 'new' END")
                    logger.info("Migrated pod_failures table: added status workflow columns")

                # Create indexes for better performance
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pod_failures_pod_namespace
                    ON pod_failures(pod_name, namespace)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pod_failures_status
                    ON pod_failures(status)
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
                        manifest TEXT DEFAULT '',
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

                # Migration: add manifest column if it doesn't exist (for existing deployments)
                manifest_col_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'security_findings' AND column_name = 'manifest'
                    )
                """)
                if not manifest_col_exists:
                    await conn.execute("ALTER TABLE security_findings ADD COLUMN manifest TEXT DEFAULT ''")
                    logger.info("Migrated security_findings table: added manifest column")

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

                # Create excluded_pods table for pod monitoring exclusions (by pod name only)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS excluded_pods (
                        id SERIAL PRIMARY KEY,
                        pod_name VARCHAR(255) NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_excluded_pods_pod_name
                    ON excluded_pods(pod_name)
                """)

                # Create excluded_rules table for security rule exclusions
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS excluded_rules (
                        id SERIAL PRIMARY KEY,
                        rule_title VARCHAR(500) NOT NULL,
                        namespace VARCHAR(255) NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(rule_title, namespace)
                    )
                """)

                # Migration: add namespace column if it doesn't exist (for existing deployments)
                # Must run BEFORE index creation since old table lacks the namespace column
                col_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'excluded_rules' AND column_name = 'namespace'
                    )
                """)
                if not col_exists:
                    await conn.execute("ALTER TABLE excluded_rules ADD COLUMN namespace VARCHAR(255) NOT NULL DEFAULT ''")
                    await conn.execute("ALTER TABLE excluded_rules DROP CONSTRAINT IF EXISTS excluded_rules_rule_title_key")
                    await conn.execute("ALTER TABLE excluded_rules ADD CONSTRAINT excluded_rules_rule_title_namespace_key UNIQUE (rule_title, namespace)")
                    logger.info("Migrated excluded_rules table: added namespace column")

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_excluded_rules_rule_title_namespace
                    ON excluded_rules(rule_title, namespace)
                """)

                # Create trusted_registries table for admin-managed trusted container registries
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS trusted_registries (
                        id SERIAL PRIMARY KEY,
                        registry VARCHAR(255) NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trusted_registries_registry
                    ON trusted_registries(registry)
                """)

                # Create notification_settings table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS notification_settings (
                        id SERIAL PRIMARY KEY,
                        provider VARCHAR(50) NOT NULL UNIQUE,
                        enabled BOOLEAN DEFAULT FALSE,
                        config JSONB NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_notification_settings_provider
                    ON notification_settings(provider)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_notification_settings_enabled
                    ON notification_settings(enabled)
                """)

                # Create llm_config table for storing LLM provider settings
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS llm_config (
                        id SERIAL PRIMARY KEY,
                        provider VARCHAR(50) NOT NULL,
                        api_key_encrypted VARCHAR(500) NOT NULL,
                        model VARCHAR(100),
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create app_settings table (key-value store for general settings)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key VARCHAR(255) PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

            logger.info("PostgreSQL database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")
            raise

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
            # Check if pod already exists and is active (new or investigating)
            existing = await conn.fetchrow("""
                SELECT id FROM pod_failures
                WHERE pod_name = $1 AND namespace = $2 AND status IN ('new', 'investigating')
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

    async def get_pod_failures(self, status_filter: list = None, include_dismissed: bool = False, dismissed_only: bool = False) -> List[PodFailureResponse]:
        """Get all pod failures from database (latest per pod)

        Args:
            status_filter: List of statuses to include (e.g. ['new', 'investigating']). Takes priority.
            include_dismissed: Legacy compat. If True, include all.
            dismissed_only: Legacy compat. If True, only ignored.
        """
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

    async def save_security_finding(self, finding: SecurityFindingResponse) -> tuple[int, bool]:
        """Save a security finding to database

        Returns:
            tuple[int, bool]: (finding_id, is_new) where is_new indicates if this is a new finding
        """
        async with self._acquire() as conn:
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
                        description = $4, remediation = $5, timestamp = $6,
                        manifest = $7
                    WHERE id = $8
                """,
                    finding.resource_type, finding.severity, finding.category,
                    finding.description, finding.remediation, timestamp,
                    finding.manifest, existing['id']
                )
                return existing['id'], False
            else:
                # Insert new record
                result = await conn.fetchrow("""
                    INSERT INTO security_findings (
                        resource_type, resource_name, namespace, severity, category,
                        title, description, remediation, timestamp, dismissed, manifest
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING id
                """,
                    finding.resource_type, finding.resource_name, finding.namespace,
                    finding.severity, finding.category, finding.title,
                    finding.description, finding.remediation, timestamp, finding.dismissed,
                    finding.manifest
                )
                return result['id'], True

    async def get_security_findings(self, include_dismissed: bool = False, dismissed_only: bool = False) -> List[SecurityFindingResponse]:
        """Get all security findings from database"""
        async with self._acquire() as conn:
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
                    dismissed=bool(row['dismissed']),
                    manifest=row.get('manifest', '')
                )
                findings.append(finding)

            return findings

    async def get_security_finding_by_id(self, finding_id: int) -> Optional[SecurityFindingResponse]:
        """Get a single security finding by ID"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM security_findings WHERE id = $1", finding_id
            )
            if not row:
                return None
            timestamp = row['timestamp'].isoformat()
            return SecurityFindingResponse(
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
                dismissed=bool(row['dismissed']),
                manifest=row.get('manifest', '')
            )

    async def dismiss_security_finding(self, finding_id: int):
        """Mark a security finding as dismissed"""
        async with self._acquire() as conn:
            await conn.execute(
                "UPDATE security_findings SET dismissed = TRUE WHERE id = $1",
                finding_id
            )

    async def restore_security_finding(self, finding_id: int):
        """Restore a dismissed security finding"""
        async with self._acquire() as conn:
            await conn.execute(
                "UPDATE security_findings SET dismissed = FALSE WHERE id = $1",
                finding_id
            )

    async def clear_security_findings(self):
        """Clear all security findings (for new scans)"""
        async with self._acquire() as conn:
            await conn.execute("DELETE FROM security_findings WHERE dismissed = FALSE")

    async def delete_findings_by_resource(self, resource_type: str, namespace: str, resource_name: str) -> tuple[int, list]:
        """Delete all findings for a specific resource (when resource is deleted from cluster)

        Returns:
            tuple[int, list]: (count, deleted_findings) - count of deleted findings and their details
        """
        async with self._acquire() as conn:
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
        async with self._acquire() as conn:
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
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM excluded_namespaces WHERE namespace = $1",
                namespace
            )
            # Extract count from result string like "DELETE 1"
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_excluded_namespaces(self) -> List[ExcludedNamespaceResponse]:
        """Get all excluded namespaces"""
        async with self._acquire() as conn:
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
        async with self._acquire() as conn:
            result = await conn.fetchrow(
                "SELECT 1 FROM excluded_namespaces WHERE namespace = $1",
                namespace
            )
            return result is not None

    async def get_all_namespaces(self) -> List[str]:
        """Get all unique namespaces from security findings and pod failures"""
        async with self._acquire() as conn:
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
        async with self._acquire() as conn:
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
        async with self._acquire() as conn:
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

    # Excluded pods methods (for pod monitoring exclusions - by pod name only)
    async def add_excluded_pod(self, pod_name: str) -> dict:
        """Add a pod to the monitoring exclusion list (by name only)"""
        async with self._acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """INSERT INTO excluded_pods (pod_name)
                       VALUES ($1)
                       ON CONFLICT (pod_name) DO NOTHING
                       RETURNING id, pod_name, created_at""",
                    pod_name
                )
                if result:
                    return {
                        'id': result['id'],
                        'pod_name': result['pod_name'],
                        'created_at': result['created_at'].isoformat()
                    }
                # If no result, pod already exists - fetch it
                existing = await conn.fetchrow(
                    "SELECT id, pod_name, created_at FROM excluded_pods WHERE pod_name = $1",
                    pod_name
                )
                return {
                    'id': existing['id'],
                    'pod_name': existing['pod_name'],
                    'created_at': existing['created_at'].isoformat()
                }
            except Exception as e:
                logger.error(f"Error adding excluded pod: {e}")
                raise

    async def remove_excluded_pod(self, pod_name: str) -> bool:
        """Remove a pod from the monitoring exclusion list"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM excluded_pods WHERE pod_name = $1",
                pod_name
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_excluded_pods(self) -> List[dict]:
        """Get all excluded pods"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, pod_name, created_at FROM excluded_pods ORDER BY pod_name"
            )
            return [
                {
                    'id': row['id'],
                    'pod_name': row['pod_name'],
                    'created_at': row['created_at'].isoformat()
                }
                for row in rows
            ]

    async def is_pod_excluded(self, pod_name: str) -> bool:
        """Check if a pod is in the monitoring exclusion list (by name only)"""
        async with self._acquire() as conn:
            result = await conn.fetchrow(
                "SELECT 1 FROM excluded_pods WHERE pod_name = $1",
                pod_name
            )
            return result is not None

    async def get_all_monitored_pods(self) -> List[dict]:
        """Get all unique pod names from pod failures (for suggestions), with namespace for display"""
        async with self._acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT pod_name, namespace FROM pod_failures
                WHERE dismissed = FALSE
                ORDER BY pod_name
            """)
            return [{'pod_name': row['pod_name'], 'namespace': row['namespace']} for row in rows]

    async def delete_pod_failure_by_pod(self, pod_name: str) -> tuple[int, list]:
        """Delete pod failures for a specific pod name (across all namespaces) and return deleted info"""
        async with self._acquire() as conn:
            # First get the pods to return them for WebSocket broadcast
            rows = await conn.fetch(
                """SELECT id, pod_name, namespace FROM pod_failures
                   WHERE pod_name = $1 AND dismissed = FALSE""",
                pod_name
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
                "DELETE FROM pod_failures WHERE pod_name = $1",
                pod_name
            )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_pods

    # Excluded rules methods (security rule exclusions)
    async def add_excluded_rule(self, rule_title: str, namespace: str = '') -> dict:
        """Add a rule to the security scan exclusion list (namespace='' for global)"""
        async with self._acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """INSERT INTO excluded_rules (rule_title, namespace)
                       VALUES ($1, $2)
                       ON CONFLICT (rule_title, namespace) DO NOTHING
                       RETURNING id, rule_title, namespace, created_at""",
                    rule_title, namespace
                )
                if result:
                    return {
                        'id': result['id'],
                        'rule_title': result['rule_title'],
                        'namespace': result['namespace'] if result['namespace'] else None,
                        'created_at': result['created_at'].isoformat()
                    }
                existing = await conn.fetchrow(
                    "SELECT id, rule_title, namespace, created_at FROM excluded_rules WHERE rule_title = $1 AND namespace = $2",
                    rule_title, namespace
                )
                return {
                    'id': existing['id'],
                    'rule_title': existing['rule_title'],
                    'namespace': existing['namespace'] if existing['namespace'] else None,
                    'created_at': existing['created_at'].isoformat()
                }
            except Exception as e:
                logger.error(f"Error adding excluded rule: {e}")
                raise

    async def remove_excluded_rule(self, rule_title: str, namespace: str = '') -> bool:
        """Remove a rule from the exclusion list (namespace='' for global)"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM excluded_rules WHERE rule_title = $1 AND namespace = $2",
                rule_title, namespace
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_excluded_rules(self) -> list:
        """Get all excluded rules"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, rule_title, namespace, created_at FROM excluded_rules ORDER BY rule_title, namespace"
            )
            return [
                {
                    'id': row['id'],
                    'rule_title': row['rule_title'],
                    'namespace': row['namespace'] if row['namespace'] else None,
                    'created_at': row['created_at'].isoformat()
                }
                for row in rows
            ]

    async def is_rule_excluded(self, rule_title: str, namespace: str = '') -> bool:
        """Check if a rule is excluded (globally or for a specific namespace).
        Supports base-name matching: excluding 'Privilege escalation allowed' also
        matches 'Privilege escalation allowed: container-name'."""
        async with self._acquire() as conn:
            result = await conn.fetchrow(
                """SELECT 1 FROM excluded_rules
                   WHERE (namespace = '' OR namespace = $2)
                   AND (rule_title = $1 OR $1 LIKE rule_title || ': %')""",
                rule_title, namespace
            )
            return result is not None

    async def get_all_rule_titles(self, namespace: str = None) -> list:
        """Get all unique rule titles from security findings (for suggestions).

        Also includes base rule names (without container suffix) for cluster-wide exclusion.
        E.g. if findings exist for 'Privilege escalation allowed: container1' and
        'Privilege escalation allowed: container2', the base name 'Privilege escalation allowed'
        is also returned so users can exclude the entire rule family.

        If namespace is provided, only return titles with findings in that namespace.
        """
        async with self._acquire() as conn:
            if namespace:
                rows = await conn.fetch("""
                    SELECT title FROM (
                        SELECT DISTINCT title FROM security_findings
                        WHERE dismissed = FALSE AND namespace = $1
                        UNION
                        SELECT DISTINCT split_part(title, ': ', 1) FROM security_findings
                        WHERE dismissed = FALSE AND namespace = $1 AND title LIKE '%: %'
                    ) sub
                    ORDER BY title
                """, namespace)
            else:
                rows = await conn.fetch("""
                    SELECT title FROM (
                        SELECT DISTINCT title FROM security_findings
                        WHERE dismissed = FALSE
                        UNION
                        SELECT DISTINCT split_part(title, ': ', 1) FROM security_findings
                        WHERE dismissed = FALSE AND title LIKE '%: %'
                    ) sub
                    ORDER BY title
                """)
            return [row['title'] for row in rows]

    async def delete_findings_by_rule_title(self, rule_title: str, namespace: str = None) -> tuple:
        """Delete security findings for a rule title. If namespace given, only in that namespace.
        Supports base-name matching: 'Privilege escalation allowed' deletes all
        findings with titles like 'Privilege escalation allowed: container-name'."""
        async with self._acquire() as conn:
            # Match exact title OR base-name prefix (e.g. "Rule name" matches "Rule name: container")
            title_condition = "(title = $1 OR title LIKE $1 || ': %')"
            if namespace:
                rows = await conn.fetch(
                    f"""SELECT id, resource_type, resource_name, namespace, severity, category,
                              title, description, remediation, timestamp
                       FROM security_findings WHERE {title_condition} AND namespace = $2 AND dismissed = FALSE""",
                    rule_title, namespace
                )
            else:
                rows = await conn.fetch(
                    f"""SELECT id, resource_type, resource_name, namespace, severity, category,
                              title, description, remediation, timestamp
                       FROM security_findings WHERE {title_condition} AND dismissed = FALSE""",
                    rule_title
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

            if namespace:
                result = await conn.execute(
                    f"DELETE FROM security_findings WHERE {title_condition} AND namespace = $2",
                    rule_title, namespace
                )
            else:
                result = await conn.execute(
                    f"DELETE FROM security_findings WHERE {title_condition}",
                    rule_title
                )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_findings

    # Trusted registries methods (admin-managed trusted container registries)
    async def add_trusted_registry(self, registry: str) -> TrustedRegistryResponse:
        """Add a trusted container registry"""
        async with self._acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """INSERT INTO trusted_registries (registry)
                       VALUES ($1)
                       ON CONFLICT (registry) DO NOTHING
                       RETURNING id, registry, created_at""",
                    registry
                )
                if result:
                    return TrustedRegistryResponse(
                        id=result['id'],
                        registry=result['registry'],
                        created_at=result['created_at'].isoformat()
                    )
                existing = await conn.fetchrow(
                    "SELECT id, registry, created_at FROM trusted_registries WHERE registry = $1",
                    registry
                )
                return TrustedRegistryResponse(
                    id=existing['id'],
                    registry=existing['registry'],
                    created_at=existing['created_at'].isoformat()
                )
            except Exception as e:
                logger.error(f"Error adding trusted registry: {e}")
                raise

    async def remove_trusted_registry(self, registry: str) -> bool:
        """Remove a trusted container registry"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM trusted_registries WHERE registry = $1",
                registry
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_trusted_registries(self) -> list:
        """Get all admin-added trusted registries"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, registry, created_at FROM trusted_registries ORDER BY registry"
            )
            return [
                TrustedRegistryResponse(
                    id=row['id'],
                    registry=row['registry'],
                    created_at=row['created_at'].isoformat()
                )
                for row in rows
            ]

    # Notification settings methods
    async def save_notification_setting(self, setting) -> NotificationSettingResponse:
        """Create or update notification setting for a provider"""
        async with self._acquire() as conn:
            config_json = json.dumps(setting.config)

            # Use upsert (INSERT ... ON CONFLICT ... UPDATE)
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

    # LLM Configuration methods
    async def save_llm_config(self, provider: str, api_key: str, model: Optional[str] = None) -> dict:
        """Save or update LLM configuration (only one config allowed)"""
        async with self._acquire() as conn:
            # Delete any existing config first (only one LLM config allowed)
            await conn.execute("DELETE FROM llm_config")

            # Insert new config
            result = await conn.fetchrow("""
                INSERT INTO llm_config (provider, api_key_encrypted, model)
                VALUES ($1, $2, $3)
                RETURNING id, provider, model, created_at, updated_at
            """, provider, api_key, model)

            return {
                'id': result['id'],
                'provider': result['provider'],
                'model': result['model'],
                'configured': True,
                'created_at': result['created_at'].isoformat() if result['created_at'] else None,
                'updated_at': result['updated_at'].isoformat() if result['updated_at'] else None
            }

    async def get_llm_config(self) -> Optional[dict]:
        """Get the LLM configuration (returns None if not configured)"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, provider, api_key_encrypted, model, created_at, updated_at FROM llm_config LIMIT 1"
            )
            if not row:
                return None

            return {
                'id': row['id'],
                'provider': row['provider'],
                'api_key': row['api_key_encrypted'],  # Will be used internally
                'model': row['model'],
                'configured': True,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
            }

    async def delete_llm_config(self) -> bool:
        """Delete the LLM configuration"""
        async with self._acquire() as conn:
            result = await conn.execute("DELETE FROM llm_config")
            count = int(result.split()[-1]) if result else 0
            return count > 0

    # App settings methods
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

    # Pod record deletion methods
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
        """Delete resolved pods older than the retention period (in minutes). Returns count of deleted records."""
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
        """Delete ignored pods older than the retention period (in minutes). Returns count of deleted records."""
        async with self._acquire() as conn:
            result = await conn.execute(
                """DELETE FROM pod_failures
                   WHERE status = 'ignored'
                   AND created_at < NOW() - INTERVAL '1 minute' * $1""",
                retention_minutes
            )
            count = int(result.split()[-1]) if result else 0
            return count