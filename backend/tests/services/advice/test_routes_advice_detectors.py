"""Route tests for ``GET /advice/detectors`` and ``PUT /advice/detectors/{id}``."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware import configure_cors
from api.routes import create_api_router
from services.advice.detector_settings import DetectorSettingsService
from services.advice.detectors import ALL_DETECTORS
from services.advice.hubble import StubHubbleClient
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager

DATABASE_AVAILABLE = bool(os.getenv("DATABASE_URL"))


class _FakeAdviceEngine:
    """Stand-in engine exposing ``hubble`` and ``detector_settings``."""

    def __init__(self, db) -> None:
        self.hubble = StubHubbleClient()
        self.detector_settings = DetectorSettingsService(db)

    async def scan(self, **_kwargs) -> List[Dict[str, Any]]:
        return []


@pytest_asyncio.fixture
async def detectors_app(test_db):
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set - skipping advice route tests")

    mock_solution_engine = Mock(spec=SolutionEngine)
    mock_solution_engine.get_solution = AsyncMock(return_value="x")
    mock_solution_engine.llm_provider = None

    fake_engine = _FakeAdviceEngine(test_db)
    websocket_manager = WebSocketManager()

    app = FastAPI()
    configure_cors(app)
    app.state.db = test_db

    api_router = create_api_router(
        db=test_db,
        solution_engine=mock_solution_engine,
        websocket_manager=websocket_manager,
        notification_service=None,
        advice_engine=fake_engine,
    )
    app.include_router(api_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake_engine, test_db


@pytest_asyncio.fixture
async def clean_settings(test_db):
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set")
    try:
        pg_db = test_db._db
        async with pg_db._acquire() as conn:
            await conn.execute(
                "DELETE FROM app_settings WHERE key = 'advice_detector_enabled'"
            )
    except Exception:
        pass
    yield


@pytest.mark.asyncio
async def test_list_detectors_returns_all_seven(detectors_app, clean_settings):
    client, _engine, _db = detectors_app
    resp = await client.get("/api/advice/detectors")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "detectors" in body
    assert len(body["detectors"]) == len(ALL_DETECTORS) == 7
    ids = {d["id"] for d in body["detectors"]}
    assert "fan-out-pattern" in ids
    assert "ephemeral-processes" in ids
    # All entries enabled by default.
    assert all(d["enabled"] is True for d in body["detectors"])
    # requires_hubble flag exposed.
    by_id = {d["id"]: d for d in body["detectors"]}
    assert by_id["fan-out-pattern"]["requires_hubble"] is True
    assert by_id["ephemeral-processes"]["requires_hubble"] is False
    # hubble_status block present.
    hs = body["hubble_status"]
    assert hs["available"] is False
    assert hs["reason"]


@pytest.mark.asyncio
async def test_put_toggle_state(detectors_app, clean_settings):
    client, _engine, _db = detectors_app
    resp = await client.put(
        "/api/advice/detectors/fan-out-pattern", json={"enabled": False}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": "fan-out-pattern", "enabled": False}

    # Confirm GET reflects the change.
    resp = await client.get("/api/advice/detectors")
    by_id = {d["id"]: d for d in resp.json()["detectors"]}
    assert by_id["fan-out-pattern"]["enabled"] is False
    # Others still default-enabled.
    assert by_id["ephemeral-processes"]["enabled"] is True

    # Re-enable.
    resp = await client.put(
        "/api/advice/detectors/fan-out-pattern", json={"enabled": True}
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_put_404_for_unknown_id(detectors_app, clean_settings):
    client, _engine, _db = detectors_app
    resp = await client.put(
        "/api/advice/detectors/no-such-detector", json={"enabled": False}
    )
    assert resp.status_code == 404
