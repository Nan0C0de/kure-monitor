import pytest
import pytest_asyncio
import asyncio
import os
from unittest.mock import AsyncMock, Mock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from database.database import Database
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager
from api.routes import create_api_router
from api.middleware import configure_cors
from api.auth import (
    require_user,
    require_write,
    require_admin,
    require_service_token,
    reset_auth_cache,
)


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

    reset_auth_cache()
    db = Database()
    await db.init_database()

    # Clean auth-related tables between tests so the setup flow can be re-exercised.
    try:
        pg_db = db._db  # unwrap Database -> PostgreSQLDatabase
        async with pg_db._acquire() as conn:
            await conn.execute("TRUNCATE invitations RESTART IDENTITY CASCADE")
            await conn.execute("TRUNCATE users RESTART IDENTITY CASCADE")
            await conn.execute(
                "DELETE FROM app_settings WHERE key IN ('service_token', 'session_secret')"
            )
    except Exception:
        # Tables may not exist on very first run; init_database would have created them.
        pass

    reset_auth_cache()

    yield db
    await db.close()


@pytest_asyncio.fixture
async def app(test_db):
    """Create test app with test database.

    For legacy test compatibility we override auth dependencies so most
    callers can hit endpoints without managing cookies/tokens. Auth-specific
    tests in test_auth.py build their own app (or explicitly use cookies).
    """
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set - skipping API tests")

    # Create mock solution engine that returns simple solution
    mock_solution_engine = Mock(spec=SolutionEngine)
    mock_solution_engine.get_solution = AsyncMock(return_value="Test solution")
    mock_solution_engine.llm_provider = None

    # Create real websocket manager
    websocket_manager = WebSocketManager()

    # Create FastAPI app
    test_app = FastAPI()
    configure_cors(test_app)
    test_app.state.db = test_db

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

    # Override auth dependencies so legacy API tests don't need to manage sessions.
    async def _fake_user():
        return {"id": 1, "username": "test-admin", "role": "admin"}

    async def _fake_service():
        return None

    test_app.dependency_overrides[require_user] = _fake_user
    test_app.dependency_overrides[require_write] = _fake_user
    test_app.dependency_overrides[require_admin] = _fake_user
    test_app.dependency_overrides[require_service_token] = _fake_service

    return test_app


@pytest_asyncio.fixture
async def client(app):
    """Create test client"""
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set - skipping API tests")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
