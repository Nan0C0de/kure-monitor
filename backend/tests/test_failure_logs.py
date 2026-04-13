"""Tests for failure-log capture, storage, and the log-aware troubleshoot flow."""

import base64
import gzip
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Request

from api.middleware import configure_cors
from api.routes import create_api_router
from models.models import (
    ContainerFailureLogs,
    ContainerLogEntry,
    FailureLogsPayload,
    PodFailureResponse,
)
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_logs_payload(
    container: str = "app",
    previous_text: str = "line1\nline2\nPANIC: boom\n",
    include_current: bool = False,
    truncated: bool = False,
) -> FailureLogsPayload:
    """Build a FailureLogsPayload where data is base64-of-gzip(text)."""
    def _encode(text: str) -> ContainerLogEntry:
        gzipped = gzip.compress(text.encode("utf-8"))
        b64 = base64.b64encode(gzipped).decode("ascii")
        return ContainerLogEntry(
            data=b64,
            original_size=len(text.encode("utf-8")),
            lines=len(text.splitlines()),
            truncated=truncated,
        )

    logs = ContainerFailureLogs(previous=_encode(previous_text))
    if include_current:
        logs.current = _encode("current instance log\n")
    return FailureLogsPayload(containers={container: logs})


def _pod_report(failure_reason: str, include_logs: bool = False, **overrides) -> dict:
    unique = uuid.uuid4().hex[:8]
    data = {
        "pod_name": f"test-pod-{unique}",
        "namespace": "default",
        "node_name": "test-node",
        "phase": "Running",
        "creation_timestamp": "2025-01-01T00:00:00Z",
        "failure_reason": failure_reason,
        "failure_message": "container crashing",
        "container_statuses": [],
        "events": [],
        "logs": "",
        "manifest": "apiVersion: v1\nkind: Pod",
    }
    data.update(overrides)
    if include_logs:
        data["failure_logs"] = _make_logs_payload().dict()
    return data


# ---------------------------------------------------------------------------
# Unit tests: payload shapes and prompt construction (no DB required)
# ---------------------------------------------------------------------------

def test_container_log_entry_defaults():
    entry = ContainerLogEntry(data="abc")
    assert entry.original_size == 0
    assert entry.lines == 0
    assert entry.truncated is False


def test_failure_logs_payload_accepts_nested_dict():
    payload = FailureLogsPayload(
        containers={
            "app": {
                "previous": {
                    "data": "abc",
                    "original_size": 10,
                    "lines": 2,
                    "truncated": False,
                },
                "error": None,
            }
        }
    )
    assert payload.version == 1
    assert payload.encoding == "gzip+base64"
    assert payload.containers["app"].previous.data == "abc"


def test_pod_failure_create_ignores_unknown_fields():
    from models.models import PodFailureCreate

    # Unknown fields must not cause 400s (pydantic v2 default = ignore).
    model = PodFailureCreate(
        pod_name="x",
        namespace="d",
        phase="Pending",
        creation_timestamp="2025-01-01T00:00:00Z",
        failure_reason="CrashLoopBackOff",
        some_future_field="ok",
    )
    assert not hasattr(model, "some_future_field")


# ---------------------------------------------------------------------------
# SolutionEngine: log-aware behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_aware_solution_no_llm_returns_error_string():
    engine = SolutionEngine()
    engine.llm_provider = None
    result = await engine.get_log_aware_solution(
        reason="CrashLoopBackOff",
        message="boom",
        events=[],
        container_statuses=[],
        pod_context={"pod_name": "p", "namespace": "n"},
        manifest="apiVersion: v1",
        container_logs=[{"container_name": "c", "source": "previous", "logs": "err", "truncated": False, "line_count": 1}],
    )
    assert "LLM" in result or "llm" in result.lower()
    assert "configure" in result.lower()


