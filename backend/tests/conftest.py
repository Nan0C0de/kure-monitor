import pytest
import asyncio
import aiosqlite
from httpx import AsyncClient
from core.app import create_app
from database.database import Database


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for session scope"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db():
    """Create test database"""
    db = Database()
    db.database_url = ":memory:"
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def app(test_db):
    """Create test app with test database"""
    test_app = create_app()
    test_app.state.db = test_db
    return test_app


@pytest.fixture
async def client(app):
    """Create test client"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac