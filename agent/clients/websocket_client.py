import asyncio
import aiohttp
import json
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class WebSocketClient:
    def __init__(self, backend_url: str):
        # Convert HTTP URL to WebSocket URL
        ws_url = backend_url.replace('http://', 'ws://').replace('https://', 'wss://').rstrip('/')
        token = os.environ.get("AUTH_API_KEY")
        self.ws_url = f"{ws_url}/ws?token={token}" if token else f"{ws_url}/ws"
        self.on_namespace_change: Optional[Callable] = None
        self.on_pod_exclusion_change: Optional[Callable] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False

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
                logger.info(f"Connecting to WebSocket: {self.ws_url}")
                self._session = aiohttp.ClientSession()
                self._ws = await self._session.ws_connect(self.ws_url)
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
                logger.info("Reconnecting to WebSocket in 5 seconds...")
                await asyncio.sleep(5)

    async def _handle_message(self, data: str):
        """Handle incoming WebSocket message"""
        try:
            message = json.loads(data)
            msg_type = message.get('type')

            if msg_type == 'namespace_exclusion_change':
                namespace = message['data'].get('namespace')
                action = message['data'].get('action')
                logger.info(f"Received namespace exclusion change: {namespace} -> {action}")

                if self.on_namespace_change:
                    await self.on_namespace_change(namespace, action)

            elif msg_type == 'pod_exclusion_change':
                pod_name = message['data'].get('pod_name')
                action = message['data'].get('action')
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
