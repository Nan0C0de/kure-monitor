#!/usr/bin/env python3
"""
Migration script to add CVE findings table to existing PostgreSQL database.
Run this if upgrading from a version without CVE support.

Usage:
    DATABASE_URL=postgresql://user:pass@host:5432/db python migrate_cve_table.py
"""

import asyncio
import asyncpg
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable is required")
        return False

    try:
        conn = await asyncpg.connect(database_url)
        logger.info("Connected to database")

        # Check if cve_findings table already exists
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'cve_findings'
            )
        """)

        if exists:
            logger.info("cve_findings table already exists, skipping creation")
        else:
            logger.info("Creating cve_findings table...")

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

            logger.info("Creating indexes...")

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

            logger.info("cve_findings table created successfully")

        await conn.close()
        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(migrate())
    exit(0 if success else 1)
