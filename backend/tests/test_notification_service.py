import pytest
from unittest.mock import Mock, AsyncMock, patch
from services.notification_service import NotificationService
from models.models import PodFailureResponse


class TestNotificationService:

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        db = AsyncMock()
        db.get_enabled_notification_settings = AsyncMock(return_value=[])
        return db

    @pytest.fixture
    def notification_service(self, mock_db):
        """Create NotificationService instance with mocked db"""
        return NotificationService(mock_db)

    @pytest.fixture
    def mock_failure(self):
        """Create mock pod failure response"""
        return PodFailureResponse(
            id=1,
            pod_name="test-pod",
            namespace="default",
            node_name="test-node",
            phase="Pending",
            creation_timestamp="2025-01-01T00:00:00Z",
            failure_reason="ImagePullBackOff",
            failure_message="Failed to pull image",
            container_statuses=[],
            events=[],
            logs="",
            manifest="",
            solution="Test solution",
            timestamp="2025-01-01T00:00:00Z",
            dismissed=False,
        )

    @pytest.mark.asyncio
    async def test_discord_not_supported(self, notification_service, mock_failure):
        """Test that Discord provider logs a warning (not supported)"""
        config = {"webhook_url": "https://discord.com/api/webhooks/test"}

        with patch("services.notification_service.logger") as mock_logger:
            await notification_service._send_notification(
                "discord", config, mock_failure
            )
            mock_logger.warning.assert_called_once()
            call_args = str(mock_logger.warning.call_args)
            assert "discord" in call_args.lower()

    @pytest.mark.asyncio
    async def test_unknown_provider_logged(self, notification_service, mock_failure):
        """Test that unknown provider is logged as warning"""
        config = {"webhook_url": "https://example.com"}

        with patch("services.notification_service.logger") as mock_logger:
            await notification_service._send_notification(
                "unknown_provider", config, mock_failure
            )
            mock_logger.warning.assert_called_once()
            assert "unknown_provider" in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_send_slack_notification(self, notification_service, mock_failure):
        """Test sending Slack notification"""
        config = {
            "webhook_url": "https://hooks.slack.com/services/test",
            "channel": "#alerts",
        }

        mock_response = AsyncMock()
        mock_response.status = 200

        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = Mock(return_value=mock_post_cm)

        with patch.object(
            notification_service,
            "_get_session",
            new=AsyncMock(return_value=mock_session_instance),
        ):
            # Should not raise
            await notification_service._send_slack(config, mock_failure)

    @pytest.mark.asyncio
    async def test_send_teams_notification(self, notification_service, mock_failure):
        """Test sending Microsoft Teams notification via Power Automate Workflows"""
        config = {
            "webhook_url": "https://prod-00.westus.logic.azure.com:443/workflows/test"
        }

        # Workflows webhooks return 202 Accepted on success
        mock_response = AsyncMock()
        mock_response.status = 202

        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = Mock(return_value=mock_post_cm)

        with patch.object(
            notification_service,
            "_get_session",
            new=AsyncMock(return_value=mock_session_instance),
        ):
            # Should not raise
            await notification_service._send_teams(config, mock_failure)

    @pytest.mark.asyncio
    async def test_send_pod_failure_notification(
        self, notification_service, mock_failure, mock_db
    ):
        """Test sending pod failure notification to all enabled providers"""
        # Setup mock settings
        mock_setting = Mock()
        mock_setting.provider = "slack"
        mock_setting.config = {"webhook_url": "https://hooks.slack.com/test"}
        mock_db.get_enabled_notification_settings.return_value = [mock_setting]

        with patch.object(
            notification_service, "_send_notification", new_callable=AsyncMock
        ) as mock_send:
            await notification_service.send_pod_failure_notification(mock_failure)
            mock_send.assert_called_once_with(
                provider="slack",
                config={"webhook_url": "https://hooks.slack.com/test"},
                failure=mock_failure,
            )

    @pytest.mark.asyncio
    async def test_routing_slack_interactive(self, notification_service, mock_failure):
        """Test that mode=app routes Slack to _send_slack_interactive"""
        config = {"mode": "app", "bot_token": "xoxb-test", "channel_id": "C0123"}
        with patch.object(notification_service, "_send_slack_interactive", new_callable=AsyncMock) as mock_interact, \
             patch.object(notification_service, "_send_slack", new_callable=AsyncMock) as mock_webhook:
            await notification_service._send_notification("slack", config, mock_failure)
            mock_interact.assert_called_once_with(config, mock_failure)
            mock_webhook.assert_not_called()

    @pytest.mark.asyncio
    async def test_routing_teams_interactive(self, notification_service, mock_failure):
        """Test that mode=app routes Teams to _send_teams_interactive"""
        config = {"mode": "app", "webhook_url": "http://test", "callback_url": "http://kure"}
        with patch.object(notification_service, "_send_teams_interactive", new_callable=AsyncMock) as mock_interact, \
             patch.object(notification_service, "_send_teams", new_callable=AsyncMock) as mock_webhook:
            await notification_service._send_notification("teams", config, mock_failure)
            mock_interact.assert_called_once_with(config, mock_failure)
            mock_webhook.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_slack_interactive_success(self, notification_service, mock_failure):
        """Test sending interactive Slack notification and saving ChatOps record"""
        config = {"mode": "app", "bot_token": "xoxb-test", "channel_id": "C0123"}
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ok": True, "channel": "C0123", "ts": "1600000000.000000"})
        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.post = Mock(return_value=mock_post_cm)

        with patch.object(notification_service, "_get_session", new=AsyncMock(return_value=mock_session)):
            await notification_service._send_slack_interactive(config, mock_failure)
            notification_service.db.save_chatops_message.assert_called_once_with(
                pod_failure_id=mock_failure.id,
                provider="slack",
                channel_id="C0123",
                message_id="1600000000.000000",
            )

    @pytest.mark.asyncio
    async def test_send_teams_interactive_success(self, notification_service, mock_failure):
        """Test sending interactive Teams notification with Action.Http"""
        config = {"mode": "app", "webhook_url": "https://test.logic.azure.com", "callback_url": "https://kure.example.com"}
        mock_resp = AsyncMock()
        mock_resp.status = 202
        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.post = Mock(return_value=mock_post_cm)

        with patch.object(notification_service, "_get_session", new=AsyncMock(return_value=mock_session)):
            await notification_service._send_teams_interactive(config, mock_failure)
            assert mock_session.post.call_count == 1
            call_kwargs = mock_session.post.call_args[1]
            payload = call_kwargs["json"]
            assert payload["attachments"][0]["content"]["actions"][0]["type"] == "Action.Http"

    @pytest.mark.asyncio
    async def test_notification_deduplication(self, notification_service, mock_failure, mock_db):
        """Test that repeated failure reports for the same pod within 24 hours are deduplicated in memory"""
        mock_setting = Mock()
        mock_setting.provider = "slack"
        mock_setting.config = {"webhook_url": "https://hooks.slack.com/test"}
        mock_db.get_enabled_notification_settings.return_value = [mock_setting]

        with patch.object(notification_service, "_send_notification", new_callable=AsyncMock) as mock_send:
            # First call should send notification
            await notification_service.send_pod_failure_notification(mock_failure)
            assert mock_send.call_count == 1

            # Second call immediately after should be skipped by in-memory deduplication cache
            await notification_service.send_pod_failure_notification(mock_failure)
            assert mock_send.call_count == 1

            # Resolving the pod should clear the cache so future failures notify again
            await notification_service.send_pod_resolved_notification(mock_failure.namespace, mock_failure.pod_name)
            await notification_service.send_pod_failure_notification(mock_failure)
            assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_notification_skip_existing_update(self, notification_service, mock_failure, mock_db):
        """Test that when is_new_failure is False (update to existing DB record), notification is skipped"""
        mock_setting = Mock()
        mock_setting.provider = "slack"
        mock_setting.config = {"webhook_url": "https://hooks.slack.com/test"}
        mock_db.get_enabled_notification_settings.return_value = [mock_setting]

        mock_failure.is_new_failure = False
        with patch.object(notification_service, "_send_notification", new_callable=AsyncMock) as mock_send:
            await notification_service.send_pod_failure_notification(mock_failure)
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_routing_slack_resolved_interactive(self, notification_service):
        """Test that mode=app routes Slack resolved notifications to _send_slack_resolved_interactive"""
        config = {"mode": "app", "bot_token": "xoxb-test", "channel_id": "C0123"}
        with patch.object(notification_service, "_send_slack_resolved_interactive", new_callable=AsyncMock) as mock_interact, \
             patch.object(notification_service, "_send_slack_resolved", new_callable=AsyncMock) as mock_webhook:
            await notification_service._send_resolved_notification("slack", config, "default", "my-pod")
            mock_interact.assert_called_once_with(config, "default", "my-pod")
            mock_webhook.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_slack_resolved_interactive_success(self, notification_service, mock_db):
        """Test sending interactive Slack resolved notification with thread_ts broadcast"""
        config = {"mode": "app", "bot_token": "xoxb-test", "channel_id": "C0123"}
        mock_failure_obj = Mock()
        mock_failure_obj.id = 42
        mock_db.get_pod_failures.return_value = [mock_failure_obj]
        mock_db.get_chatops_message.return_value = {"message_id": "1600000000.000000"}

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ok": True, "channel": "C0123", "ts": "1600000005.000000"})
        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.post = Mock(return_value=mock_post_cm)

        with patch.object(notification_service, "_get_session", new=AsyncMock(return_value=mock_session)):
            await notification_service._send_slack_resolved_interactive(config, "default", "my-pod")
            assert mock_session.post.call_count == 1
            call_kwargs = mock_session.post.call_args[1]
            payload = call_kwargs["json"]
            assert payload["channel"] == "C0123"
            assert payload["thread_ts"] == "1600000000.000000"
            assert payload["reply_broadcast"] is True
            assert "🟢 Pod Recovered & Resolved" in payload["blocks"][0]["text"]["text"]
