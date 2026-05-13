"""Smoke tests for the ``/api/advice`` HTTP surface.

These tests require ``DATABASE_URL`` and skip otherwise (mirroring the
existing route-test pattern in ``tests/conftest.py``).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, Mock

from api.middleware import configure_cors
from api.routes import create_api_router
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager

DATABASE_AVAILABLE = bool(os.getenv("DATABASE_URL"))


class _FakeAdviceEngine:
    """Stand-in engine that records calls and returns canned findings."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._next_id = 1000
        self.canned: List[Dict[str, Any]] = []
        self.explain_mock: Optional[Any] = None

    def queue(self, finding: Dict[str, Any]) -> None:
        self.canned.append(finding)

    async def explain_finding(self, finding_id: int):
        if self.explain_mock is None:
            return None
        return await self.explain_mock(finding_id)

    async def scan(
        self,
        *,
        namespace: str,
        workload_kind: Optional[str] = None,
        workload_name: Optional[str] = None,
        pod_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self.calls.append(
            {
                "namespace": namespace,
                "workload_kind": workload_kind,
                "workload_name": workload_name,
                "pod_name": pod_name,
            }
        )
        # The route layer expects the engine to have already persisted the
        # findings; the canned items already include an ``id`` and ``is_new``.
        return list(self.canned)


def _wire_finding(
    *,
    id: int,
    detector_id: str = "static-test",
    namespace: str = "default",
    resource_kind: str = "Deployment",
    resource_name: str = "api",
    dismissed: bool = False,
    is_new: bool = True,
) -> Dict[str, Any]:
    return {
        "id": id,
        "detector_id": detector_id,
        "severity": "low",
        "category": "test",
        "title": "Static finding",
        "summary": "A canned finding for the route test.",
        "resource_kind": resource_kind,
        "resource_name": resource_name,
        "namespace": namespace,
        "evidence": {"k": "v"},
        "recommended_change": "do the thing",
        "confidence": 0.9,
        "explanation": None,
        "dismissed": dismissed,
        "is_new": is_new,
    }


@pytest_asyncio.fixture
async def advice_app(test_db):
    """FastAPI app wired with a fake AdviceEngine + the real test DB."""
    if not DATABASE_AVAILABLE:
        pytest.skip("DATABASE_URL not set - skipping advice route tests")

    mock_solution_engine = Mock(spec=SolutionEngine)
    mock_solution_engine.get_solution = AsyncMock(return_value="x")
    mock_solution_engine.llm_provider = None

    fake_advice_engine = _FakeAdviceEngine()
    websocket_manager = WebSocketManager()

    app = FastAPI()
    configure_cors(app)
    app.state.db = test_db

    api_router = create_api_router(
        db=test_db,
        solution_engine=mock_solution_engine,
        websocket_manager=websocket_manager,
        notification_service=None,
        advice_engine=fake_advice_engine,
    )
    app.include_router(api_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake_advice_engine, test_db


@pytest_asyncio.fixture
async def clean_advice_table(test_db):
    """Clear the ``advice_findings`` table before each test."""
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
async def test_scan_returns_findings_and_scan_id(advice_app, clean_advice_table):
    client, fake_engine, db = advice_app
    fake_engine.queue(_wire_finding(id=1, namespace="ns1"))

    # Persist directly so list endpoint sees it (route layer reads from db).
    await db.save_advice_finding(_wire_finding(id=0, namespace="ns1"))

    resp = await client.post("/api/advice/scan", json={"namespace": "ns1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "scan_id" in body
    assert len(body["findings"]) == 1
    assert body["findings"][0]["detector_id"] == "static-test"
    # Confirm engine was called with the right scope.
    assert fake_engine.calls[-1] == {
        "namespace": "ns1",
        "workload_kind": None,
        "workload_name": None,
        "pod_name": None,
    }


@pytest.mark.asyncio
async def test_scan_rejects_pod_without_workload(advice_app, clean_advice_table):
    client, _engine, _db = advice_app
    resp = await client.post(
        "/api/advice/scan", json={"namespace": "n", "pod_name": "p"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_scan_rejects_workload_without_kind(advice_app, clean_advice_table):
    client, _engine, _db = advice_app
    resp = await client.post(
        "/api/advice/scan", json={"namespace": "n", "workload_name": "api"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_findings_filters_by_dismissed(advice_app, clean_advice_table):
    client, _engine, db = advice_app
    fid_active, _ = await db.save_advice_finding(
        _wire_finding(id=0, namespace="ns1", resource_name="active")
    )
    fid_dismissed, _ = await db.save_advice_finding(
        _wire_finding(id=0, namespace="ns1", resource_name="dismissed")
    )
    await db.dismiss_advice_finding(fid_dismissed)

    # Default: only active.
    resp = await client.get("/api/advice/findings")
    assert resp.status_code == 200
    names = [f["resource_name"] for f in resp.json()["findings"]]
    assert "active" in names
    assert "dismissed" not in names

    # include_dismissed=true: both.
    resp = await client.get("/api/advice/findings?include_dismissed=true")
    names = [f["resource_name"] for f in resp.json()["findings"]]
    assert "active" in names and "dismissed" in names

    # dismissed_only=true: just the dismissed one.
    resp = await client.get("/api/advice/findings?dismissed_only=true")
    names = [f["resource_name"] for f in resp.json()["findings"]]
    assert names == ["dismissed"]


@pytest.mark.asyncio
async def test_dismiss_and_restore(advice_app, clean_advice_table):
    client, _engine, db = advice_app
    fid, _ = await db.save_advice_finding(
        _wire_finding(id=0, namespace="ns1", resource_name="api")
    )

    resp = await client.delete(f"/api/advice/findings/{fid}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"dismissed": True, "id": fid}

    row = await db.get_advice_finding_by_id(fid)
    assert row["dismissed"] is True

    resp = await client.put(f"/api/advice/findings/{fid}/restore")
    assert resp.status_code == 200
    assert resp.json() == {"restored": True, "id": fid}

    row = await db.get_advice_finding_by_id(fid)
    assert row["dismissed"] is False


@pytest.mark.asyncio
async def test_dismiss_404_for_unknown_id(advice_app, clean_advice_table):
    client, _engine, _db = advice_app
    resp = await client.delete("/api/advice/findings/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_single_finding(advice_app, clean_advice_table):
    client, _engine, db = advice_app
    fid, _ = await db.save_advice_finding(
        _wire_finding(id=0, namespace="ns1", resource_name="api")
    )

    resp = await client.get(f"/api/advice/findings/{fid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == fid
    assert body["resource_name"] == "api"

    resp = await client.get("/api/advice/findings/999999")
    assert resp.status_code == 404


class TestExplainEndpoint:
    """``POST /api/advice/findings/{id}/explain`` -- on-demand LLM explanation."""

    @pytest.mark.asyncio
    async def test_404_when_finding_missing(self, advice_app, clean_advice_table):
        client, fake_engine, _db = advice_app
        fake_engine.explain_mock = AsyncMock(return_value=None)

        resp = await client.post("/api/advice/findings/424242/explain")
        assert resp.status_code == 404
        fake_engine.explain_mock.assert_awaited_once_with(424242)

    @pytest.mark.asyncio
    async def test_idempotent_when_explanation_present(
        self, advice_app, clean_advice_table
    ):
        client, fake_engine, _db = advice_app
        cached_row = _wire_finding(id=42, namespace="ns1")
        cached_row["explanation"] = "## cached\nstuff"
        cached_row.pop("is_new", None)
        fake_engine.explain_mock = AsyncMock(return_value=cached_row)

        resp = await client.post("/api/advice/findings/42/explain")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["explanation"] == "## cached\nstuff"
        assert body["id"] == 42
        # Engine was invoked exactly once with the right id.
        fake_engine.explain_mock.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_generates_and_returns_new_explanation(
        self, advice_app, clean_advice_table
    ):
        client, fake_engine, _db = advice_app
        updated_row = _wire_finding(id=77, namespace="ns1")
        updated_row["explanation"] = "## Why this matters\nfresh"
        updated_row.pop("is_new", None)
        fake_engine.explain_mock = AsyncMock(return_value=updated_row)

        resp = await client.post("/api/advice/findings/77/explain")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == 77
        assert body["explanation"] == "## Why this matters\nfresh"
        assert body["detector_id"] == "static-test"
        assert body["resource_name"] == "api"
        fake_engine.explain_mock.assert_awaited_once_with(77)

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_explainer_noop(
        self, advice_app, clean_advice_table
    ):
        """No LLM provider / empty response -> row returned with explanation=None."""
        client, fake_engine, _db = advice_app
        unchanged_row = _wire_finding(id=88, namespace="ns1")
        unchanged_row.pop("is_new", None)
        # explanation stays None
        fake_engine.explain_mock = AsyncMock(return_value=unchanged_row)

        resp = await client.post("/api/advice/findings/88/explain")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == 88
        assert body["explanation"] is None
        fake_engine.explain_mock.assert_awaited_once_with(88)
