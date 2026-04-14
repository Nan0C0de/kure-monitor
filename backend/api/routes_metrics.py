from fastapi import APIRouter, Depends, HTTPException
import logging

from services.prometheus_metrics import SECURITY_SCAN_DURATION_SECONDS
from .auth import require_service_token
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_metrics_ingest_router(deps: RouterDeps) -> APIRouter:
    """Metrics-ingest endpoints (agent/scanner traffic). Uses service token auth."""
    router = APIRouter(dependencies=[Depends(require_service_token)])

    @router.post("/metrics/security-scan-duration")
    async def report_security_scan_duration(data: dict):
        """Receive security scan duration from scanner for Prometheus metrics"""
        duration = data.get("duration_seconds")
        if duration is not None:
            SECURITY_SCAN_DURATION_SECONDS.set(float(duration))
            logger.info(f"Security scan duration: {duration:.1f}s")
            return {"message": "Scan duration recorded"}
        raise HTTPException(status_code=400, detail="duration_seconds is required")

    return router
