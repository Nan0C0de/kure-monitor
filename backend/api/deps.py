from dataclasses import dataclass
from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager


@dataclass
class RouterDeps:
    """Shared dependencies injected into all route modules."""
    db: Database
    solution_engine: SolutionEngine
    websocket_manager: WebSocketManager
    notification_service: object = None
    policy_engine: object = None
