from pydantic import BaseModel
from typing import List, Optional, Dict, Any

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
    status: str = "new"  # new, investigating, resolved, ignored
    resolved_at: Optional[str] = None
    resolution_note: Optional[str] = None


class PodStatusUpdate(BaseModel):
    status: str  # investigating, resolved, ignored, new
    resolution_note: Optional[str] = None

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
    manifest: str = ""

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

class ExcludedRule(BaseModel):
    rule_title: str
    namespace: Optional[str] = None  # None = global, "ns-name" = per-namespace
    created_at: Optional[str] = None

class ExcludedRuleResponse(ExcludedRule):
    id: Optional[int] = None

class TrustedRegistry(BaseModel):
    registry: str
    created_at: Optional[str] = None

class TrustedRegistryResponse(TrustedRegistry):
    id: Optional[int] = None


# Notification models
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
    cpu_usage: Optional[int] = None  # millicores (raw value)
    cpu_usage_formatted: Optional[str] = None  # e.g., "150m" or "1.5 cores"
    memory_usage: Optional[int] = None  # bytes (raw value)
    memory_usage_formatted: Optional[str] = None  # e.g., "256Mi"


class PodMetricsPoint(BaseModel):
    """Single point in pod metrics history"""
    timestamp: str
    cpu_millicores: Optional[int] = None
    memory_bytes: Optional[int] = None
    cpu_formatted: Optional[str] = None
    memory_formatted: Optional[str] = None


class PodMetricsHistory(BaseModel):
    """Pod metrics history response"""
    name: str
    namespace: str
    current_cpu: Optional[str] = None
    current_memory: Optional[str] = None
    history: List[PodMetricsPoint] = []


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


# LLM Configuration models
class LLMConfigCreate(BaseModel):
    provider: str
    api_key: str
    model: Optional[str] = None
    base_url: Optional[str] = None


class LLMConfigResponse(BaseModel):
    id: Optional[int] = None
    provider: str
    model: Optional[str] = None
    configured: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LLMConfigStatus(BaseModel):
    configured: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    source: Optional[str] = None  # "database"
