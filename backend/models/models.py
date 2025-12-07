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


class CVEFinding(BaseModel):
    """Model for Kubernetes CVE findings from the official feed"""
    cve_id: str  # e.g., "CVE-2024-12345"
    title: str
    description: str
    severity: str  # "critical", "high", "medium", "low"
    cvss_score: Optional[float] = None
    affected_versions: List[str] = []
    fixed_versions: List[str] = []
    components: List[str] = []  # e.g., ["kubelet", "kube-apiserver"]
    published_date: Optional[str] = None
    url: Optional[str] = None  # GitHub issue URL
    external_url: Optional[str] = None  # CVE.org URL
    cluster_version: str  # The cluster version this was checked against
    timestamp: str


class CVEFindingReport(CVEFinding):
    pass


class CVEFindingResponse(CVEFinding):
    id: Optional[int] = None
    dismissed: bool = False
    acknowledged: bool = False  # User has seen/acknowledged this CVE