@pytest.mark.asyncio
async def test_log_aware_solution_prompt_contains_logs_and_manifest():
    engine = SolutionEngine()

    captured_prompts: dict = {}

    class _FakeProvider:
        provider_name = "fake"

        async def generate_raw(self, system_prompt, user_prompt):
            captured_prompts["system"] = system_prompt
            captured_prompts["user"] = user_prompt
            from llm_providers.base import LLMResponse
            return LLMResponse(content="ROOT CAUSE FOUND", provider="fake", model="m")

    engine.llm_provider = _FakeProvider()

    logs = [{
        "container_name": "worker",
        "source": "previous",
        "logs": "boot...\nERROR: cannot connect to db\n",
        "truncated": False,
        "line_count": 2,
    }]
    out = await engine.get_log_aware_solution(
        reason="CrashLoopBackOff",
        message="exit 1",
        events=[],
        container_statuses=[],
        pod_context={"pod_name": "p", "namespace": "n", "image": "img:1"},
        manifest="apiVersion: v1\nkind: Pod\n",
        container_logs=logs,
    )
    assert out == "ROOT CAUSE FOUND"
    prompt = captured_prompts["user"]
    assert "Previous Container Logs" in prompt
    assert "ERROR: cannot connect to db" in prompt
    assert "Pod Manifest" in prompt
    assert "worker" in prompt
    # System prompt emphasises logs as primary signal
    assert "primary" in captured_prompts["system"].lower()


@pytest.mark.asyncio
async def test_log_aware_solution_truncates_to_tail_lines(monkeypatch):
    # Set a tiny tail so we can assert truncation
    import core.config as cfg
    monkeypatch.setattr(cfg, "LLM_LOGS_TAIL_LINES", 3, raising=False)
    import services.solution_engine as se_mod
    monkeypatch.setattr(se_mod, "LLM_LOGS_TAIL_LINES", 3, raising=False)

    captured: dict = {}

    class _FakeProvider:
        provider_name = "fake"

        async def generate_raw(self, system_prompt, user_prompt):
            captured["user"] = user_prompt
            from llm_providers.base import LLMResponse
            return LLMResponse(content="ok", provider="fake", model="m")

    engine = SolutionEngine()
    engine.llm_provider = _FakeProvider()

    log_text = "\n".join(f"line-{i}" for i in range(20))
    await engine.get_log_aware_solution(
        reason="OOMKilled",
        message="",
        events=[],
        container_statuses=[],
        pod_context={"pod_name": "p", "namespace": "n"},
        manifest="",
        container_logs=[{
            "container_name": "c",
            "source": "previous",
            "logs": log_text,
            "truncated": False,
            "line_count": 20,
        }],
    )
    prompt = captured["user"]
    assert "line-19" in prompt
    # Kept only the last 3 lines (17, 18, 19); line-0 must be gone
    assert "line-0\n" not in prompt
    assert "truncated" in prompt.lower()


# ---------------------------------------------------------------------------
# Database tests (require DATABASE_URL)
# ---------------------------------------------------------------------------

def _require_db():
    import os
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set - skipping database tests")


def _base_pod_failure(reason: str = "CrashLoopBackOff") -> PodFailureResponse:
    return PodFailureResponse(
        id=0,
        pod_name=f"pod-{uuid.uuid4().hex[:8]}",
        namespace="default",
        node_name="n1",
        phase="Running",
        creation_timestamp="2025-01-01T00:00:00Z",
        failure_reason=reason,
        failure_message="boom",
        container_statuses=[],
        events=[],
        logs="",
        manifest="apiVersion: v1",
        solution="prev",
        timestamp="2025-01-01T00:00:00Z",
        dismissed=False,
    )


@pytest.mark.asyncio
async def test_save_and_load_pod_failure_logs_roundtrip(test_db):
    _require_db()
    pf = _base_pod_failure()
    pf_id = await test_db.save_pod_failure(pf)

    text = "line-a\nline-b\nPANIC\n"
    payload = _make_logs_payload("app", previous_text=text, include_current=True)

    rows = await test_db.save_pod_failure_logs(pf_id, payload)
    assert rows == 2  # previous + current

    assert await test_db.has_captured_logs(pf_id) is True
    logs = await test_db.get_pod_failure_logs(pf_id)
    by_source = {(e["container_name"], e["source"]): e for e in logs}
    assert by_source[("app", "previous")]["logs"] == text
    assert by_source[("app", "current")]["logs"].startswith("current instance log")


