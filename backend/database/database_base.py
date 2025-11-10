from abc import ABC, abstractmethod
from typing import List
from models.models import PodFailureResponse, SecurityFindingResponse


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
    async def save_security_finding(self, finding: SecurityFindingResponse) -> int:
        """Save a security finding to database"""
        pass

    @abstractmethod
    async def get_security_findings(self, include_dismissed: bool = False, dismissed_only: bool = False) -> List[SecurityFindingResponse]:
        """Get security findings from database"""
        pass

    @abstractmethod
    async def dismiss_security_finding(self, finding_id: int):
        """Mark a security finding as dismissed"""
        pass

    @abstractmethod
    async def restore_security_finding(self, finding_id: int):
        """Restore a dismissed security finding"""
        pass

    @abstractmethod
    async def clear_security_findings(self):
        """Clear all security findings (for new scans)"""
        pass

    @abstractmethod
    async def close(self):
        """Close database connection"""
        pass