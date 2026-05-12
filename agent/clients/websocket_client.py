import asyncio
import aiohttp
import json
import logging
import os
import random
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _truthy(val: Optional[str]) -> bool:
    if not val:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid integer value for %s=%r; falling back to default %d",
            name,
            raw,
            default,
        )
        return default


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
                "SERVICE_TOKEN is not set; WebSocket will connect without a token "
                "and will be rejected by the backend."
            )
        self._token = token

        # Send the service token via the X-Service-Token request header
        # rather than a `?token=` query string so it never lands in proxy or
        # access logs. Default true; can be disabled by setting
        # AGENT_AUTH_VIA_HEADER=false to fall back to the legacy query-param
        # form for compatibility with old backend builds.
        self._auth_via_header = _truthy(os.environ.get("AGENT_AUTH_VIA_HEADER", "true"))

        if self._auth_via_header:
            # Token will be sent via header; do not embed in URL.
            self.ws_url = f"{ws_url}/ws"
        else:
            self.ws_url = f"{ws_url}/ws?token={token}" if token else f"{ws_url}/ws"

        # Token-free base URL used for INFO logs so the token never leaks into
        # access/proxy logs, exception messages, or stdout captures.
        self._log_url = f"{ws_url}/ws"

        self.on_namespace_change: Optional[Callable] = None
        self.on_pod_exclusion_change: Optional[Callable] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False

        # Reconnect/backoff configuration. Overridable via env so operators can
        # tune reconnect aggressiveness without rebuilding the image.
        self._reconnect_max_seconds = _int_env("AGENT_WS_RECONNECT_MAX_SECONDS", 60)
        self._heartbeat_seconds = _int_env("AGENT_WS_HEARTBEAT_SECONDS", 30)
        self._reconnect_attempt = 0
        # Injection hook for tests — defaults to asyncio.sleep.
        self._sleep = asyncio.sleep

    def _compute_backoff(self, attempt: int) -> float:
        """Exponential backoff with additive jitter; base capped at max_seconds."""
        base = min(self._reconnect_max_seconds, 1 * (2**attempt))
        jitter = random.uniform(0, 0.5 * (2**attempt))
        return base + jitter

    def set_namespace_change_handler(self, handler: Callable):
        """Set the callback for namespace exclusion changes"""
        self.on_namespace_change = handler

    def set_pod_exclusion_change_handler(self, handler: Callable):
        """Set the callback for pod exclusion changes"""
        self.on_pod_exclusion_change = handler

    async def connect(self):
        """Connect to the backend WebSocket"""
        self._running = True
        while self._running:
            try:
                logger.info(f"Connecting to WebSocket: {self._log_url}")
                self._session = aiohttp.ClientSession()
                if self._auth_via_header and self._token:
                    headers = {"X-Service-Token": self._token}
                    self._ws = await self._session.ws_connect(
                        self.ws_url,
                        headers=headers,
                        heartbeat=self._heartbeat_seconds,
                    )
                else:
                    self._ws = await self._session.ws_connect(
                        self.ws_url,
                        heartbeat=self._heartbeat_seconds,
                    )
                # Only reset the backoff counter after a real session is
                # established — not just on ws_connect returning.
                self._reconnect_attempt = 0
                logger.info("WebSocket connected successfully")

                # Listen for messages
                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {self._ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.info("WebSocket closed by server")
                        break

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
                attempt = self._reconnect_attempt
                sleep_s = self._compute_backoff(attempt)
                # Log loudly for the first couple of attempts so transient
                # blips are visible. Drop to DEBUG during long outages, but
                # surface every 10th attempt at INFO so operators scanning
                # logs see ongoing reconnect activity.
                msg = (
                    f"WS disconnected, reconnecting in {sleep_s:.2f}s "
                    f"(attempt {attempt + 1})..."
                )
                if attempt < 2:
                    logger.info(msg)
                elif (attempt + 1) % 10 == 0:
                    logger.info(msg)
                else:
                    logger.debug(msg)
                self._reconnect_attempt = attempt + 1
                await self._sleep(sleep_s)

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

            elif msg_type == "pod_exclusion_change":
                pod_name = message["data"].get("pod_name")
                action = message["data"].get("action")
                logger.info(f"Received pod exclusion change: {pod_name} -> {action}")

                if self.on_pod_exclusion_change:
                    await self.on_pod_exclusion_change(pod_name, action)

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