@pytest.mark.asyncio
async def test_save_pod_failure_logs_upsert(test_db):
    _require_db()
    pf_id = await test_db.save_pod_failure(_base_pod_failure())

    first = _make_logs_payload("app", previous_text="first\n")
    await test_db.save_pod_failure_logs(pf_id, first)
    second = _make_logs_payload("app", previous_text="replaced\n")
    await test_db.save_pod_failure_logs(pf_id, second)

    logs = await test_db.get_pod_failure_logs(pf_id)
    assert len(logs) == 1
    assert logs[0]["logs"] == "replaced\n"


@pytest.mark.asyncio
async def test_cascade_delete_removes_logs(test_db):
    _require_db()
    pf_id = await test_db.save_pod_failure(_base_pod_failure())
    await test_db.save_pod_failure_logs(pf_id, _make_logs_payload("app"))
    assert await test_db.has_captured_logs(pf_id) is True

    # Force-move to resolved then delete (delete_pod_failure requires resolved/ignored)
    await test_db.update_pod_status(pf_id, "investigating")
    await test_db.update_pod_status(pf_id, "ignored")
    assert await test_db.delete_pod_failure(pf_id) is True

    assert await test_db.has_captured_logs(pf_id) is False


@pytest.mark.asyncio
async def test_update_pod_troubleshoot_solution_sets_both_columns(test_db):
    _require_db()
    pf_id = await test_db.save_pod_failure(_base_pod_failure())
    ts = await test_db.update_pod_troubleshoot_solution(pf_id, "the fix")
    assert ts is not None

    pod = await test_db.get_pod_failure_by_id(pf_id)
    assert pod.log_aware_solution == "the fix"
    assert pod.log_aware_solution_generated_at == ts


@pytest.mark.asyncio
async def test_oversize_logs_marked_truncated_not_rejected(test_db):
    _require_db()
    pf_id = await test_db.save_pod_failure(_base_pod_failure())

    # Report original_size way beyond cap; truncated=false from agent
    huge_text = "x\n" * 10
    gzipped = gzip.compress(huge_text.encode("utf-8"))
    b64 = base64.b64encode(gzipped).decode("ascii")
    payload = FailureLogsPayload(containers={
        "app": ContainerFailureLogs(previous=ContainerLogEntry(
            data=b64,
            original_size=5 * 1024 * 1024,  # 5 MiB reported
            lines=10,
            truncated=False,
        ))
    })
    rows = await test_db.save_pod_failure_logs(pf_id, payload)
    assert rows == 1

    logs = await test_db.get_pod_failure_logs(pf_id)
    assert len(logs) == 1
    assert logs[0]["truncated"] is True


@pytest.mark.asyncio
async def test_logs_captured_flag_on_responses(test_db):
    _require_db()
    pf_id = await test_db.save_pod_failure(_base_pod_failure())

    pod = await test_db.get_pod_failure_by_id(pf_id)
    assert pod.logs_captured is False

    await test_db.save_pod_failure_logs(pf_id, _make_logs_payload())
    pod = await test_db.get_pod_failure_by_id(pf_id)
    assert pod.logs_captured is True

    # List endpoint also surfaces the flag
    all_pods = await test_db.get_pod_failures(include_dismissed=True)
    matching = next((p for p in all_pods if p.id == pf_id), None)
    assert matching is not None
    assert matching.logs_captured is True


# ---------------------------------------------------------------------------
# API tests (ingest + troubleshoot endpoint)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_solution_engine():
    engine = MagicMock(spec=SolutionEngine)
    engine.get_solution = AsyncMock(return_value="quick solution")
    engine.get_log_aware_solution = AsyncMock(return_value="LOG-AWARE solution")
    engine.llm_provider = object()
    return engine


