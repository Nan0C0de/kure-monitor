from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
from typing import List
from api.auth import AUTH_API_KEY, validate_ws_token
from models.models import PodFailureResponse, SecurityFindingResponse, ClusterMetrics
from services.prometheus_metrics import WEBSOCKET_CONNECTIONS_ACTIVE

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.router = APIRouter()
        self.router.websocket("/ws")(self.websocket_endpoint)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        WEBSOCKET_CONNECTIONS_ACTIVE.inc()
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        WEBSOCKET_CONNECTIONS_ACTIVE.dec()
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def _broadcast(self, message_type: str, data, description: str = None, parallel: bool = False):
        """Generic broadcast to all connected WebSocket clients.

        Args:
            message_type: The message type string sent to clients.
            data: The payload (dict, list, or Pydantic model with .dict()).
            description: Human-readable label for log messages. Defaults to message_type.
            parallel: If True, send to all clients concurrently with timeouts.
        """
        if not self.active_connections:
            return

        desc = description or message_type

        if hasattr(data, 'dict'):
            data = data.dict()

        if parallel:
            serialized = json.dumps({"type": message_type, "data": data}, default=str)

            async def send_to_client(connection):
                try:
                    await asyncio.wait_for(connection.send_text(serialized), timeout=10.0)
                    return True, connection
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout sending {desc} to WebSocket client")
                    return False, connection
                except Exception as e:
                    logger.warning(f"Failed to send {desc} to WebSocket: {e}")
                    return False, connection

            results = await asyncio.gather(
                *[send_to_client(conn) for conn in self.active_connections],
                return_exceptions=True,
            )

            disconnected = []
            for result in results:
                if isinstance(result, tuple):
                    success, conn = result
                    if not success:
                        disconnected.append(conn)
        else:
            message = {"type": message_type, "data": data}
            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(json.dumps(message, default=str))
                except Exception as e:
                    logger.warning(f"Failed to send {desc} to WebSocket: {e}")
                    disconnected.append(connection)

        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

    # --- Pod broadcasts ---

    async def broadcast_pod_failure(self, failure: PodFailureResponse):
        """Broadcast new pod failure to all connected clients"""
        await self._broadcast("pod_failure", failure)

    async def broadcast_pod_deleted(self, namespace: str, pod_name: str):
        """Broadcast pod deletion to all connected clients"""
        await self._broadcast("pod_deleted", {"namespace": namespace, "pod_name": pod_name})

    async def broadcast_pod_solution_updated(self, pod_failure: PodFailureResponse):
        """Broadcast pod solution update to all connected clients"""
        await self._broadcast("pod_solution_updated", pod_failure)

    async def broadcast_pod_record_deleted(self, pod_id: int):
        """Broadcast permanent pod record deletion to all connected clients"""
        await self._broadcast("pod_record_deleted", {"id": pod_id})

    async def broadcast_pod_status_change(self, pod_failure: PodFailureResponse):
        """Broadcast pod status change to all connected clients"""
        await self._broadcast("pod_status_change", pod_failure)

    # --- Security broadcasts ---

    async def broadcast_security_finding(self, finding: SecurityFindingResponse):
        """Broadcast new security finding to all connected clients"""
        await self._broadcast("security_finding", finding)

    async def broadcast_security_finding_deleted(self, finding_data: dict):
        """Broadcast security finding deletion to all connected clients"""
        await self._broadcast("security_finding_deleted", finding_data)

    async def broadcast_security_rescan_status(self, status: str, reason: str = None):
        """Broadcast security rescan status to all connected clients (started/completed)"""
        logger.info(f"Broadcasting security rescan status: {status} (reason: {reason}) to {len(self.active_connections)} clients")
        await self._broadcast("security_rescan_status", {"status": status, "reason": reason})

    # --- Admin/exclusion broadcasts ---

    async def broadcast_namespace_exclusion_change(self, namespace: str, action: str):
        """Broadcast namespace exclusion change to all connected clients (including scanners)"""
        await self._broadcast("namespace_exclusion_change", {"namespace": namespace, "action": action})

    async def broadcast_pod_exclusion_change(self, pod_name: str, action: str):
        """Broadcast pod exclusion change to all connected clients (including agent)"""
        await self._broadcast("pod_exclusion_change", {"pod_name": pod_name, "action": action})

    async def broadcast_rule_exclusion_change(self, rule_title: str, action: str, namespace: str = None):
        """Broadcast rule exclusion change to all connected clients (including scanners)"""
        await self._broadcast("rule_exclusion_change", {"rule_title": rule_title, "namespace": namespace, "action": action})

    async def broadcast_trusted_registry_change(self, registry: str, action: str):
        """Broadcast trusted registry change to all connected clients (including scanners)"""
        logger.info(f"Broadcasting trusted registry change: {registry} -> {action} to {len(self.active_connections)} clients")
        await self._broadcast(
            "trusted_registry_change",
            {"registry": registry, "action": action},
            description="trusted registry change",
            parallel=True,
        )

    # --- Metrics broadcasts ---

    async def broadcast_cluster_metrics(self, metrics: ClusterMetrics):
        """Broadcast cluster metrics to all connected clients"""
        await self._broadcast("cluster_metrics", metrics)

    # --- WebSocket endpoint ---

    async def websocket_endpoint(self, websocket: WebSocket):
        # When auth is enabled, all WebSocket connections must provide a valid token.
        # The frontend passes the user's API key; agent/scanner pass AUTH_API_KEY
        # from their environment.
        if AUTH_API_KEY:
            token = websocket.query_params.get("token")
            if not validate_ws_token(token):
                await websocket.close(code=4001, reason="Unauthorized")
                return
        await self.connect(websocket)
        try:
            while True:
                # Keep connection alive
                await websocket.receive_text()
        except WebSocketDisconnect:
            self.disconnect(websocket)
