from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

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
    pod_name: str
    created_at: Optional[str] = None

class ExcludedPodResponse(ExcludedPod):
    id: Optional[int] = None


# Notification models
class NotificationProvider(str, Enum):
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"


class EmailConfig(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    from_email: str
    to_emails: List[str]
    use_tls: bool = True


class SlackConfig(BaseModel):
    webhook_url: str
    channel: Optional[str] = None


class TeamsConfig(BaseModel):
    webhook_url: str


class NotificationSettingCreate(BaseModel):
    provider: str
    enabled: bool = False
    config: Dict[str, Any]


class NotificationSettingResponse(BaseModel):
    id: Optional[int] = None
    provider: str
    enabled: bool = False
    config: Dict[str, Any]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# Cluster Metrics models
class NodeMetrics(BaseModel):
    name: str
    cpu_capacity: str
    cpu_allocatable: str
    cpu_usage: Optional[str] = None
    memory_capacity: str
    memory_allocatable: str
    memory_usage: Optional[str] = None
    storage_capacity: Optional[str] = None
    storage_used: Optional[str] = None
    conditions: List[Dict[str, Any]] = []
    pods_count: Optional[int] = None


class PodInfo(BaseModel):
    name: str
    namespace: str
    node: str
    status: str
    ready: bool
    restarts: int


class ClusterMetrics(BaseModel):
    node_count: int
    nodes: List[NodeMetrics]
    total_cpu_capacity: str
    total_cpu_allocatable: str
    total_cpu_usage: Optional[str] = None
    cpu_usage_percent: Optional[float] = None
    total_memory_capacity: str
    total_memory_allocatable: str
    total_memory_usage: Optional[str] = None
    memory_usage_percent: Optional[float] = None
    total_storage_capacity: Optional[str] = None
    total_storage_used: Optional[str] = None
    storage_usage_percent: Optional[float] = None
    total_pods: Optional[int] = None
    pods: List[PodInfo] = []
    metrics_available: bool = False
    timestamp: str
