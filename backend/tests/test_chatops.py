import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, Mock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_chatops import (
    create_chatops_router,
    _verify_slack_signature,
    _truncate_for_slack,
    _truncate_for_teams,
    _process_slack_troubleshoot,
    _process_teams_troubleshoot,
)
from models.models import PodFailureResponse, NotificationSettingResponse


@pytest.fixture
def mock_deps():
    deps = Mock()
    deps.db = AsyncMock()
    deps.solution_engine = AsyncMock()
    deps.notification_service = AsyncMock()
    return deps


@pytest.fixture
def client(mock_deps):
    app = FastAPI()
    router = create_chatops_router(mock_deps)
    app.include_router(router, prefix="/api")
    return TestClient(app)


class TestChatOpsFormatting:
    def test_truncate_for_slack_short(self):
        text = "short text"
        assert _truncate_for_slack(text) == "short text"

    def test_truncate_for_slack_long(self):
        text = "a" * 3500
        truncated = _truncate_for_slack(text, max_len=3000)
        assert len(truncated) <= 3000
        assert "truncated" in truncated

    def test_truncate_for_teams_short(self):
        text = "short text"
        assert _truncate_for_teams(text) == "short text"

    def test_truncate_for_teams_long(self):
        text = "a" * 12000
        truncated = _truncate_for_teams(text, max_len=10000)
        assert len(truncated) <= 10000
        assert "truncated" in truncated


