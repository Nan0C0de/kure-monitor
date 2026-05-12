"""Tests for WebSocketClient reconnect behaviour and heartbeat wiring."""

import asyncio
import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch

from clients.websocket_client import WebSocketClient


def _make_ws_mock(messages=None):
    """Build an async-iterable mock WS that yields the given messages then stops."""
    messages = messages or []
    ws = MagicMock()
    ws.closed = False
    ws.close = AsyncMock()

    async def _aiter(self):
        for m in messages:
            yield m

    ws.__aiter__ = _aiter
    return ws


class TestWebSocketClientReconnect:
    @pytest.fixture
    def client(self):
        c = WebSocketClient("http://test-backend:8000")
        # Make backoff deterministic by zeroing jitter.
        c._compute_backoff = lambda attempt: float(
            min(c._reconnect_max_seconds, 1 * (2**attempt))
        )
        return c

    @pytest.mark.asyncio
    async def test_exponential_backoff_on_repeated_failures(self, client):
        """After 3 failed connect attempts, sleeps should follow 1, 2, 4 seconds."""
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 3:
                client._running = False

        client._sleep = fake_sleep

        # ws_connect always raises a ClientError -> triggers reconnect path.
        fake_session = MagicMock()
        fake_session.closed = False
        fake_session.close = AsyncMock()
        fake_session.ws_connect = AsyncMock(side_effect=aiohttp.ClientError("boom"))

        with patch(
            "clients.websocket_client.aiohttp.ClientSession",
            return_value=fake_session,
        ):
            await client.connect()

        assert sleeps == [1.0, 2.0, 4.0]
        # attempt counter advanced once per failure.
        assert client._reconnect_attempt == 3

    @pytest.mark.asyncio
    async def test_heartbeat_passed_to_ws_connect(self, client):
        """heartbeat kwarg must be forwarded to ws_connect."""
        ws = _make_ws_mock(messages=[])

        async def fake_sleep(_):
            client._running = False

        client._sleep = fake_sleep

        fake_session = MagicMock()
        fake_session.closed = False
        fake_session.close = AsyncMock()
        fake_session.ws_connect = AsyncMock(return_value=ws)

        with patch(
            "clients.websocket_client.aiohttp.ClientSession",
            return_value=fake_session,
        ):
            await client.connect()

        assert fake_session.ws_connect.await_count >= 1
        _, kwargs = fake_session.ws_connect.call_args
        assert kwargs.get("heartbeat") == 30

    @pytest.mark.asyncio
    async def test_reconnect_attempt_resets_after_successful_connect(self, client):
        """A real connection must zero _reconnect_attempt; next failure restarts at 1s."""
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            # Stop after we've seen the post-success sleep.
            if len(sleeps) >= 3:
                client._running = False

        client._sleep = fake_sleep

        ws_ok = _make_ws_mock(messages=[])  # empty -> exits iter immediately
        # First two attempts fail, third succeeds (and ws iter ends -> disconnect),
        # fourth fails again — the sleep after the post-success disconnect should
        # be 1s, proving the counter reset.
        fake_session = MagicMock()
        fake_session.closed = False
        fake_session.close = AsyncMock()
        fake_session.ws_connect = AsyncMock(
            side_effect=[
                aiohttp.ClientError("fail1"),
                aiohttp.ClientError("fail2"),
                ws_ok,
                aiohttp.ClientError("fail3"),
            ]
        )

        with patch(
            "clients.websocket_client.aiohttp.ClientSession",
            return_value=fake_session,
        ):
            await client.connect()

        # Sleeps: after fail1 -> 1 (attempt 0), after fail2 -> 2 (attempt 1),
        # after success-then-iter-ends -> 1 (counter reset to 0),
        assert sleeps[0] == 1.0
        assert sleeps[1] == 2.0
        assert sleeps[2] == 1.0
