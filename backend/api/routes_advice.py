"""AI Advice API routes.

Endpoints:

* ``POST   /advice/scan``               -- run detectors over a scope.
* ``GET    /advice/findings``           -- list findings (filterable).
* ``GET    /advice/findings/{id}``      -- single finding by id.
* ``DELETE /advice/findings/{id}``      -- dismiss.
* ``PUT    /advice/findings/{id}/restore`` -- restore a dismissed finding.

All authenticated. The scan endpoint requires ``write`` role; reads are
covered by the parent router's ``require_read`` dependency. Dismiss /
restore require ``write``.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

try:  # Pydantic v2
    from pydantic import model_validator as _v2_model_validator  # type: ignore

    _PYDANTIC_V2 = True
except ImportError:  # pragma: no cover - pydantic v1 fallback
    from pydantic import root_validator as _v1_root_validator  # type: ignore

    _PYDANTIC_V2 = False

from models.models import AdviceFinding
from services.advice.detectors import ALL_DETECTORS

from .auth import require_write
from .deps import RouterDeps

logger = logging.getLogger(__name__)


class AdviceScanRequest(BaseModel):
    namespace: str
    workload_kind: Optional[str] = None
    workload_name: Optional[str] = None
    pod_name: Optional[str] = None

    if _PYDANTIC_V2:

        @_v2_model_validator(mode="after")
        def _check_scope(self):  # type: ignore
            if self.pod_name and not (self.workload_kind and self.workload_name):
                raise ValueError(
                    "pod_name requires both workload_kind and workload_name"
                )
            if self.workload_name and not self.workload_kind:
                raise ValueError("workload_name requires workload_kind")
            return self

    else:  # pragma: no cover - pydantic v1

        @_v1_root_validator
        def _check_scope(cls, values):  # type: ignore
            pod_name = values.get("pod_name")
            workload_kind = values.get("workload_kind")
            workload_name = values.get("workload_name")
            if pod_name and not (workload_kind and workload_name):
                raise ValueError(
                    "pod_name requires both workload_kind and workload_name"
                )
            if workload_name and not workload_kind:
                raise ValueError("workload_name requires workload_kind")
            return values


class DetectorToggleRequest(BaseModel):
    enabled: bool


def _row_to_advice_finding(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return the dict shape used by the wire model + book-keeping fields."""
    # The mixin already returns a JSON-friendly dict; pass through.
    return row


def _detector_description(cls: type) -> str:
    """Return the first non-blank line of a detector's docstring."""
    doc = (cls.__doc__ or "").strip()
    if not doc:
        return ""
    for line in doc.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


_CSV_COLUMNS: List[str] = [
    "id",
    "created_at",
    "severity",
    "category",
    "detector_id",
    "namespace",
    "resource_kind",
    "resource_name",
    "title",
    "summary",
    "confidence",
    "dismissed",
    "recommended_change",
    "explanation",
    "evidence_json",
]


