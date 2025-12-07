from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
from typing import List
from models.models import PodFailureResponse, SecurityFindingResponse, CVEFindingResponse

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.router = APIRouter()
        self.router.websocket("/ws")(self.websocket_endpoint)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast_pod_failure(self, failure: PodFailureResponse):
        """Broadcast new pod failure to all connected clients"""
        if self.active_connections:
            message = {
                "type": "pod_failure",
                "data": failure.dict()
            }

            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(json.dumps(message, default=str))
                except Exception as e:
                    logger.warning(f"Failed to send message to WebSocket: {e}")
                    disconnected.append(connection)

            # Remove disconnected connections
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    async def broadcast_pod_deleted(self, namespace: str, pod_name: str):
        """Broadcast pod deletion to all connected clients"""
        if self.active_connections:
            message = {
                "type": "pod_deleted",
                "data": {"namespace": namespace, "pod_name": pod_name}
            }

            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(json.dumps(message, default=str))
                except Exception as e:
                    logger.warning(f"Failed to send deletion message to WebSocket: {e}")
                    disconnected.append(connection)

            # Remove disconnected connections
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    async def broadcast_security_finding(self, finding: SecurityFindingResponse):
        """Broadcast new security finding to all connected clients"""
        if self.active_connections:
            message = {
                "type": "security_finding",
                "data": finding.dict()
            }

            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(json.dumps(message, default=str))
                except Exception as e:
                    logger.warning(f"Failed to send security finding to WebSocket: {e}")
                    disconnected.append(connection)

            # Remove disconnected connections
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    async def broadcast_cve_finding(self, finding: CVEFindingResponse):
        """Broadcast new CVE finding to all connected clients"""
        if self.active_connections:
            message = {
                "type": "cve_finding",
                "data": finding.dict()
            }

            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(json.dumps(message, default=str))
                except Exception as e:
                    logger.warning(f"Failed to send CVE finding to WebSocket: {e}")
                    disconnected.append(connection)

            # Remove disconnected connections
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    async def websocket_endpoint(self, websocket: WebSocket):
        await self.connect(websocket)
        try:
            while True:
                # Keep connection alive
                await websocket.receive_text()
        except WebSocketDisconnect:
            self.disconnect(websocket)
