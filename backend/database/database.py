import os
import logging
from .database_base import DatabaseInterface

logger = logging.getLogger(__name__)


def get_database() -> DatabaseInterface:
    """
    Factory function to get the appropriate database implementation
    based on environment detection.
    
    Returns:
        - PostgreSQLDatabase if running in Kubernetes (POSTGRES_HOST env var exists)
        - SQLiteDatabase for local development (fallback)
    """
    
    # Check if we're in a Kubernetes environment with PostgreSQL
    if os.getenv("POSTGRES_HOST"):
        logger.info("Detected Kubernetes environment - using PostgreSQL database")
        try:
            from .database_postgresql import PostgreSQLDatabase
            return PostgreSQLDatabase()
        except ImportError as e:
            logger.error(f"PostgreSQL dependencies not available: {e}")
            logger.info("Falling back to SQLite database")
            from .database_sqlite import SQLiteDatabase
            return SQLiteDatabase()
    else:
        logger.info("Detected local development environment - using SQLite database")
        from .database_sqlite import SQLiteDatabase
        return SQLiteDatabase()


# For backward compatibility, create a Database class that wraps the factory function
class Database:
    def __init__(self):
        self._db = get_database()
    
    async def init_database(self):
        return await self._db.init_database()
    
    async def save_pod_failure(self, failure):
        return await self._db.save_pod_failure(failure)
    
    async def get_pod_failures(self, include_dismissed=False, dismissed_only=False):
        return await self._db.get_pod_failures(include_dismissed, dismissed_only)
    
    async def dismiss_pod_failure(self, failure_id):
        return await self._db.dismiss_pod_failure(failure_id)
    
    async def restore_pod_failure(self, failure_id):
        return await self._db.restore_pod_failure(failure_id)
    
    async def dismiss_deleted_pod(self, namespace, pod_name):
        return await self._db.dismiss_deleted_pod(namespace, pod_name)
    
    async def close(self):
        return await self._db.close()
