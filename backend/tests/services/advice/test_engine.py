"""Tests for ``services.advice.advice_engine.AdviceEngine``.

These tests exercise the engine with a fake DB and a fake TopologyService,
so no Kubernetes cluster or real database is required.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from llm_providers.base import LLMProvider, LLMResponse
from services.advice import advice_engine as engine_mod
from services.advice.advice_engine import AdviceEngine
from services.advice.findings import Finding, Severity, WorkloadContext
from services.advice.detectors.base import PatternDetector

# ---------------------------------------------------------------- fakes


class _FakeDB:
    """Minimal in-memory stand-in for the AdviceFindingsMixin."""

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []
        self.clear_calls: List[Dict[str, Any]] = []
        self._next_id = 1

    async def clear_advice_findings_for_scope(
        self,
        *,
        namespace: Optional[str] = None,
        resource_kind: Optional[str] = None,
        resource_name: Optional[str] = None,
    ) -> int:
        self.clear_calls.append(
            {
                "namespace": namespace,
                "resource_kind": resource_kind,
                "resource_name": resource_name,
            }
        )
        before = len(self.rows)
        self.rows = [
            r
            for r in self.rows
            if r.get("dismissed")
            or (namespace is not None and r.get("namespace") != namespace)
        ]
        return before - len(self.rows)

    async def save_advice_finding(self, wire: Dict[str, Any]) -> Tuple[int, bool]:
        key = (
            wire.get("detector_id"),
            wire.get("namespace"),
            wire.get("resource_kind"),
            wire.get("resource_name"),
        )
        for row in self.rows:
            row_key = (
                row.get("detector_id"),
                row.get("namespace"),
                row.get("resource_kind"),
                row.get("resource_name"),
            )
            if row_key == key and not row.get("dismissed"):
                row.update({k: v for k, v in wire.items() if k != "id"})
                return row["id"], False
        new = dict(wire)
        new["id"] = self._next_id
        new["dismissed"] = False
        self._next_id += 1
        self.rows.append(new)
        return new["id"], True

    async def get_advice_finding_by_id(
        self, finding_id: int
    ) -> Optional[Dict[str, Any]]:
        for row in self.rows:
            if row.get("id") == finding_id:
                return dict(row)
        return None

    async def update_advice_finding_explanation(
        self, finding_id: int, explanation: str
    ) -> bool:
        for row in self.rows:
            if row.get("id") == finding_id:
                row["explanation"] = explanation
                return True
        return False


class _FakeTopology:
    """Fake :class:`TopologyService` returning canned namespace contexts."""

    def __init__(self, ns_ctx: Dict[str, Any]) -> None:
        self._ns_ctx = ns_ctx
        self.calls: List[str] = []

    async def _fetch_namespace_context(self, namespace: str) -> Dict[str, Any]:
        self.calls.append(namespace)
        return self._ns_ctx

    def _init_k8s(self) -> None:
        raise RuntimeError("no k8s in tests")


class _FakeProvider(LLMProvider):
    """LLMProvider stub that returns a fixed explanation."""

    def __init__(self, content: str = "## Why this matters\nbecause") -> None:
        self.api_key = "test"
        self.model = "fake"
        self._content = content
        self.calls: List[Tuple[str, str]] = []

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def default_model(self) -> str:
        return "fake"

    async def generate_solution(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError

    async def generate_raw(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.calls.append((system_prompt, user_prompt))
        return LLMResponse(content=self._content, model="fake", provider="fake")


class _StaticDetector(PatternDetector):
    """Detector that emits one fixed finding regardless of context."""

    id = "static-test"
    default_severity = Severity.LOW
    category = "test"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        return [
            Finding(
                detector_id=self.id,
                severity=self.default_severity,
                category=self.category,
                title="static",
                summary="a static finding",
                resource_kind="Deployment",
                resource_name="api",
                namespace=ctx.namespace,
                evidence={"replicas": 3},
                recommended_change="do the thing",
                confidence=0.9,
            )
        ]


class _ExplodingDetector(PatternDetector):
    id = "exploding-test"
    default_severity = Severity.LOW
    category = "test"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        raise RuntimeError("boom")


# ---------------------------------------------------------------- helpers


def _patch_detectors(monkeypatch, detector_classes):
    """Force AdviceEngine to use the given detector classes for this test."""
    # The engine snapshots ALL_DETECTORS at __init__, so patching the source
    # list before construction is enough.
    monkeypatch.setattr(engine_mod, "ALL_DETECTORS", detector_classes)


def _empty_ns_ctx() -> Dict[str, Any]:
    return {
        "pods": [],
        "replicasets": [],
        "services": [],
        "ingresses": [],
        "hpas": [],
        "netpols": [],
        "jobs": [],
        "pvcs": [],
        "configmaps": [],
    }


# ---------------------------------------------------------------- tests


@pytest.mark.asyncio
async def test_scan_runs_detectors_and_persists(monkeypatch):
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: None)

    result = await eng.scan(namespace="default")

    assert len(result) == 1
    assert result[0]["detector_id"] == "static-test"
    assert result[0]["is_new"] is True
    assert result[0]["explanation"] is None  # no provider
    assert len(db.rows) == 1
    assert db.rows[0]["namespace"] == "default"


@pytest.mark.asyncio
async def test_clear_called_before_detectors_run(monkeypatch):
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: None)

    await eng.scan(namespace="default")
    assert len(db.clear_calls) == 1
    assert db.clear_calls[0]["namespace"] == "default"


@pytest.mark.asyncio
async def test_workload_scope_passes_kind_and_name_to_clear(monkeypatch):
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: None)

    await eng.scan(namespace="default", workload_kind="Deployment", workload_name="api")
    assert db.clear_calls[-1] == {
        "namespace": "default",
        "resource_kind": "Deployment",
        "resource_name": "api",
    }


@pytest.mark.asyncio
async def test_scan_does_not_invoke_llm_provider(monkeypatch):
    """LLM explanation is deferred to view-time; scan must not call provider."""
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    provider = _FakeProvider(content="## Why this matters\nbecause reasons")
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: provider)

    result = await eng.scan(namespace="default")
    # Scanned findings are persisted with explanation=None; the explainer
    # runs lazily via POST /api/advice/findings/{id}/explain.
    assert result[0]["explanation"] is None
    assert provider.calls == [], "scan must not invoke the LLM provider"


@pytest.mark.asyncio
async def test_detector_exception_does_not_stop_scan(monkeypatch):
    _patch_detectors(monkeypatch, [_ExplodingDetector, _StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: None)

    result = await eng.scan(namespace="default")
    assert len(result) == 1
    assert result[0]["detector_id"] == "static-test"


@pytest.mark.asyncio
async def test_scan_does_not_call_provider_getter(monkeypatch):
    """Scan must not resolve the LLM provider; that happens at explain-time."""
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())

    calls = {"n": 0}

    def getter():
        calls["n"] += 1
        return None

    eng = AdviceEngine(db, topology, llm_provider_getter=getter)
    await eng.scan(namespace="default")
    await eng.scan(namespace="default")
    assert calls["n"] == 0


# ----------------------------------------------------------- explain_finding


@pytest.mark.asyncio
async def test_explain_finding_returns_none_when_missing(monkeypatch):
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: None)

    result = await eng.explain_finding(999)
    assert result is None


@pytest.mark.asyncio
async def test_explain_finding_invokes_provider_and_persists(monkeypatch):
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    provider = _FakeProvider(content="## Why this matters\nbecause reasons")
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: provider)

    persisted = await eng.scan(namespace="default")
    fid = persisted[0]["id"]
    assert persisted[0]["explanation"] is None

    row = await eng.explain_finding(fid)
    assert row is not None
    assert row["explanation"] == "## Why this matters\nbecause reasons"
    assert provider.calls, "explainer must call provider.generate_raw"
    # Persisted back to the row.
    stored = await db.get_advice_finding_by_id(fid)
    assert stored["explanation"] == "## Why this matters\nbecause reasons"


@pytest.mark.asyncio
async def test_explain_finding_idempotent_when_explanation_present(monkeypatch):
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    provider = _FakeProvider(content="should-not-be-called")
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: provider)

    persisted = await eng.scan(namespace="default")
    fid = persisted[0]["id"]
    # Pre-populate explanation directly on the row.
    db.rows[0]["explanation"] = "## cached\nexisting text"

    row = await eng.explain_finding(fid)
    assert row["explanation"] == "## cached\nexisting text"
    assert provider.calls == [], "provider must NOT be called when cached"


@pytest.mark.asyncio
async def test_explain_finding_no_provider_returns_row_unchanged(monkeypatch):
    _patch_detectors(monkeypatch, [_StaticDetector])
    db = _FakeDB()
    topology = _FakeTopology(_empty_ns_ctx())
    eng = AdviceEngine(db, topology, llm_provider_getter=lambda: None)

    persisted = await eng.scan(namespace="default")
    fid = persisted[0]["id"]

    row = await eng.explain_finding(fid)
    assert row is not None
    assert row["explanation"] is None
    # Nothing persisted either.
    stored = await db.get_advice_finding_by_id(fid)
    assert stored["explanation"] is None
