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
            dismissed=False
        )

    @pytest.mark.asyncio
    async def test_discord_not_supported(self, notification_service, mock_failure):
        """Test that Discord provider logs a warning (not supported)"""
        config = {'webhook_url': 'https://discord.com/api/webhooks/test'}

        with patch('services.notification_service.logger') as mock_logger:
            await notification_service._send_notification('discord', config, mock_failure)
            mock_logger.warning.assert_called_once()
            call_args = str(mock_logger.warning.call_args)
            assert 'discord' in call_args.lower()

    @pytest.mark.asyncio
    async def test_unknown_provider_logged(self, notification_service, mock_failure):
        """Test that unknown provider is logged as warning"""
        config = {'webhook_url': 'https://example.com'}

        with patch('services.notification_service.logger') as mock_logger:
            await notification_service._send_notification('unknown_provider', config, mock_failure)
            mock_logger.warning.assert_called_once()
            assert 'unknown_provider' in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_send_slack_notification(self, notification_service, mock_failure):
        """Test sending Slack notification"""
        config = {
            'webhook_url': 'https://hooks.slack.com/services/test',
            'channel': '#alerts'
        }

        with patch('services.notification_service.aiohttp.ClientSession') as mock_session:
            # Create proper async context manager mocks
            mock_response = AsyncMock()
            mock_response.status = 200

            mock_post_cm = AsyncMock()
            mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_cm.__aexit__ = AsyncMock(return_value=None)

            mock_session_instance = AsyncMock()
            mock_session_instance.post = Mock(return_value=mock_post_cm)

            mock_session_cm = AsyncMock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value = mock_session_cm

            # Should not raise
            await notification_service._send_slack(config, mock_failure)

    @pytest.mark.asyncio
    async def test_send_teams_notification(self, notification_service, mock_failure):
        """Test sending Microsoft Teams notification via Power Automate Workflows"""
        config = {
            'webhook_url': 'https://prod-00.westus.logic.azure.com:443/workflows/test'
        }

        with patch('services.notification_service.aiohttp.ClientSession') as mock_session:
            # Create proper async context manager mocks
            # Workflows webhooks return 202 Accepted on success
            mock_response = AsyncMock()
            mock_response.status = 202

            mock_post_cm = AsyncMock()
            mock_post_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_cm.__aexit__ = AsyncMock(return_value=None)

            mock_session_instance = AsyncMock()
            mock_session_instance.post = Mock(return_value=mock_post_cm)

            mock_session_cm = AsyncMock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.return_value = mock_session_cm

            # Should not raise
            await notification_service._send_teams(config, mock_failure)

    @pytest.mark.asyncio
    async def test_send_pod_failure_notification(self, notification_service, mock_failure, mock_db):
        """Test sending pod failure notification to all enabled providers"""
        # Setup mock settings
        mock_setting = Mock()
        mock_setting.provider = 'slack'
        mock_setting.config = {'webhook_url': 'https://hooks.slack.com/test'}
        mock_db.get_enabled_notification_settings.return_value = [mock_setting]

        with patch.object(notification_service, '_send_notification', new_callable=AsyncMock) as mock_send:
            await notification_service.send_pod_failure_notification(mock_failure)
            mock_send.assert_called_once_with(
                provider='slack',
                config={'webhook_url': 'https://hooks.slack.com/test'},
                failure=mock_failure
            )
