from fastapi import FastAPI
from fastapi.responses import Response
from contextlib import asynccontextmanager
import asyncio
import logging

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager
from services.notification_service import NotificationService
from api.routes import create_api_router
from api.middleware import configure_cors, configure_exception_handlers

logger = logging.getLogger(__name__)


async def history_cleanup_task(db: Database):
    """Background task that periodically cleans up old resolved and ignored pods based on retention settings"""
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute

            # Cleanup resolved pods
            value = await db.get_app_setting("history_retention_minutes")
            retention_minutes = int(value) if value else 0
            if retention_minutes > 0:
                count = await db.cleanup_old_resolved_pods(retention_minutes)
                if count > 0:
                    logger.info(f"History cleanup: deleted {count} resolved pods older than {retention_minutes}m")

            # Cleanup ignored pods
            ignored_value = await db.get_app_setting("ignored_retention_minutes")
            ignored_minutes = int(ignored_value) if ignored_value else 0
            if ignored_minutes > 0:
                count = await db.cleanup_old_ignored_pods(ignored_minutes)
                if count > 0:
                    logger.info(f"Ignored cleanup: deleted {count} ignored pods older than {ignored_minutes}m")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in history cleanup task: {e}")


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

        # Start background cleanup task
        cleanup_task = asyncio.create_task(history_cleanup_task(db))
        logger.info("History cleanup background task started")

        yield

        # Shutdown
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await db.close()

    # Create FastAPI app
    app = FastAPI(title="Kure Backend", version="1.6.0", lifespan=lifespan)

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