class TestSlackSignatureVerification:
    @pytest.mark.asyncio
    async def test_no_secret_configured_skips_verification(self):
        db = AsyncMock()
        db.get_notification_setting = AsyncMock(return_value=None)
        request = Mock()
        # Should not raise
        await _verify_slack_signature(request, b"body", db)

    @pytest.mark.asyncio
    async def test_valid_signature(self):
        secret = "test_secret"
        db = AsyncMock()
        db.get_notification_setting = AsyncMock(
            return_value=NotificationSettingResponse(
                provider="slack", enabled=True, config={"signing_secret": secret}
            )
        )

        ts = str(int(time.time()))
        body = b"payload=test"
        sig_basestring = f"v0:{ts}:{body.decode('utf-8')}"
        computed = "v0=" + hmac.new(
            secret.encode(), sig_basestring.encode(), hashlib.sha256
        ).hexdigest()

        request = Mock()
        request.headers = {
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": computed,
        }

        # Should not raise
        await _verify_slack_signature(request, body, db)

    @pytest.mark.asyncio
    async def test_invalid_signature_raises_403(self):
        secret = "test_secret"
        db = AsyncMock()
        db.get_notification_setting = AsyncMock(
            return_value=NotificationSettingResponse(
                provider="slack", enabled=True, config={"signing_secret": secret}
            )
        )

        ts = str(int(time.time()))
        request = Mock()
        request.headers = {
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": "v0=invalid_signature",
        }

        with pytest.raises(Exception) as exc_info:
            await _verify_slack_signature(request, b"payload=test", db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_timestamp_raises_403(self):
        secret = "test_secret"
        db = AsyncMock()
        db.get_notification_setting = AsyncMock(
            return_value=NotificationSettingResponse(
                provider="slack", enabled=True, config={"signing_secret": secret}
            )
        )

        old_ts = str(int(time.time()) - 400)
        request = Mock()
        request.headers = {
            "X-Slack-Request-Timestamp": old_ts,
            "X-Slack-Signature": "v0=anything",
        }

        with pytest.raises(Exception) as exc_info:
            await _verify_slack_signature(request, b"payload=test", db)
        assert exc_info.value.status_code == 403


class TestChatOpsEndpoints:
    @patch("api.routes_chatops._process_slack_troubleshoot", return_value=None)
    @patch("api.routes_chatops._verify_slack_signature", new_callable=AsyncMock)
    @patch("api.routes_chatops.asyncio.create_task")
    def test_slack_interaction_endpoint_success(
        self, mock_create_task, mock_verify_sig, mock_process, client
    ):
        button_value = json.dumps(
            {
                "pod_failure_id": 123,
                "namespace": "default",
                "pod_name": "my-pod",
                "failure_reason": "CrashLoopBackOff",
            }
        )
        payload = {
            "actions": [{"action_id": "kure_troubleshoot", "value": button_value}],
            "channel": {"id": "C0123"},
            "message": {"ts": "1600000000.000000"},
            "user": {"username": "tester"},
            "response_url": "https://hooks.slack.com/actions/test",
        }

        response = client.post(
            "/api/chatops/slack/interact",
            data={"payload": json.dumps(payload)},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_create_task.assert_called_once()
        mock_process.assert_called_once()

    @patch("api.routes_chatops._verify_slack_signature", new_callable=AsyncMock)
    def test_slack_interaction_ignore_unknown_action(self, mock_verify_sig, client):
        payload = {
            "actions": [{"action_id": "other_action", "value": "{}"}],
        }
        response = client.post(
            "/api/chatops/slack/interact",
            data={"payload": json.dumps(payload)},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @patch("api.routes_chatops._process_teams_troubleshoot", return_value=None)
    @patch("api.routes_chatops.asyncio.create_task")
    def test_teams_interaction_endpoint_success(
        self, mock_create_task, mock_process, client
    ):
        body = {
            "pod_failure_id": 456,
            "webhook_url": "https://prod-xx.logic.azure.com/test",
            "namespace": "prod",
            "pod_name": "api-pod",
        }
        response = client.post("/api/chatops/teams/interact", json=body)
        assert response.status_code == 200
        assert response.json()["status"] == "processing"
        mock_create_task.assert_called_once()
        mock_process.assert_called_once()

    def test_teams_interaction_missing_fields(self, client):
        response = client.post(
            "/api/chatops/teams/interact", json={"pod_failure_id": 123}
        )
        assert response.status_code == 400

    @patch("api.routes_chatops._verify_slack_signature", new_callable=AsyncMock)
    def test_slack_events_url_verification(self, mock_verify_sig, client):
        payload = {
            "type": "url_verification",
            "challenge": "test_challenge_123"
        }
        resp = client.post(
            "/api/chatops/slack/events",
            json=payload,
            headers={
                "X-Slack-Request-Timestamp": "1600000000",
                "X-Slack-Signature": "v0=dummy",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"challenge": "test_challenge_123"}

    @patch("api.routes_chatops._verify_slack_signature", new_callable=AsyncMock)
    @patch("api.routes_chatops._process_slack_chat_reply", new_callable=AsyncMock)
    def test_slack_events_callback_thread_reply(self, mock_reply, mock_verify_sig, client, mock_deps):
        mock_deps.db.get_chatops_message_by_message_id = AsyncMock(
            return_value={"pod_failure_id": 42, "provider": "slack"}
        )
        payload = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U12345",
                "text": "How do I fix this?",
                "thread_ts": "1600000000.000000",
                "channel": "C012345",
            }
        }
        resp = client.post(
            "/api/chatops/slack/events",
            json=payload,
            headers={
                "X-Slack-Request-Timestamp": "1600000000",
                "X-Slack-Signature": "v0=dummy",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_deps.db.get_chatops_message_by_message_id.assert_called_once_with(
            provider="slack", message_id="1600000000.000000"
        )

    @patch("api.routes_chatops._process_slack_troubleshoot", return_value=None)
    @patch("api.routes_chatops._verify_slack_signature", new_callable=AsyncMock)
    def test_slack_events_endpoint_handles_interactivity_form_data(self, mock_verify_sig, mock_process, client, mock_deps):
        """Test that /api/chatops/slack/events can handle URL-encoded form data (e.g. if configured as interactivity URL)"""
        action_val = json.dumps({"pod_failure_id": 42})
        payload_json = json.dumps({
            "actions": [{"action_id": "kure_troubleshoot", "value": action_val}],
            "channel": {"id": "C0123"},
            "message": {"ts": "123456.789"},
            "user": {"username": "tester"},
            "response_url": "https://hooks.slack.com/actions/test"
        })
        form_body = f"payload={payload_json}"
        response = client.post(
            "/api/chatops/slack/events",
            content=form_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @patch("api.routes_chatops._process_slack_chat_reply", return_value=None)
    @patch("api.routes_chatops._verify_slack_signature", new_callable=AsyncMock)
    def test_slack_interact_endpoint_handles_event_callbacks_json(self, mock_verify_sig, mock_reply, client, mock_deps):
        """Test that /api/chatops/slack/interact can handle raw JSON event callbacks (e.g. if configured as events URL)"""
        mock_deps.db.get_chatops_message_by_message_id.return_value = {"pod_failure_id": 42}
        payload = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "thread_ts": "123456.789",
                "channel": "C0123",
                "text": "What is the memory limit?",
                "user": "U123"
            }
        }
        response = client.post(
            "/api/chatops/slack/interact",
            json=payload
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}


class TestBackgroundProcessing:
    @pytest.mark.asyncio
    async def test_process_slack_troubleshoot_success(self):
        db = AsyncMock()
        solution_engine = AsyncMock()
        notif_service = AsyncMock()

        db.get_notification_setting = AsyncMock(
            return_value=NotificationSettingResponse(
                provider="slack", enabled=True, config={"bot_token": "xoxb-test"}
            )
        )
        pod = PodFailureResponse(
            id=10,
            pod_name="api",
            namespace="prod",
            node_name="node1",
            phase="Failed",
            creation_timestamp="2025-01-01T00:00:00Z",
            failure_reason="CrashLoopBackOff",
            failure_message="error",
            container_statuses=[],
            events=[],
            logs="",
            manifest="",
            solution="Quick fix",
            timestamp="2025-01-01T00:00:00Z",
        )
        db.get_pod_failure_by_id = AsyncMock(return_value=pod)
        db.get_pod_failure_logs = AsyncMock(
            return_value=[{"container_name": "api", "source": "previous", "logs": "NPE"}]
        )
        solution_engine.get_log_aware_solution = AsyncMock(
            return_value="Log-aware fix details"
        )

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ok": True, "ts": "1600000000.000001"})

        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = Mock(return_value=mock_post_cm)
        notif_service._get_session = AsyncMock(return_value=mock_session)

        await _process_slack_troubleshoot(
            db=db,
            solution_engine=solution_engine,
            notification_service=notif_service,
            pod_failure_id=10,
            channel_id="C01",
            message_ts="1600000000.000000",
            user_name="tester",
            response_url="http://example.com",
        )

        assert mock_session.post.call_count == 2
        solution_engine.get_log_aware_solution.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_slack_chat_reply_success(self):
        from api.routes_chatops import _process_slack_chat_reply
        db = AsyncMock()
        solution_engine = AsyncMock()
        notif_service = AsyncMock()

        db.get_notification_setting = AsyncMock(
            return_value=NotificationSettingResponse(
                provider="slack", enabled=True, config={"bot_token": "xoxb-test"}
            )
        )
        pod = PodFailureResponse(
            id=10,
            pod_name="api",
            namespace="prod",
            phase="Failed",
            creation_timestamp="2025-01-01T00:00:00Z",
            failure_reason="CrashLoopBackOff",
            failure_message="error",
            timestamp="2025-01-01T00:00:00Z",
        )

        db.get_pod_failure_by_id = AsyncMock(return_value=pod)
        db.get_pod_failure_logs = AsyncMock(return_value=[])
        db.get_chat_history = AsyncMock(return_value=[
            {"role": "user", "text": "<@U123>: Why did it fail?"}
        ])

        llm_provider = AsyncMock()
        llm_provider.generate_raw = AsyncMock(return_value=Mock(content="Here is why it failed..."))
        solution_engine.llm_provider = llm_provider

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ok": True, "ts": "1600000000.000001"})

        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = Mock(return_value=mock_post_cm)
        notif_service._get_session = AsyncMock(return_value=mock_session)

        await _process_slack_chat_reply(
            db=db,
            solution_engine=solution_engine,
            notification_service=notif_service,
            pod_failure_id=10,
            channel_id="C01",
            thread_ts="1600000000.000000",
            user_id="U123",
            user_text="Why did it fail?",
        )

        assert mock_session.post.call_count == 2
        llm_provider.generate_raw.assert_called_once()
        assert db.save_chat_message.call_count == 2
