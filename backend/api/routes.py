from fastapi import APIRouter, Depends
import logging

from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager
from .auth import require_read
from .deps import RouterDeps
from .routes_auth import create_auth_router
from .routes_users import create_users_router
from .routes_pods import create_pod_router, create_pod_ingest_router
from .routes_security import create_security_router, create_security_ingest_router
from .routes_admin import create_admin_router
from .routes_metrics import create_metrics_ingest_router
from .routes_logs import create_logs_router
from .routes_llm import create_llm_router
from .routes_mirror import create_mirror_router
from .routes_diagram import create_diagram_router

logger = logging.getLogger(__name__)


def create_api_router(db: Database, solution_engine: SolutionEngine, websocket_manager: WebSocketManager, notification_service=None, mirror_service=None) -> APIRouter:
    """Create and configure the API router.

    The router is structured as follows:
      - Public auth endpoints (setup, login, logout, invitation lookup/accept).
      - Service-token-protected ingest endpoints (agent/scanner traffic).
      - Authenticated user endpoints (require valid session cookie).
      - Admin endpoints (require admin role).
    """
    router = APIRouter(prefix="/api")
    deps = RouterDeps(db, solution_engine, websocket_manager, notification_service, mirror_service)

    # Public (no auth) auth endpoints
    router.include_router(create_auth_router(deps))

    # Ingest endpoints (agent/scanner) — require service token, NOT user session.
    router.include_router(create_pod_ingest_router(deps))
    router.include_router(create_security_ingest_router(deps))
    router.include_router(create_metrics_ingest_router(deps))

    # Authenticated user endpoints (require any valid session)
    authed = APIRouter(dependencies=[Depends(require_read)])

    @authed.get("/config")
    async def get_config():
        """Get application configuration status"""
        return {
            "ai_enabled": solution_engine.llm_provider is not None,
            "ai_provider": solution_engine.llm_provider.provider_name if solution_engine.llm_provider else None
        }

    authed.include_router(create_pod_router(deps))
    authed.include_router(create_security_router(deps))
    authed.include_router(create_admin_router(deps))
    authed.include_router(create_logs_router(deps))
    authed.include_router(create_llm_router(deps))
    authed.include_router(create_users_router(deps))
    authed.include_router(create_diagram_router(deps))

    if mirror_service:
        authed.include_router(create_mirror_router(deps, mirror_service))

    router.include_router(authed)

    return router