@pytest.fixture
async def api_app(test_db, fake_solution_engine):
    _require_db()
    ws_manager = WebSocketManager()
    app = FastAPI()
    configure_cors(app)

    @app.get("/health")
    async def _h():
        return {"ok": True}

    api_router = create_api_router(
        db=test_db,
        solution_engine=fake_solution_engine,
        websocket_manager=ws_manager,
        notification_service=None,
    )
    app.include_router(api_router)

    from api.auth import require_auth, require_admin

    async def _no_auth(request: Request):
        request.state.role = "admin"

    def _no_admin(request: Request):
        pass

    app.dependency_overrides[require_auth] = _no_auth
    app.dependency_overrides[require_admin] = _no_admin
    return app


@pytest.fixture
async def api_client(api_app):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_report_failed_pod_stores_logs_for_crashloop(api_client, test_db):
    _require_db()
    data = _pod_report("CrashLoopBackOff", include_logs=True)
    resp = await api_client.post("/api/pods/failed", json=data)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    pid = body["id"]
    assert body["logs_captured"] is True

    # Logs were actually persisted
    stored = await test_db.get_pod_failure_logs(pid)
    assert any("PANIC" in e["logs"] for e in stored)


@pytest.mark.asyncio
async def test_report_failed_pod_skips_logs_for_imagepullbackoff(api_client, test_db):
    _require_db()
    data = _pod_report("ImagePullBackOff", include_logs=True)
    resp = await api_client.post("/api/pods/failed", json=data)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    pid = body["id"]
    assert body.get("logs_captured") is False

    stored = await test_db.get_pod_failure_logs(pid)
    assert stored == []


@pytest.mark.asyncio
async def test_troubleshoot_endpoint_generates_and_caches(api_client, test_db, fake_solution_engine):
    _require_db()
    data = _pod_report("CrashLoopBackOff", include_logs=True)
    resp = await api_client.post("/api/pods/failed", json=data)
    pid = resp.json()["id"]

    # First call: generated, cached=False
    r1 = await api_client.post(f"/api/pods/failed/{pid}/troubleshoot")
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    assert j1["cached"] is False
    assert j1["log_aware"] is True
    assert j1["solution"] == "LOG-AWARE solution"
    assert fake_solution_engine.get_log_aware_solution.await_count == 1

    # Second call: cached
    r2 = await api_client.post(f"/api/pods/failed/{pid}/troubleshoot")
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["cached"] is True
    assert j2["solution"] == "LOG-AWARE solution"
    # Still only one LLM call
    assert fake_solution_engine.get_log_aware_solution.await_count == 1

    # regenerate=true bypasses cache
    fake_solution_engine.get_log_aware_solution.return_value = "REGEN"
    r3 = await api_client.post(f"/api/pods/failed/{pid}/troubleshoot?regenerate=true")
    assert r3.status_code == 200
    j3 = r3.json()
    assert j3["cached"] is False
    assert j3["solution"] == "REGEN"
    assert fake_solution_engine.get_log_aware_solution.await_count == 2


@pytest.mark.asyncio
async def test_troubleshoot_404_when_pod_missing(api_client):
    _require_db()
    resp = await api_client.post("/api/pods/failed/999999/troubleshoot")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_troubleshoot_400_for_wrong_failure_type(api_client, test_db):
    _require_db()
    pf = _base_pod_failure("ImagePullBackOff")
    pf_id = await test_db.save_pod_failure(pf)
    resp = await api_client.post(f"/api/pods/failed/{pf_id}/troubleshoot")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_troubleshoot_404_when_no_logs(api_client, test_db):
    _require_db()
    pf = _base_pod_failure("CrashLoopBackOff")
    pf_id = await test_db.save_pod_failure(pf)
    resp = await api_client.post(f"/api/pods/failed/{pf_id}/troubleshoot")
    assert resp.status_code == 404
