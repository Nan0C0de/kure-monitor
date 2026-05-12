import asyncio
import aiohttp
import json
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _sanitize_url(url: str) -> str:
    """Strip query string from a URL for safe logging (never leak tokens)."""
    if not url:
        return url
    return url.split("?", 1)[0]


class WebSocketClient:
    def __init__(self, backend_url: str):
        # Convert HTTP URL to WebSocket URL
        ws_url = (
            backend_url.replace("http://", "ws://")
            .replace("https://", "wss://")
            .rstrip("/")
        )
        token = os.environ.get("SERVICE_TOKEN")
        if not token:
            logger.error(
                "SERVICE_TOKEN environment variable is not set. "
                "WebSocket connection will be rejected with 401 if the "
                "backend requires authentication."
            )
        # Send the service token via the X-Service-Token request header
        # rather than a `?token=` query string so it never lands in proxy or
        # access logs. Default true; set SCANNER_AUTH_VIA_HEADER=false to fall
        # back to the legacy query-param form for compatibility with old
        # backend builds.
        self._auth_via_header = os.environ.get(
            "SCANNER_AUTH_VIA_HEADER", "true"
        ).lower() in ("1", "true", "yes")
        self._token = token
        self._base_ws_url = f"{ws_url}/ws"
        if self._auth_via_header or not token:
            self.ws_url = self._base_ws_url
        else:
            self.ws_url = f"{self._base_ws_url}?token={token}"
        self.on_namespace_change: Optional[Callable] = None
        self.on_rule_change: Optional[Callable] = None
        self.on_registry_change: Optional[Callable] = None
        self.on_rescan_request: Optional[Callable] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False

    def set_namespace_change_handler(self, handler: Callable):
        """Set the callback for namespace exclusion changes"""
        self.on_namespace_change = handler

    def set_rule_change_handler(self, handler: Callable):
        """Set the callback for rule exclusion changes"""
        self.on_rule_change = handler

    def set_registry_change_handler(self, handler: Callable):
        """Set the callback for trusted registry changes"""
        self.on_registry_change = handler

    def set_rescan_request_handler(self, handler: Callable):
        """Set the callback for manual rescan requests"""
        self.on_rescan_request = handler

    async def _send_keepalive(self):
        """Send periodic keepalive pings to keep connection alive"""
        while self._running and self._ws and not self._ws.closed:
            try:
                await asyncio.sleep(30)  # Send ping every 30 seconds
                if self._ws and not self._ws.closed:
                    await self._ws.ping()
                    logger.debug("Sent WebSocket keepalive ping")
            except Exception as e:
                logger.warning(f"Failed to send keepalive ping: {e}")
                break

    async def connect(self):
        """Connect to the backend WebSocket"""
        self._running = True
        while self._running:
            try:
                # Never log the full URL — it may contain ?token=... when
                # SCANNER_AUTH_VIA_HEADER is unset (legacy backend mode).
                logger.info(f"Connecting to WebSocket: {_sanitize_url(self.ws_url)}")
                self._session = aiohttp.ClientSession()
                ws_headers = {}
                if self._auth_via_header and self._token:
                    ws_headers["X-Service-Token"] = self._token
                self._ws = await self._session.ws_connect(
                    self.ws_url, heartbeat=30, headers=ws_headers or None
                )
                logger.info("WebSocket connected successfully")

                # Start keepalive task
                keepalive_task = asyncio.create_task(self._send_keepalive())

                # Listen for messages
                try:
                    async for msg in self._ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            logger.debug(
                                f"Received WebSocket message: {msg.data[:100]}..."
                            )
                            await self._handle_message(msg.data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket error: {self._ws.exception()}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            logger.info("WebSocket closed by server")
                            break
                finally:
                    keepalive_task.cancel()

            except aiohttp.ClientError as e:
                logger.warning(f"WebSocket connection error: {e}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                if self._session and not self._session.closed:
                    await self._session.close()

            if self._running:
                logger.info("Reconnecting to WebSocket in 5 seconds...")
                await asyncio.sleep(5)

    async def _handle_message(self, data: str):
        """Handle incoming WebSocket message"""
        try:
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "namespace_exclusion_change":
                namespace = message["data"].get("namespace")
                action = message["data"].get("action")
                logger.info(
                    f"Received namespace exclusion change: {namespace} -> {action}"
                )

                if self.on_namespace_change:
                    await self.on_namespace_change(namespace, action)

            elif msg_type == "rule_exclusion_change":
                rule_title = message["data"].get("rule_title")
                namespace = message["data"].get("namespace")
                action = message["data"].get("action")
                scope = f"namespace '{namespace}'" if namespace else "global"
                logger.info(
                    f"Received rule exclusion change: {rule_title} ({scope}) -> {action}"
                )

                if self.on_rule_change:
                    await self.on_rule_change(rule_title, action, namespace)

            elif msg_type == "trusted_registry_change":
                registry = message["data"].get("registry")
                action = message["data"].get("action")
                logger.info(f"Received trusted registry change: {registry} -> {action}")

                if self.on_registry_change:
                    await self.on_registry_change(registry, action)

            elif msg_type == "security_rescan_request":
                logger.info("Received manual security rescan request")

                if self.on_rescan_request:
                    await self.on_rescan_request()

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

    async def disconnect(self):
        """Disconnect from the WebSocket"""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
