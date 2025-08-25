import os
import logging
from .database_base import DatabaseInterface

logger = logging.getLogger(__name__)


def get_database() -> DatabaseInterface:
    """
    Factory function to get PostgreSQL database implementation.
    
    Returns:
        - PostgreSQLDatabase (only supported database)
    """
    
    logger.info("Using PostgreSQL database")
    try:
        from .database_postgresql import PostgreSQLDatabase
        return PostgreSQLDatabase()
    except ImportError as e:
        logger.error(f"PostgreSQL dependencies not available: {e}")
        raise ImportError("PostgreSQL is required but dependencies are not available")


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
