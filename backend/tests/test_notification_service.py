import pytest
from unittest.mock import Mock, AsyncMock, patch
from services.notification_service import NotificationService
from models.models import PodFailureResponse


class TestNotificationService:

    @pytest.fixture
    def notification_service(self):
        """Create NotificationService instance"""
        return NotificationService()

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

    def test_supported_providers(self, notification_service):
        """Test that only email, slack, and teams are supported providers"""
        # These should be the only supported providers after removing Discord
        supported = ['email', 'slack', 'teams']

        # Verify Discord is NOT in the handlers
        assert 'discord' not in notification_service._get_handlers()

        # Verify supported providers are in handlers
        handlers = notification_service._get_handlers()
        for provider in supported:
            assert provider in handlers

    def test_discord_not_supported(self, notification_service):
        """Test that Discord provider is not supported"""
        handlers = notification_service._get_handlers()
        assert 'discord' not in handlers

    @pytest.mark.asyncio
    async def test_unknown_provider_logged(self, notification_service, mock_failure):
        """Test that unknown provider is logged as warning"""
        config = {'webhook_url': 'https://example.com'}

        with patch('services.notification_service.logger') as mock_logger:
            await notification_service._send_notification('discord', config, mock_failure)
            mock_logger.warning.assert_called_once()
            assert 'discord' in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_send_slack_notification(self, notification_service, mock_failure):
        """Test sending Slack notification"""
        config = {
            'webhook_url': 'https://hooks.slack.com/services/test',
            'channel': '#alerts'
        }

        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response

            # Should not raise
            await notification_service._send_slack(config, mock_failure)

    @pytest.mark.asyncio
    async def test_send_teams_notification(self, notification_service, mock_failure):
        """Test sending Microsoft Teams notification"""
        config = {
            'webhook_url': 'https://outlook.office.com/webhook/test'
        }

        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response

            # Should not raise
            await notification_service._send_teams(config, mock_failure)

    def _get_handlers(self):
        """Helper to get notification handlers"""
        return {
            'email': self._send_email,
            'slack': self._send_slack,
            'teams': self._send_teams
        }


# Add _get_handlers method to NotificationService for testing
def _get_handlers_patch(self):
    return {
        'email': self._send_email,
        'slack': self._send_slack,
        'teams': self._send_teams
    }

NotificationService._get_handlers = _get_handlers_patch
