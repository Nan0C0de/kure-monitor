from fastapi import FastAPI
from fastapi.responses import Response
from contextlib import asynccontextmanager
import logging

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager
from services.notification_service import NotificationService
from api.routes import create_api_router
from api.middleware import configure_cors, configure_exception_handlers

logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""

    # Global instances
    db = Database()
    solution_engine = SolutionEngine(db=db)  # Pass db for LLM config loading
    websocket_manager = WebSocketManager()
    notification_service = NotificationService(db)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        await db.init_database()
        logger.info("Database initialized")
        # Initialize solution engine (loads LLM config from db or env)
        await solution_engine.initialize()
        logger.info("Solution engine initialized")
        yield
        # Shutdown
        await db.close()

    # Create FastAPI app
    app = FastAPI(title="Kure Backend", version="1.5.0", lifespan=lifespan)

    # Configure middleware and exception handlers
    configure_cors(app)
    configure_exception_handlers(app)

    # Health check endpoint (outside of API router for compatibility)
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy"}

    # Prometheus metrics endpoint
    @app.get("/metrics")
    async def prometheus_metrics():
        """Prometheus metrics endpoint"""
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    # Include routers
    api_router = create_api_router(db, solution_engine, websocket_manager, notification_service)
    app.include_router(api_router)
    app.include_router(websocket_manager.router)

    return app