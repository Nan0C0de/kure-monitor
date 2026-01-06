from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class ContainerStatus(BaseModel):
    name: str
    ready: bool
    restart_count: int
    image: str
    state: str
    reason: Optional[str] = None
    message: Optional[str] = None
    exit_code: Optional[int] = None

class PodEvent(BaseModel):
    type: str
    reason: str
    message: str
    timestamp: Optional[str] = None

class PodFailureCreate(BaseModel):
    pod_name: str
    namespace: str
    node_name: Optional[str] = None
    phase: str
    creation_timestamp: str
    failure_reason: str
    failure_message: Optional[str] = None
    container_statuses: List[ContainerStatus] = []
    events: List[PodEvent] = []
    logs: str = ""
    manifest: str = ""

class PodFailureReport(PodFailureCreate):
    pass

class PodFailureResponse(PodFailureReport):
    id: Optional[int] = None
    solution: str
    timestamp: str
    dismissed: bool = False

class SecurityFinding(BaseModel):
    resource_type: str  # e.g., "Pod", "Deployment", "Service"
    resource_name: str
    namespace: str
    severity: str  # "critical", "high", "medium", "low"
    category: str  # e.g., "Security", "Compliance", "Best Practice"
    title: str
    description: str
    remediation: str
    timestamp: str

class SecurityFindingReport(SecurityFinding):
    pass

class SecurityFindingResponse(SecurityFinding):
    id: Optional[int] = None
    dismissed: bool = False


# Admin models
class ExcludedNamespace(BaseModel):
    namespace: str
    created_at: Optional[str] = None

class ExcludedNamespaceResponse(ExcludedNamespace):
    id: Optional[int] = None

class ExcludedPod(BaseModel):
    namespace: str
    pod_name: str
    created_at: Optional[str] = None

class ExcludedPodResponse(ExcludedPod):
    id: Optional[int] = None
