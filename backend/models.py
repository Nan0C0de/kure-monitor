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

class PodFailureReport(BaseModel):
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

class PodFailureResponse(PodFailureReport):
    id: Optional[int] = None
    solution: str
    timestamp: str
    dismissed: bool = False
