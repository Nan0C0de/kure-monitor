import asyncpg
import logging
import os
import json
from typing import List
from datetime import datetime, timezone
from .database_base import DatabaseInterface
from models.models import PodFailureResponse, SecurityFindingResponse, CVEFindingResponse

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

                # Create cve_findings table for Kubernetes CVE tracking
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS cve_findings (
                        id SERIAL PRIMARY KEY,
                        cve_id VARCHAR(50) NOT NULL UNIQUE,
                        title VARCHAR(500) NOT NULL,
                        description TEXT NOT NULL,
                        severity VARCHAR(50) NOT NULL,
                        cvss_score DECIMAL(3,1),
                        affected_versions JSONB,
                        fixed_versions JSONB,
                        components JSONB,
                        published_date TIMESTAMPTZ,
                        url TEXT,
                        external_url TEXT,
                        cluster_version VARCHAR(50),
                        timestamp TIMESTAMPTZ NOT NULL,
                        dismissed BOOLEAN DEFAULT FALSE,
                        acknowledged BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create indexes for CVE findings
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cve_findings_cve_id
                    ON cve_findings(cve_id)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cve_findings_severity
                    ON cve_findings(severity)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cve_findings_dismissed
                    ON cve_findings(dismissed)
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

    # ==================== CVE Finding Methods ====================

    async def save_cve_finding(self, finding: CVEFindingResponse) -> tuple[int, bool]:
        """Save a CVE finding to database

        Returns:
            tuple[int, bool]: (finding_id, is_new) where is_new indicates if this is a new finding
        """
        async with self.pool.acquire() as conn:
            timestamp = self._normalize_timestamp(finding.timestamp)
            published_date = None
            if finding.published_date:
                try:
                    published_date = self._normalize_timestamp(finding.published_date)
                except Exception:
                    pass

            # Check if CVE already exists
            existing = await conn.fetchrow("""
                SELECT id FROM cve_findings WHERE cve_id = $1
            """, finding.cve_id)

            # Convert lists to JSON for JSONB columns
            affected_versions = json.dumps(finding.affected_versions)
            fixed_versions = json.dumps(finding.fixed_versions)
            components = json.dumps(finding.components)

            if existing:
                # Update existing record but preserve dismissed/acknowledged status
                await conn.execute("""
                    UPDATE cve_findings SET
                        title = $1, description = $2, severity = $3, cvss_score = $4,
                        affected_versions = $5, fixed_versions = $6, components = $7,
                        published_date = $8, url = $9, external_url = $10,
                        cluster_version = $11, timestamp = $12
                    WHERE id = $13
                """,
                    finding.title, finding.description, finding.severity, finding.cvss_score,
                    affected_versions, fixed_versions, components,
                    published_date, finding.url, finding.external_url,
                    finding.cluster_version, timestamp,
                    existing['id']
                )
                return existing['id'], False
            else:
                # Insert new record
                result = await conn.fetchrow("""
                    INSERT INTO cve_findings (
                        cve_id, title, description, severity, cvss_score,
                        affected_versions, fixed_versions, components,
                        published_date, url, external_url, cluster_version,
                        timestamp, dismissed, acknowledged
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    RETURNING id
                """,
                    finding.cve_id, finding.title, finding.description, finding.severity,
                    finding.cvss_score, affected_versions, fixed_versions, components,
                    published_date, finding.url, finding.external_url, finding.cluster_version,
                    timestamp, finding.dismissed, finding.acknowledged
                )
                return result['id'], True

    async def get_cve_findings(self, include_dismissed: bool = False, dismissed_only: bool = False) -> List[CVEFindingResponse]:
        """Get all CVE findings from database"""
        async with self.pool.acquire() as conn:
            query = "SELECT * FROM cve_findings WHERE 1=1"

            if dismissed_only:
                query += " AND dismissed = TRUE"
            elif not include_dismissed:
                query += " AND dismissed = FALSE"

            query += " ORDER BY severity DESC, created_at DESC"

            rows = await conn.fetch(query)

            findings = []
            for row in rows:
                timestamp = row['timestamp'].isoformat() if row['timestamp'] else None
                published_date = row['published_date'].isoformat() if row['published_date'] else None

                finding = CVEFindingResponse(
                    id=row['id'],
                    cve_id=row['cve_id'],
                    title=row['title'],
                    description=row['description'],
                    severity=row['severity'],
                    cvss_score=float(row['cvss_score']) if row['cvss_score'] else None,
                    affected_versions=json.loads(row['affected_versions']) if row['affected_versions'] else [],
                    fixed_versions=json.loads(row['fixed_versions']) if row['fixed_versions'] else [],
                    components=json.loads(row['components']) if row['components'] else [],
                    published_date=published_date,
                    url=row['url'],
                    external_url=row['external_url'],
                    cluster_version=row['cluster_version'] or "unknown",
                    timestamp=timestamp,
                    dismissed=bool(row['dismissed']),
                    acknowledged=bool(row['acknowledged'])
                )
                findings.append(finding)

            return findings

    async def dismiss_cve_finding(self, finding_id: int):
        """Mark a CVE finding as dismissed"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE cve_findings SET dismissed = TRUE WHERE id = $1",
                finding_id
            )

    async def restore_cve_finding(self, finding_id: int):
        """Restore a dismissed CVE finding"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE cve_findings SET dismissed = FALSE WHERE id = $1",
                finding_id
            )

    async def acknowledge_cve_finding(self, finding_id: int):
        """Mark a CVE finding as acknowledged"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE cve_findings SET acknowledged = TRUE WHERE id = $1",
                finding_id
            )

    async def clear_cve_findings(self):
        """Clear all non-dismissed CVE findings (for new scans)"""
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM cve_findings WHERE dismissed = FALSE")

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()