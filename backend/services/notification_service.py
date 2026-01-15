import aiohttp
import logging
from typing import Dict, Any
from models.models import PodFailureResponse

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via various providers"""

    def __init__(self, db):
        self.db = db

    async def send_pod_failure_notification(self, failure: PodFailureResponse):
        """Send notification for a pod failure to all enabled providers"""
        try:
            settings = await self.db.get_enabled_notification_settings()

            for setting in settings:
                try:
                    await self._send_notification(
                        provider=setting.provider,
                        config=setting.config,
                        failure=failure
                    )
                    logger.info(f"Sent {setting.provider} notification for pod {failure.namespace}/{failure.pod_name}")
                except Exception as e:
                    logger.error(f"Failed to send {setting.provider} notification: {e}")
        except Exception as e:
            logger.error(f"Error getting notification settings: {e}")

    async def _send_notification(self, provider: str, config: Dict[str, Any], failure: PodFailureResponse):
        """Route to appropriate provider handler"""
        handlers = {
            'slack': self._send_slack,
            'teams': self._send_teams
        }

        handler = handlers.get(provider)
        if handler:
            await handler(config, failure)
        else:
            logger.warning(f"Unknown notification provider: {provider}")

    async def _send_slack(self, config: Dict[str, Any], failure: PodFailureResponse):
        """Send Slack notification via webhook"""
        payload = {
            "attachments": [{
                "color": "danger",
                "title": f"Pod Failure: {failure.namespace}/{failure.pod_name}",
                "fields": [
                    {"title": "Namespace", "value": failure.namespace, "short": True},
                    {"title": "Pod", "value": failure.pod_name, "short": True},
                    {"title": "Reason", "value": failure.failure_reason, "short": True},
                    {"title": "Node", "value": failure.node_name or "N/A", "short": True},
                    {"title": "Message", "value": (failure.failure_message or "N/A")[:500], "short": False}
                ],
                "footer": "Kure Monitor",
                "ts": int(__import__('time').time())
            }]
        }

        if config.get('channel'):
            payload['channel'] = config['channel']

        async with aiohttp.ClientSession() as session:
            async with session.post(
                config['webhook_url'],
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"Slack webhook returned {response.status}: {text}")

    async def _send_teams(self, config: Dict[str, Any], failure: PodFailureResponse):
        """Send Microsoft Teams notification via Power Automate Workflows webhook"""
        # Use Adaptive Card format for Power Automate Workflows
        # (Office 365 Connectors with MessageCard format are deprecated)
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Large",
                                "weight": "Bolder",
                                "color": "Attention",
                                "text": "Pod Failure Alert"
                            },
                            {
                                "type": "TextBlock",
                                "text": f"{failure.namespace}/{failure.pod_name}",
                                "wrap": True,
                                "weight": "Bolder"
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Namespace", "value": failure.namespace},
                                    {"title": "Pod", "value": failure.pod_name},
                                    {"title": "Reason", "value": failure.failure_reason},
                                    {"title": "Node", "value": failure.node_name or "N/A"}
                                ]
                            },
                            {
                                "type": "TextBlock",
                                "text": "Message",
                                "weight": "Bolder",
                                "spacing": "Medium"
                            },
                            {
                                "type": "TextBlock",
                                "text": (failure.failure_message or "N/A")[:500],
                                "wrap": True
                            },
                            {
                                "type": "TextBlock",
                                "text": "Kure Monitor",
                                "size": "Small",
                                "color": "Accent",
                                "spacing": "Medium"
                            }
                        ]
                    }
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                config['webhook_url'],
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                # Workflows webhooks return 202 Accepted on success
                if response.status not in (200, 202):
                    text = await response.text()
                    raise Exception(f"Teams webhook returned {response.status}: {text}")

    async def test_notification(self, provider: str, config: Dict[str, Any]) -> bool:
        """Send a test notification to verify configuration"""
        # Create a mock failure for testing
        test_failure = PodFailureResponse(
            pod_name="test-pod",
            namespace="test-namespace",
            node_name="test-node",
            phase="Failed",
            creation_timestamp="2024-01-01T00:00:00Z",
            failure_reason="TestNotification",
            failure_message="This is a test notification from Kure Monitor. If you received this, your notification settings are working correctly!",
            container_statuses=[],
            events=[],
            logs="",
            manifest="",
            solution="This is a test - no solution needed.",
            timestamp="2024-01-01T00:00:00Z"
        )

        await self._send_notification(provider, config, test_failure)
        return True
