import aiohttp
import logging
import json
from typing import Dict, Any, Optional
from models.models import PodFailureResponse

logger = logging.getLogger(__name__)

# Total HTTP timeout for outbound webhook calls (Slack/Teams).
_WEBHOOK_TIMEOUT_SECONDS = 30.0


class NotificationService:
    """Service for sending notifications via various providers"""

    def __init__(self, db):
        self.db = db
        # Lazily created in an event loop on first webhook send.
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return a process-wide ClientSession, creating it lazily."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=_WEBHOOK_TIMEOUT_SECONDS)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the shared ClientSession if one was created."""
        if self._session is not None and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = None

    async def send_pod_failure_notification(self, failure: PodFailureResponse):
        """Send notification for a pod failure to all enabled providers"""
        try:
            settings = await self.db.get_enabled_notification_settings()

            for setting in settings:
                try:
                    await self._send_notification(
                        provider=setting.provider,
                        config=setting.config,
                        failure=failure,
                    )
                    logger.info(
                        f"Sent {setting.provider} notification for pod {failure.namespace}/{failure.pod_name}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send {setting.provider} notification: {e}")
        except Exception as e:
            logger.error(f"Error getting notification settings: {e}")

    async def _send_notification(
        self, provider: str, config: Dict[str, Any], failure: PodFailureResponse
    ):
        """Route to appropriate provider handler, choosing interactive vs webhook mode"""
        if provider == "slack":
            if config.get("mode") == "app" or config.get("bot_token"):
                await self._send_slack_interactive(config, failure)
            else:
                await self._send_slack(config, failure)
        elif provider == "teams":
            if config.get("mode") == "app" or config.get("callback_url"):
                await self._send_teams_interactive(config, failure)
            else:
                await self._send_teams(config, failure)
        else:
            logger.warning(f"Unknown notification provider: {provider}")

    async def _send_slack(self, config: Dict[str, Any], failure: PodFailureResponse):
        """Send Slack notification via webhook"""
        payload = {
            "attachments": [
                {
                    "color": "danger",
                    "title": f"Pod Failure: {failure.namespace}/{failure.pod_name}",
                    "fields": [
                        {
                            "title": "Namespace",
                            "value": failure.namespace,
                            "short": True,
                        },
                        {"title": "Pod", "value": failure.pod_name, "short": True},
                        {
                            "title": "Reason",
                            "value": failure.failure_reason,
                            "short": True,
                        },
                        {
                            "title": "Node",
                            "value": failure.node_name or "N/A",
                            "short": True,
                        },
                        {
                            "title": "Message",
                            "value": (failure.failure_message or "N/A")[:500],
                            "short": False,
                        },
                    ],
                    "footer": "Kure Monitor",
                    "ts": int(__import__("time").time()),
                }
            ]
        }

        session = await self._get_session()
        async with session.post(
            config["webhook_url"],
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
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
                                "text": "Pod Failure Alert",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"{failure.namespace}/{failure.pod_name}",
                                "wrap": True,
                                "weight": "Bolder",
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Namespace", "value": failure.namespace},
                                    {"title": "Pod", "value": failure.pod_name},
                                    {
                                        "title": "Reason",
                                        "value": failure.failure_reason,
                                    },
                                    {
                                        "title": "Node",
                                        "value": failure.node_name or "N/A",
                                    },
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": "Message",
                                "weight": "Bolder",
                                "spacing": "Medium",
                            },
                            {
                                "type": "TextBlock",
                                "text": (failure.failure_message or "N/A")[:500],
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": "Kure Monitor",
                                "size": "Small",
                                "color": "Accent",
                                "spacing": "Medium",
                            },
                        ],
                    },
                }
            ],
        }

        session = await self._get_session()
        async with session.post(
            config["webhook_url"],
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            # Workflows webhooks return 202 Accepted on success
            if response.status not in (200, 202):
                text = await response.text()
                raise Exception(f"Teams webhook returned {response.status}: {text}")

    async def _send_slack_interactive(self, config: Dict[str, Any], failure: PodFailureResponse):
        """Send Slack notification via Bot Token with interactive Block Kit button"""
        bot_token = config.get("bot_token")
        if not bot_token:
            raise Exception("Slack Bot User OAuth Token (bot_token) is required for app mode")
        channel = config.get("channel_id", config.get("channel", ""))
        if not channel:
            raise Exception("Slack Channel ID (channel_id) is required for app mode")

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 Pod Failure Detected", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Pod:*\n`{failure.pod_name}`"},
                    {"type": "mrkdwn", "text": f"*Namespace:*\n`{failure.namespace}`"},
                    {"type": "mrkdwn", "text": f"*Reason:*\n`{failure.failure_reason}`"},
                    {"type": "mrkdwn", "text": f"*Node:*\n`{failure.node_name or 'N/A'}`"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Message:*\n{(failure.failure_message or 'N/A')[:500]}"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🔍 Troubleshoot", "emoji": True},
                        "style": "primary",
                        "action_id": "kure_troubleshoot",
                        "value": json.dumps({
                            "pod_failure_id": failure.id or 0,
                            "namespace": failure.namespace,
                            "pod_name": failure.pod_name,
                            "failure_reason": failure.failure_reason,
                        }),
                    }
                ],
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Kure Monitor • {failure.creation_timestamp}"}
                ],
            },
        ]

        session = await self._get_session()
        async with session.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {bot_token}"},
            json={
                "channel": channel,
                "blocks": blocks,
                "text": f"Pod failure: {failure.namespace}/{failure.pod_name}",
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            data = await response.json()
            if data.get("ok"):
                if failure.id:
                    try:
                        await self.db.save_chatops_message(
                            pod_failure_id=failure.id,
                            provider="slack",
                            channel_id=data["channel"],
                            message_id=data["ts"],
                        )
                    except Exception as db_err:
                        logger.warning(f"Failed to store Slack chatops message mapping: {db_err}")
            else:
                raise Exception(f"Slack API error: {data.get('error', 'unknown')}")

    async def _send_teams_interactive(self, config: Dict[str, Any], failure: PodFailureResponse):
        """Send Teams notification via Adaptive Card with Action.Http button"""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            raise Exception("Teams Workflow Webhook URL (webhook_url) is required")
        callback_url = config.get("callback_url", "").rstrip("/")
        if not callback_url:
            raise Exception("Kure Public URL (callback_url) is required for app mode")

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
                                "text": "🚨 Pod Failure Alert",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"{failure.namespace}/{failure.pod_name}",
                                "wrap": True,
                                "weight": "Bolder",
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Namespace", "value": failure.namespace},
                                    {"title": "Pod", "value": failure.pod_name},
                                    {"title": "Reason", "value": failure.failure_reason},
                                    {"title": "Node", "value": failure.node_name or "N/A"},
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": f"**Message:** {(failure.failure_message or 'N/A')[:500]}",
                                "wrap": True,
                            },
                        ],
                        "actions": [
                            {
                                "type": "Action.Http",
                                "title": "🔍 Troubleshoot",
                                "method": "POST",
                                "url": f"{callback_url}/api/chatops/teams/interact",
                                "body": json.dumps({
                                    "pod_failure_id": failure.id or 0,
                                    "namespace": failure.namespace,
                                    "pod_name": failure.pod_name,
                                    "failure_reason": failure.failure_reason,
                                    "webhook_url": webhook_url,
                                }),
                                "style": "positive",
                            }
                        ],
                    },
                }
            ],
        }

        session = await self._get_session()
        async with session.post(
            webhook_url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status not in (200, 202):
                text = await response.text()
                raise Exception(f"Teams interactive webhook returned {response.status}: {text}")

    async def send_pod_resolved_notification(self, namespace: str, pod_name: str):
        """Send notification when a pod failure is resolved/dismissed"""
        try:
            settings = await self.db.get_enabled_notification_settings()

            for setting in settings:
                try:
                    await self._send_resolved_notification(
                        provider=setting.provider,
                        config=setting.config,
                        namespace=namespace,
                        pod_name=pod_name,
                    )
                    logger.info(
                        f"Sent {setting.provider} resolved notification for pod {namespace}/{pod_name}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send {setting.provider} resolved notification: {e}"
                    )
        except Exception as e:
            logger.error(f"Error getting notification settings: {e}")

    async def _send_resolved_notification(
        self, provider: str, config: Dict[str, Any], namespace: str, pod_name: str
    ):
        """Route to appropriate provider handler for resolved notifications"""
        handlers = {
            "slack": self._send_slack_resolved,
            "teams": self._send_teams_resolved,
        }

        handler = handlers.get(provider)
        if handler:
            await handler(config, namespace, pod_name)
        else:
            logger.warning(f"Unknown notification provider: {provider}")

    async def _send_slack_resolved(
        self, config: Dict[str, Any], namespace: str, pod_name: str
    ):
        """Send Slack resolved notification via webhook"""
        payload = {
            "attachments": [
                {
                    "color": "good",
                    "title": f"Pod Resolved: {namespace}/{pod_name}",
                    "fields": [
                        {"title": "Namespace", "value": namespace, "short": True},
                        {"title": "Pod", "value": pod_name, "short": True},
                        {"title": "Status", "value": "Resolved", "short": True},
                    ],
                    "footer": "Kure Monitor",
                    "ts": int(__import__("time").time()),
                }
            ]
        }

        session = await self._get_session()
        async with session.post(
            config["webhook_url"],
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"Slack webhook returned {response.status}: {text}")

    async def _send_teams_resolved(
        self, config: Dict[str, Any], namespace: str, pod_name: str
    ):
        """Send Microsoft Teams resolved notification via Power Automate Workflows webhook"""
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
                                "color": "Good",
                                "text": "Pod Resolved",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"{namespace}/{pod_name}",
                                "wrap": True,
                                "weight": "Bolder",
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Namespace", "value": namespace},
                                    {"title": "Pod", "value": pod_name},
                                    {"title": "Status", "value": "Resolved"},
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": "Kure Monitor",
                                "size": "Small",
                                "color": "Accent",
                                "spacing": "Medium",
                            },
                        ],
                    },
                }
            ],
        }

        session = await self._get_session()
        async with session.post(
            config["webhook_url"],
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
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
            timestamp="2024-01-01T00:00:00Z",
        )

        await self._send_notification(provider, config, test_failure)
        return True
