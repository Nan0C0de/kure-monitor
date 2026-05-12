"""Verify ``AdviceEngine`` honors ``DetectorSettingsService`` toggles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from services.advice import advice_engine as engine_mod
from services.advice.advice_engine import AdviceEngine
from services.advice.detector_settings import DetectorSettingsService
from services.advice.detectors.base import PatternDetector
from services.advice.findings import Finding, Severity, WorkloadContext


class _FakeDB:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []
        self._kv: Dict[str, str] = {}
        self._next_id = 1

    async def clear_advice_findings_for_scope(self, **_kwargs) -> int:
        return 0

    async def save_advice_finding(self, wire: Dict[str, Any]) -> Tuple[int, bool]:
        wire = dict(wire)
        wire["id"] = self._next_id
        self._next_id += 1
        self.rows.append(wire)
        return wire["id"], True

    async def get_app_setting(self, key: str) -> Optional[str]:
        return self._kv.get(key)

    async def set_app_setting(self, key: str, value: str) -> None:
        self._kv[key] = value


class _FakeTopology:
    def __init__(self) -> None:
        self._ctx = {
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

    async def _fetch_namespace_context(self, namespace: str) -> Dict[str, Any]:
        return self._ctx

    def _init_k8s(self) -> None:
        raise RuntimeError("no k8s")


class _DetectorA(PatternDetector):
    id = "detector-a"
    default_severity = Severity.LOW
    category = "test"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        return [
            Finding(
                detector_id=self.id,
                severity=self.default_severity,
                category=self.category,
                title="a",
                summary="a",
                resource_kind="Deployment",
                resource_name="x",
                namespace=ctx.namespace,
                evidence={},
                recommended_change="-",
                confidence=0.5,
            )
        ]


class _DetectorB(PatternDetector):
    id = "detector-b"
    default_severity = Severity.LOW
    category = "test"

    async def detect(self, ctx: WorkloadContext) -> List[Finding]:
        return [
            Finding(
                detector_id=self.id,
                severity=self.default_severity,
                category=self.category,
                title="b",
                summary="b",
                resource_kind="Deployment",
                resource_name="y",
                namespace=ctx.namespace,
                evidence={},
                recommended_change="-",
                confidence=0.5,
            )
        ]


@pytest.mark.asyncio
async def test_disabled_detector_is_skipped(monkeypatch):
    monkeypatch.setattr(engine_mod, "ALL_DETECTORS", [_DetectorA, _DetectorB])
    db = _FakeDB()
    settings = DetectorSettingsService(db)
    eng = AdviceEngine(
        db=db,
        topology_service=_FakeTopology(),
        llm_provider_getter=lambda: None,
        detector_settings=settings,
    )

    # First scan: both detectors fire.
    persisted = await eng.scan(namespace="ns")
    ids = {f["detector_id"] for f in persisted}
    assert ids == {"detector-a", "detector-b"}

    # Disable detector-b.
    await settings.set_enabled("detector-b", False)
    persisted = await eng.scan(namespace="ns")
    ids = {f["detector_id"] for f in persisted}
    assert ids == {"detector-a"}

    # Re-enable: both fire again.
    await settings.set_enabled("detector-b", True)
    persisted = await eng.scan(namespace="ns")
    ids = {f["detector_id"] for f in persisted}
    assert ids == {"detector-a", "detector-b"}
