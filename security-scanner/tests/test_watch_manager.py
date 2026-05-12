"""Tests for WatchManager liveness/shutdown and the _wait_for_backend probe.

Covers:
 - Producer thread that dies with a non-ApiException is detected by the
   liveness loop, logged, and restarted on the same executor.
 - shutdown() called while watches are active does not raise; executors
   are marked shut down.
 - _wait_for_backend logs the originating cause when retries are exhausted
   (the previous "Backend not ready" message swallowed it).
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock, patch

import pytest

from services.backend_client import BackendClient, BackendError
from services.security_scanner import SecurityScanner
from services.watch_manager import WatchManager, _ProducerRegistration


def _make_scanner():
    with patch("services.security_scanner.BackendClient"), patch(
        "services.security_scanner.WebSocketClient"
    ):
        scanner = SecurityScanner()
    scanner.backend_client = AsyncMock()
    return scanner


class TestWatchManagerLiveness:
    @pytest.mark.asyncio
    async def test_dead_producer_is_logged_and_restarted(self, caplog):
        """Producer thread raises non-ApiException; liveness loop must
        detect it, log ERROR, and resubmit the watch on the same executor."""
        scanner = _make_scanner()
        wm = WatchManager(scanner)
        wm.LIVENESS_CHECK_INTERVAL = 0.05

        call_count = {"n": 0}

        def fake_sync_watch(callback):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("synthetic producer crash")
            # On restart, just block briefly so the future stays running.
            import time as _time

            _time.sleep(0.5)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-watch")
        future = executor.submit(fake_sync_watch, lambda ev: None)
        reg = _ProducerRegistration(
            resource_type="TestRes",
            thread_prefix="test-watch",
            executor=executor,
            sync_watch=fake_sync_watch,
            on_event=lambda ev: None,
            future=future,
        )
        wm._executors.append(executor)
        wm._producers.append(reg)

        # Wait for the original future to fail (don't re-raise).
        for _ in range(50):
            if future.done():
                break
            await asyncio.sleep(0.02)
        assert future.done()

        with caplog.at_level(logging.ERROR):
            liveness = asyncio.create_task(wm.liveness_check_loop())
            # Give the loop enough time to observe and restart.
            await asyncio.sleep(0.2)
            wm._shutdown = True
            liveness.cancel()
            try:
                await liveness
            except asyncio.CancelledError:
                pass

        try:
            assert call_count["n"] >= 2, "producer should have been restarted"
            assert any(
                "died with exception" in rec.message for rec in caplog.records
            ), "expected ERROR log mentioning the producer crash"
        finally:
            await wm.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_while_active_does_not_raise(self):
        """shutdown() while a producer is actively blocking must succeed and
        mark every tracked executor as shut down."""
        scanner = _make_scanner()
        wm = WatchManager(scanner)

        def blocking_watch(callback):
            import time as _time

            _time.sleep(5)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="t-blocking")
        future = executor.submit(blocking_watch, lambda ev: None)
        wm._executors.append(executor)
        wm._producers.append(
            _ProducerRegistration(
                resource_type="Blocking",
                thread_prefix="t-blocking",
                executor=executor,
                sync_watch=blocking_watch,
                on_event=lambda ev: None,
                future=future,
            )
        )

        # Must not raise.
        await wm.shutdown()

        # `_shutdown` flips True; executor cannot accept new work.
        assert wm._shutdown is True
        with pytest.raises(RuntimeError):
            executor.submit(lambda: None)

    @pytest.mark.asyncio
    async def test_consumer_does_not_deadlock_after_producer_restart(self):
        """If the producer thread dies and is restarted, the asyncio consumer
        side (event_queue.get()) should not deadlock — events from the
        restarted producer still reach the consumer via the same on_event."""
        scanner = _make_scanner()
        wm = WatchManager(scanner)
        wm.LIVENESS_CHECK_INTERVAL = 0.05

        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        attempts = {"n": 0}

        def producer(callback):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("first attempt crashes")
            callback({"type": "ADDED", "value": attempts["n"]})
            # Stay alive so future doesn't complete again.
            import time as _time

            _time.sleep(2)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="t-restart")
        future = executor.submit(producer, on_event)
        wm._executors.append(executor)
        wm._producers.append(
            _ProducerRegistration(
                resource_type="RestartRes",
                thread_prefix="t-restart",
                executor=executor,
                sync_watch=producer,
                on_event=on_event,
                future=future,
            )
        )

        liveness = asyncio.create_task(wm.liveness_check_loop())
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=2.0)
            assert event["type"] == "ADDED"
        finally:
            wm._shutdown = True
            liveness.cancel()
            try:
                await liveness
            except asyncio.CancelledError:
                pass
            await wm.shutdown()


class TestWaitForBackend:
    @pytest.mark.asyncio
    async def test_logs_original_cause_on_timeout(self, caplog):
        """When the backend never becomes ready, the ERROR log must include
        the underlying cause, not just a generic 'Backend not ready'."""
        scanner = _make_scanner()
        scanner.backend_client.health_check = AsyncMock(
            side_effect=BackendError("connect refused: tcp 127.0.0.1:8000")
        )

        with caplog.at_level(logging.ERROR):
            ok = await scanner._wait_for_backend(max_retries=2, retry_interval=0.01)

        assert ok is False
        joined = " | ".join(rec.getMessage() for rec in caplog.records)
        assert "Backend not ready after" in joined
        assert "connect refused" in joined

    @pytest.mark.asyncio
    async def test_returns_true_when_health_check_passes(self):
        scanner = _make_scanner()
        scanner.backend_client.health_check = AsyncMock(return_value=None)
        scanner.exclusion_mgr.refresh_excluded_namespaces = AsyncMock(return_value=True)
        scanner.exclusion_mgr.refresh_excluded_rules = AsyncMock(return_value=True)

        ok = await scanner._wait_for_backend(max_retries=1, retry_interval=0.01)
        assert ok is True
        scanner.backend_client.health_check.assert_awaited()
        scanner.exclusion_mgr.refresh_excluded_namespaces.assert_awaited()
        scanner.exclusion_mgr.refresh_excluded_rules.assert_awaited()


class TestBackendHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_raises_backend_error_with_chain(self):
        """The explicit probe must surface the original cause via __cause__
        so callers (and logs) can see *why* the backend isn't ready."""
        client = BackendClient("http://example.invalid")

        class _FakeSession:
            closed = False

            def get(self, *a, **kw):
                raise asyncio.TimeoutError()

        async def _fake_get_session():
            return _FakeSession()

        client._get_session = _fake_get_session  # type: ignore[assignment]

        with pytest.raises(BackendError) as exc_info:
            await client.health_check()
        assert "timed out" in str(exc_info.value).lower()
        assert isinstance(exc_info.value.__cause__, asyncio.TimeoutError)