def _findings_to_csv(rows: List[Dict[str, Any]]) -> str:
    """Serialize advice-finding rows to a CSV string.

    The ``evidence`` dict is JSON-encoded into the final column.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "id": row.get("id", ""),
                "created_at": row.get("created_at") or "",
                "severity": row.get("severity") or "",
                "category": row.get("category") or "",
                "detector_id": row.get("detector_id") or "",
                "namespace": row.get("namespace") or "",
                "resource_kind": row.get("resource_kind") or "",
                "resource_name": row.get("resource_name") or "",
                "title": row.get("title") or "",
                "summary": row.get("summary") or "",
                "confidence": row.get("confidence", ""),
                "dismissed": "true" if row.get("dismissed") else "false",
                "recommended_change": row.get("recommended_change") or "",
                "explanation": row.get("explanation") or "",
                "evidence_json": json.dumps(row.get("evidence") or {}),
            }
        )
    return buf.getvalue()


def build_router(deps: RouterDeps) -> APIRouter:
    """Construct the ``/advice`` router."""
    router = APIRouter(prefix="/advice")
    db = deps.db
    websocket_manager = deps.websocket_manager
    advice_engine = getattr(deps, "advice_engine", None)

    @router.post(
        "/scan",
        dependencies=[Depends(require_write)],
    )
    async def scan_advice(body: AdviceScanRequest):
        if advice_engine is None:
            raise HTTPException(
                status_code=503,
                detail="Advice engine not configured",
            )
        scan_id = uuid.uuid4().hex
        scope = body.model_dump()
        logger.info("Advice scan starting (scan_id=%s, scope=%s)", scan_id, scope)
        try:
            await websocket_manager.broadcast_advice_scan_status(
                "started", scope, scan_id
            )
        except Exception:
            logger.exception("advice_scan_status 'started' broadcast failed")

        try:
            persisted = await advice_engine.scan(
                namespace=body.namespace,
                workload_kind=body.workload_kind,
                workload_name=body.workload_name,
                pod_name=body.pod_name,
            )
        except Exception as e:
            logger.exception(
                "Advice scan failed (scan_id=%s, scope=%s)", scan_id, scope
            )
            try:
                await websocket_manager.broadcast_advice_scan_status(
                    "failed", scope, scan_id
                )
            except Exception:
                logger.exception("advice_scan_status 'failed' broadcast failed")
            raise HTTPException(status_code=500, detail="Internal server error")

        # Broadcast each new finding.
        for wire in persisted:
            if wire.get("is_new"):
                try:
                    await websocket_manager.broadcast_advice_finding(wire)
                except Exception:
                    logger.exception("advice_finding broadcast failed")

        try:
            await websocket_manager.broadcast_advice_scan_status(
                "completed", scope, scan_id
            )
        except Exception:
            logger.exception("advice_scan_status 'completed' broadcast failed")

        logger.info(
            "Advice scan completed (scan_id=%s, findings=%d)",
            scan_id,
            len(persisted),
        )
        # Strip internal bookkeeping field before responding.
        clean = [{k: v for k, v in w.items() if k != "is_new"} for w in persisted]
        return {"findings": clean, "scan_id": scan_id}

    @router.get("/findings")
    async def list_advice_findings(
        include_dismissed: bool = Query(False),
        dismissed_only: bool = Query(False),
        namespace: Optional[str] = Query(None),
        resource_kind: Optional[str] = Query(None),
        resource_name: Optional[str] = Query(None),
    ):
        rows = await db.get_advice_findings(
            include_dismissed=include_dismissed,
            dismissed_only=dismissed_only,
            namespace=namespace,
            resource_kind=resource_kind,
            resource_name=resource_name,
        )
        return {"findings": [_row_to_advice_finding(r) for r in rows]}

    @router.get("/findings/export")
    async def export_advice_findings(
        format: str = Query("json", pattern="^(json|csv)$"),
        include_dismissed: bool = Query(False),
        dismissed_only: bool = Query(False),
        namespace: Optional[str] = Query(None),
        resource_kind: Optional[str] = Query(None),
        resource_name: Optional[str] = Query(None),
    ):
        rows = await db.get_advice_findings(
            include_dismissed=include_dismissed,
            dismissed_only=dismissed_only,
            namespace=namespace,
            resource_kind=resource_kind,
            resource_name=resource_name,
        )
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if format == "csv":
            body = _findings_to_csv(rows)
            return Response(
                content=body,
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="advice-findings-{date_str}.csv"'
                    )
                },
            )
        # JSON (default)
        body = json.dumps({"findings": [_row_to_advice_finding(r) for r in rows]})
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="advice-findings-{date_str}.json"'
                )
            },
        )

    @router.get("/detectors")
    async def list_detectors():
        if advice_engine is None:
            raise HTTPException(status_code=503, detail="Advice engine not configured")
        settings_service = getattr(advice_engine, "detector_settings", None)
        settings_map: Dict[str, bool] = {}
        if settings_service is not None:
            try:
                settings_map = await settings_service.get_all()
            except Exception:
                logger.exception("DetectorSettingsService.get_all failed")

        detectors_out: List[Dict[str, Any]] = []
        for cls in ALL_DETECTORS:
            sev = cls.default_severity
            sev_value = sev.value if hasattr(sev, "value") else str(sev)
            detectors_out.append(
                {
                    "id": cls.id,
                    "category": cls.category,
                    "default_severity": sev_value,
                    "requires_hubble": getattr(cls, "requires_hubble", False),
                    "enabled": settings_map.get(cls.id, True),
                    "description": _detector_description(cls),
                }
            )

        hubble_status: Dict[str, Any] = {
            "available": False,
            "reason": None,
            "flow_count": 0,
        }
        hubble = getattr(advice_engine, "hubble", None)
        if hubble is not None:
            try:
                status_obj = await hubble.status()
                hubble_status = {
                    "available": status_obj.available,
                    "reason": status_obj.reason,
                    "flow_count": status_obj.flow_count,
                }
            except Exception:
                logger.exception("hubble.status() failed; reporting unavailable")

        return {"detectors": detectors_out, "hubble_status": hubble_status}

    @router.put(
        "/detectors/{detector_id}",
        dependencies=[Depends(require_write)],
    )
    async def toggle_detector(detector_id: str, body: DetectorToggleRequest):
        known_ids = {cls.id for cls in ALL_DETECTORS}
        if detector_id not in known_ids:
            raise HTTPException(status_code=404, detail="Unknown detector id")
        if advice_engine is None:
            raise HTTPException(status_code=503, detail="Advice engine not configured")
        settings_service = getattr(advice_engine, "detector_settings", None)
        if settings_service is None:
            raise HTTPException(
                status_code=503, detail="Detector settings service not configured"
            )
        await settings_service.set_enabled(detector_id, body.enabled)
        return {"id": detector_id, "enabled": body.enabled}

    @router.get("/findings/{finding_id}")
    async def get_advice_finding(finding_id: int):
        row = await db.get_advice_finding_by_id(finding_id)
        if not row:
            raise HTTPException(status_code=404, detail="Advice finding not found")
        return _row_to_advice_finding(row)

    @router.delete(
        "/findings/{finding_id}",
        dependencies=[Depends(require_write)],
    )
    async def dismiss_finding(finding_id: int):
        existing = await db.get_advice_finding_by_id(finding_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Advice finding not found")
        ok = await db.dismiss_advice_finding(finding_id)
        if not ok:
            # Already dismissed; treat as a no-op success.
            return {"dismissed": True, "id": finding_id}
        try:
            await websocket_manager.broadcast_advice_finding_deleted(
                {
                    "id": finding_id,
                    "namespace": existing.get("namespace"),
                    "resource_kind": existing.get("resource_kind"),
                    "resource_name": existing.get("resource_name"),
                    "detector_id": existing.get("detector_id"),
                }
            )
        except Exception:
            logger.exception("advice_finding_deleted broadcast failed")
        return {"dismissed": True, "id": finding_id}

    @router.put(
        "/findings/{finding_id}/restore",
        dependencies=[Depends(require_write)],
    )
    async def restore_finding(finding_id: int):
        existing = await db.get_advice_finding_by_id(finding_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Advice finding not found")
        await db.restore_advice_finding(finding_id)
        # Re-broadcast as a new finding so clients add it back to their list.
        try:
            refreshed = await db.get_advice_finding_by_id(finding_id)
            if refreshed:
                await websocket_manager.broadcast_advice_finding(refreshed)
        except Exception:
            logger.exception("advice_finding broadcast after restore failed")
        return {"restored": True, "id": finding_id}

    return router
