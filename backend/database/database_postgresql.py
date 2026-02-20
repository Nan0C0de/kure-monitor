import asyncpg
import logging
import os
from datetime import datetime, timezone
from .database_base import DatabaseInterface
from .mixins import (
    PodFailureMixin,
    SecurityFindingMixin,
    ExclusionMixin,
    NotificationMixin,
    LLMConfigMixin,
)
from services.prometheus_metrics import DATABASE_QUERIES_TOTAL

logger = logging.getLogger(__name__)


class PostgreSQLDatabase(
    PodFailureMixin,
    SecurityFindingMixin,
    ExclusionMixin,
    NotificationMixin,
    LLMConfigMixin,
    DatabaseInterface,
):
    def __init__(self):
        self.pool = None
        self.connection_string = self._get_connection_string()

    def _normalize_timestamp(self, timestamp) -> datetime:
        """Convert timestamp to timezone-aware datetime object"""
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                return timestamp.replace(tzinfo=timezone.utc)
            return timestamp
        elif isinstance(timestamp, str):
            try:
                timestamp_str = timestamp.replace('Z', '+00:00')
                dt = datetime.fromisoformat(timestamp_str)
                return dt
            except ValueError:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    logger.warning(f"Could not parse timestamp '{timestamp}', using current time")
                    return datetime.now(timezone.utc)
        else:
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

            async with self._acquire() as conn:
                # Create pod_failures table
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

                # Migration: add status workflow columns if they don't exist
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

                # Migration: add manifest column if it doesn't exist
                manifest_col_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'security_findings' AND column_name = 'manifest'
                    )
                """)
                if not manifest_col_exists:
                    await conn.execute("ALTER TABLE security_findings ADD COLUMN manifest TEXT DEFAULT ''")
                    logger.info("Migrated security_findings table: added manifest column")

                # Create excluded_namespaces table
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

                # Create excluded_pods table
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

                # Create excluded_rules table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS excluded_rules (
                        id SERIAL PRIMARY KEY,
                        rule_title VARCHAR(500) NOT NULL,
                        namespace VARCHAR(255) NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(rule_title, namespace)
                    )
                """)

                # Migration: add namespace column if it doesn't exist
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

                # Create trusted_registries table
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

                # Create llm_config table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS llm_config (
                        id SERIAL PRIMARY KEY,
                        provider VARCHAR(50) NOT NULL,
                        api_key_encrypted VARCHAR(1000) NOT NULL,
                        model VARCHAR(100),
                        base_url VARCHAR(500),
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Migration: add base_url column if it doesn't exist
                base_url_col_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'llm_config' AND column_name = 'base_url'
                    )
                """)
                if not base_url_col_exists:
                    await conn.execute("ALTER TABLE llm_config ADD COLUMN base_url VARCHAR(500)")
                    logger.info("Migrated llm_config table: added base_url column")

                # Create app_settings table
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

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
