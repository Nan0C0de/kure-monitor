"""Route tests for ``GET /advice/findings/export``."""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware import configure_cors
from api.routes import create_api_router
from services.advice.detector_settings import DetectorSettingsService
from services.advice.hubble import StubHubbleClient
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager

DATABASE_AVAILABLE = bool(os.getenv("DATABASE_URL"))


class _FakeAdviceEngine:
    def __init__(self, db) -> None:
        self.hubble = StubHubbleClient()
        self.detector_settings = DetectorSettingsService(db)

    async def scan(self, **_kwargs) -> List[Dict[str, Any]]:
        return []


def _wire_finding(
    *,
    id: int,
    detector_id: str = "static-test",
    namespace: str = "default",
    resource_kind: str = "Deployment",
    resource_name: str = "api",
    dismissed: bool = False,
):
    return {
        "id": id,
        "detector_id": detector_id,
        "severity": "low",
        "category": "test",
        "title": "Static finding",
        "summary": "A canned finding for the export test.",
        "resource_kind": resource_kind,
        "resource_name": resource_name,
        "namespace": namespace,
        "evidence": {"k": "v"},
        "recommended_change": "do the thing",
        "confidence": 0.9,
        "explanation": None,
        "dismissed": dismissed,
        "is_new": True,
    }


@pytest_asyncio.fixture
async def export_app(test_db):
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set - skipping export route tests")

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
        yield client, test_db


@pytest_asyncio.fixture
async def clean_findings(test_db):
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set")
    try:
        pg_db = test_db._db
        async with pg_db._acquire() as conn:
            await conn.execute("DELETE FROM advice_findings")
    except Exception:
        pass
    yield


@pytest.mark.asyncio
async def test_export_json_returns_valid_json(export_app, clean_findings):
    client, db = export_app
    await db.save_advice_finding(_wire_finding(id=0, namespace="ns1"))

    resp = await client.get("/api/advice/findings/export?format=json")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/json")
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd and ".json" in cd
    body = json.loads(resp.content)
    assert "findings" in body
    assert len(body["findings"]) == 1
    assert body["findings"][0]["namespace"] == "ns1"


@pytest.mark.asyncio
async def test_export_default_is_json(export_app, clean_findings):
    client, db = export_app
    await db.save_advice_finding(_wire_finding(id=0, namespace="ns1"))
    resp = await client.get("/api/advice/findings/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_export_csv_returns_csv(export_app, clean_findings):
    client, db = export_app
    await db.save_advice_finding(_wire_finding(id=0, namespace="ns1"))

    resp = await client.get("/api/advice/findings/export?format=csv")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd and ".csv" in cd

    reader = csv.DictReader(io.StringIO(resp.text))
    assert "evidence_json" in (reader.fieldnames or [])
    assert "severity" in (reader.fieldnames or [])
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["namespace"] == "ns1"
    # evidence got JSON-encoded into the last column.
    assert json.loads(rows[0]["evidence_json"]) == {"k": "v"}


@pytest.mark.asyncio
async def test_export_applies_namespace_filter(export_app, clean_findings):
    client, db = export_app
    await db.save_advice_finding(_wire_finding(id=0, namespace="ns1"))
    await db.save_advice_finding(
        _wire_finding(id=0, namespace="ns2", resource_name="other")
    )

    resp = await client.get("/api/advice/findings/export?format=json&namespace=ns1")
    assert resp.status_code == 200
    body = json.loads(resp.content)
    namespaces = {f["namespace"] for f in body["findings"]}
    assert namespaces == {"ns1"}


@pytest.mark.asyncio
async def test_export_rejects_invalid_format(export_app, clean_findings):
    client, _db = export_app
    resp = await client.get("/api/advice/findings/export?format=xml")
    # Pydantic / FastAPI returns 422 for query-pattern violations.
    assert resp.status_code == 422
