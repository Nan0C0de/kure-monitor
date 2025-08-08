from abc import ABC, abstractmethod
from typing import List
from models import PodFailureResponse


class DatabaseInterface(ABC):
    """Abstract base class for database implementations"""
    
    @abstractmethod
    async def init_database(self):
        """Initialize the database"""
        pass
    
    @abstractmethod
    async def save_pod_failure(self, failure: PodFailureResponse) -> int:
        """Save a pod failure to database"""
        pass
    
    @abstractmethod
    async def get_pod_failures(self, include_dismissed: bool = False, dismissed_only: bool = False) -> List[PodFailureResponse]:
        """Get pod failures from database"""
        pass
    
    @abstractmethod
    async def dismiss_pod_failure(self, failure_id: int):
        """Mark a pod failure as dismissed"""
        pass
    
    @abstractmethod
    async def restore_pod_failure(self, failure_id: int):
        """Restore a dismissed pod failure"""
        pass
    
    @abstractmethod
    async def dismiss_deleted_pod(self, namespace: str, pod_name: str):
        """Mark all entries for a deleted pod as dismissed"""
        pass
    
    @abstractmethod
    async def close(self):
        """Close database connection"""
        pass