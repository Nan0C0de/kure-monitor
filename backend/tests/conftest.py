import pytest
import pytest_asyncio
import asyncio
import os
from unittest.mock import AsyncMock, Mock
from httpx import AsyncClient
from fastapi import FastAPI

from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager
from api.routes import create_api_router
from api.middleware import configure_cors


# Check if database is available
DATABASE_AVAILABLE = bool(os.getenv('DATABASE_URL'))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for session scope"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db():
    """Create test database - PostgreSQL only"""
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set - skipping database tests")

    from database.database import Database
    db = Database()
    await db.init_database()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def app(test_db):
    """Create test app with test database"""
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set - skipping API tests")

    # Create mock solution engine that returns simple solution
    mock_solution_engine = Mock(spec=SolutionEngine)
    mock_solution_engine.get_solution = AsyncMock(return_value="Test solution")

    # Create real websocket manager
    websocket_manager = WebSocketManager()

    # Create FastAPI app
    test_app = FastAPI()
    configure_cors(test_app)

    # Health check endpoint
    @test_app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    # Create API router with test database and mock solution engine
    api_router = create_api_router(
        db=test_db,
        solution_engine=mock_solution_engine,
        websocket_manager=websocket_manager,
        notification_service=None
    )
    test_app.include_router(api_router)

    return test_app


@pytest_asyncio.fixture
async def client(app):
    """Create test client"""
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set - skipping API tests")

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
