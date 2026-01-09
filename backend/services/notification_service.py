import aiohttp
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List
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
            'email': self._send_email,
            'slack': self._send_slack,
            'teams': self._send_teams
        }

        handler = handlers.get(provider)
        if handler:
            await handler(config, failure)
        else:
            logger.warning(f"Unknown notification provider: {provider}")

    async def _send_email(self, config: Dict[str, Any], failure: PodFailureResponse):
        """Send email notification using aiosmtplib"""
        try:
            import aiosmtplib

            message = MIMEMultipart('alternative')
            message['From'] = config['from_email']
            message['To'] = ', '.join(config['to_emails'])
            message['Subject'] = f"[Kure Alert] Pod Failure: {failure.namespace}/{failure.pod_name}"

            # Plain text version
            text_body = self._format_text_body(failure)
            message.attach(MIMEText(text_body, 'plain'))

            # HTML version
            html_body = self._format_email_body(failure)
            message.attach(MIMEText(html_body, 'html'))

            await aiosmtplib.send(
                message,
                hostname=config['smtp_host'],
                port=config.get('smtp_port', 587),
                username=config.get('smtp_user'),
                password=config.get('smtp_password'),
                use_tls=config.get('use_tls', True),
                start_tls=config.get('use_tls', True)
            )
        except ImportError:
            logger.error("aiosmtplib not installed. Install with: pip install aiosmtplib")
            raise
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise

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
        """Send Microsoft Teams notification via webhook"""
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "FF0000",
            "summary": f"Pod Failure: {failure.namespace}/{failure.pod_name}",
            "sections": [{
                "activityTitle": f"Pod Failure Alert",
                "activitySubtitle": f"{failure.namespace}/{failure.pod_name}",
                "facts": [
                    {"name": "Namespace", "value": failure.namespace},
                    {"name": "Pod", "value": failure.pod_name},
                    {"name": "Reason", "value": failure.failure_reason},
                    {"name": "Node", "value": failure.node_name or "N/A"},
                    {"name": "Message", "value": (failure.failure_message or "N/A")[:500]}
                ],
                "markdown": True
            }]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                config['webhook_url'],
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
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

    def _format_text_body(self, failure: PodFailureResponse) -> str:
        """Format plain text email body"""
        return f"""Kure Monitor - Pod Failure Alert

Namespace: {failure.namespace}
Pod: {failure.pod_name}
Reason: {failure.failure_reason}
Node: {failure.node_name or 'N/A'}
Message: {failure.failure_message or 'N/A'}

AI-Generated Solution:
{failure.solution}

---
This alert was sent by Kure Monitor
"""

    def _format_email_body(self, failure: PodFailureResponse) -> str:
        """Format HTML email body"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background-color: #dc3545; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f5f5f5; }}
        .solution {{ background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin-top: 20px; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Pod Failure Alert</h1>
    </div>
    <div class="content">
        <h2>{failure.namespace}/{failure.pod_name}</h2>
        <table>
            <tr><th>Field</th><th>Value</th></tr>
            <tr><td><strong>Namespace</strong></td><td>{failure.namespace}</td></tr>
            <tr><td><strong>Pod</strong></td><td>{failure.pod_name}</td></tr>
            <tr><td><strong>Reason</strong></td><td>{failure.failure_reason}</td></tr>
            <tr><td><strong>Node</strong></td><td>{failure.node_name or 'N/A'}</td></tr>
            <tr><td><strong>Message</strong></td><td>{failure.failure_message or 'N/A'}</td></tr>
        </table>

        <div class="solution">
            <h3>AI-Generated Solution</h3>
            <pre style="white-space: pre-wrap; word-wrap: break-word;">{failure.solution}</pre>
        </div>
    </div>
    <div class="footer">
        <p>This alert was sent by Kure Monitor</p>
    </div>
</body>
</html>
"""
