from fastapi import APIRouter, Depends
import logging

from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager
from .auth import require_auth, create_auth_router
from .deps import RouterDeps
from .routes_pods import create_pod_router
from .routes_security import create_security_router
from .routes_admin import create_admin_router
from .routes_metrics import create_metrics_router
from .routes_logs import create_logs_router
from .routes_llm import create_llm_router

logger = logging.getLogger(__name__)


def create_api_router(db: Database, solution_engine: SolutionEngine, websocket_manager: WebSocketManager, notification_service=None) -> APIRouter:
    """Create and configure the API router by assembling domain-specific sub-routers."""
    router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
    deps = RouterDeps(db, solution_engine, websocket_manager, notification_service)

    @router.get("/config")
    async def get_config():
        """Get application configuration status"""
        return {
            "ai_enabled": solution_engine.llm_provider is not None,
            "ai_provider": solution_engine.llm_provider.provider_name if solution_engine.llm_provider else None
        }

    # Auth routes (exempted in require_auth via path matching)
    router.include_router(create_auth_router())

    router.include_router(create_pod_router(deps))
    router.include_router(create_security_router(deps))
    router.include_router(create_admin_router(deps))
    router.include_router(create_metrics_router(deps))
    router.include_router(create_logs_router(deps))
    router.include_router(create_llm_router(deps))

    return router
