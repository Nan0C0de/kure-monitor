"""ChatOps interaction endpoints for Slack and Teams button clicks.

When Kure Monitor sends a pod-failure notification in "app" mode, the
alert includes an interactive button (Slack Block Kit / Teams Adaptive
Card).  Clicking the button sends a callback to one of the endpoints
defined here.  The endpoint acknowledges immediately (Slack demands
< 3 s) and kicks off an ``asyncio.Task`` that:

1. Posts a "thinking" indicator in the thread.
2. Fetches pod diagnostic data and generates an AI solution.
3. Updates the thread with the full AI analysis.
"""

from fastapi import APIRouter, Request, HTTPException
import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Set
from urllib.parse import parse_qs

from .deps import RouterDeps

logger = logging.getLogger(__name__)

# Failure reasons eligible for log-aware troubleshooting (mirrors routes_pods.py).
_LOG_CAPTURE_REASONS: Set[str] = {"CrashLoopBackOff", "OOMKilled", "Error"}


def create_chatops_router(deps: RouterDeps) -> APIRouter:
    """ChatOps interaction endpoints — no user auth required.

    Verification is handled per-provider (Slack signing secret, etc.).
    """
    router = APIRouter()
    db = deps.db
    solution_engine = deps.solution_engine
    notification_service = deps.notification_service

    # -----------------------------------------------------------------
    # Slack interactive endpoint
    # -----------------------------------------------------------------

    @router.post("/chatops/slack/interact")
    async def slack_interaction(request: Request):
        """Handle Slack interactive component payloads (button clicks).

        Slack sends a URL-encoded form with a ``payload`` field containing
        JSON.  We must respond within 3 seconds, so we acknowledge
        immediately and process the troubleshoot request in the background.
        """
        # 1. Verify Slack signature
        body = await request.body()
        await _verify_slack_signature(request, body, db)

        # 2. Parse the payload
        form_data = parse_qs(body.decode("utf-8", errors="replace"))
        raw_payload = form_data.get("payload", [None])[0]
        if not raw_payload:
            raise HTTPException(status_code=400, detail="Missing payload")
        payload = json.loads(raw_payload)

        # Handle only our known action; silently ignore everything else.
        actions = payload.get("actions", [])
        if not actions:
            return {"ok": True}
        action = actions[0]
        if action.get("action_id") != "kure_troubleshoot":
            return {"ok": True}

        # 3. Extract context from button value
        try:
            button_value = json.loads(action["value"])
        except (KeyError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Malformed action value")

        pod_failure_id = button_value.get("pod_failure_id")
        if pod_failure_id is None:
            raise HTTPException(status_code=400, detail="Missing pod_failure_id")

        # 4. Gather Slack-specific context for the threaded reply.
        channel_id = payload.get("channel", {}).get("id", "")
        message_ts = payload.get("message", {}).get("ts", "")
        user_name = payload.get("user", {}).get("username", "someone")
        response_url = payload.get("response_url", "")

        # 5. Fire-and-forget the heavy processing.
        asyncio.create_task(
            _process_slack_troubleshoot(
                db=db,
                solution_engine=solution_engine,
                notification_service=notification_service,
                pod_failure_id=pod_failure_id,
                channel_id=channel_id,
                message_ts=message_ts,
                user_name=user_name,
                response_url=response_url,
            )
        )

        # 6. Acknowledge immediately (Slack requires < 3 s response).
        return {"ok": True}

    # -----------------------------------------------------------------
    # Teams interactive endpoint
    # -----------------------------------------------------------------

    @router.post("/chatops/teams/interact")
    async def teams_interaction(request: Request):
        """Handle Teams Adaptive Card ``Action.Http`` callbacks."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        pod_failure_id = body.get("pod_failure_id")
        webhook_url = body.get("webhook_url")

        if not pod_failure_id:
            raise HTTPException(status_code=400, detail="Missing pod_failure_id")
        if not webhook_url:
            raise HTTPException(status_code=400, detail="Missing webhook_url")

        asyncio.create_task(
            _process_teams_troubleshoot(
                db=db,
                solution_engine=solution_engine,
                pod_failure_id=pod_failure_id,
                webhook_url=webhook_url,
            )
        )

        # Return a quick acknowledgement; the real solution arrives as a
        # new Adaptive Card posted to the same webhook.
        return {"status": "processing", "message": "AI analysis started…"}

    return router


# =====================================================================
# Helpers
# =====================================================================

async def _verify_slack_signature(
    request: Request, body: bytes, db
) -> None:
    """Verify the request came from Slack using the signing secret.

    If no signing secret is configured we log a warning but do **not**
    reject the request — this keeps the onboarding experience smooth
    while the admin is still setting things up.
    """
    settings = await db.get_notification_setting("slack")
    signing_secret: str | None = None
    if settings:
        signing_secret = settings.config.get("signing_secret")
    if not signing_secret:
        logger.warning(
            "Slack signing secret not configured — skipping request verification"
        )
        return

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    slack_signature = request.headers.get("X-Slack-Signature", "")

    if not timestamp or not slack_signature:
        raise HTTPException(status_code=403, detail="Missing Slack signature headers")

    # Reject requests older than 5 minutes (replay protection).
    try:
        if abs(time.time() - float(timestamp)) > 300:
            raise HTTPException(status_code=403, detail="Request too old")
    except (ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Invalid timestamp")

    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8', errors='replace')}"
    computed = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(computed, slack_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")


# =====================================================================
# Background processing tasks
# =====================================================================

async def _generate_solution(db, solution_engine, pod_failure_id: int) -> str:
    """Fetch pod failure data and generate the best available AI solution.

    Tries the log-aware path first (for CrashLoopBackOff / OOMKilled /
    Error when captured logs exist), then falls back to the quick
    solution path.
    """
    pod = await db.get_pod_failure_by_id(pod_failure_id)
    if not pod:
        raise Exception(f"Pod failure {pod_failure_id} not found")

    # If the pod already has a cached log-aware solution, reuse it.
    if pod.log_aware_solution:
        return pod.log_aware_solution

    # Try log-aware first.
    if pod.failure_reason in _LOG_CAPTURE_REASONS:
        logs = await db.get_pod_failure_logs(pod_failure_id)
        if logs:
            return await solution_engine.get_log_aware_solution(
                reason=pod.failure_reason,
                message=pod.failure_message or "",
                events=pod.events,
                container_statuses=pod.container_statuses,
                pod_context={
                    "pod_name": pod.pod_name,
                    "namespace": pod.namespace,
                    "image": "Unknown",
                },
                manifest=pod.manifest or "",
                container_logs=logs,
            )

    # Fallback: quick solution (LLM or rule-based).
    return await solution_engine.get_solution(
        reason=pod.failure_reason,
        message=pod.failure_message,
        events=pod.events,
        container_statuses=pod.container_statuses,
        pod_context={
            "name": pod.pod_name,
            "namespace": pod.namespace,
            "image": "Unknown",
        },
    )


async def _process_slack_troubleshoot(
    db,
    solution_engine,
    notification_service,
    pod_failure_id: int,
    channel_id: str,
    message_ts: str,
    user_name: str,
    response_url: str,  # noqa: ARG001 — kept for future ephemeral updates
) -> None:
    """Background task: generate AI solution and post as threaded Slack reply."""
    bot_token: str | None = None
    session = None
    try:
        settings = await db.get_notification_setting("slack")
        if not settings:
            logger.error("Slack notification setting not found")
            return
        bot_token = settings.config.get("bot_token")
        if not bot_token:
            logger.error("Slack bot_token not configured")
            return

        session = await notification_service._get_session()

        # 1. Post "analyzing …" message in the thread.
        async with session.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {bot_token}"},
            json={
                "channel": channel_id,
                "thread_ts": message_ts,
                "text": (
                    f"🔍 <@{user_name}> requested AI troubleshooting. "
                    f"Analyzing pod failure…"
                ),
            },
        ) as resp:
            thinking_data = await resp.json()
            thinking_ts = thinking_data.get("ts")

        # 2. Generate the AI solution.
        pod = await db.get_pod_failure_by_id(pod_failure_id)
        solution = await _generate_solution(db, solution_engine, pod_failure_id)

        # 3. Update the "thinking" message with the actual analysis.
        pod_label = (
            f"{pod.namespace}/{pod.pod_name}" if pod else f"pod #{pod_failure_id}"
        )
        solution_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🤖 AI Analysis: {pod_label}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _truncate_for_slack(solution),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Requested by <@{user_name}> • "
                            "Powered by Kure Monitor AI"
                        ),
                    }
                ],
            },
        ]

        if thinking_ts:
            # Update the placeholder message in-place.
            async with session.post(
                "https://slack.com/api/chat.update",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={
                    "channel": channel_id,
                    "ts": thinking_ts,
                    "blocks": solution_blocks,
                    "text": f"AI Analysis for {pod_label}",
                },
            ) as resp:
                update_data = await resp.json()
                if not update_data.get("ok"):
                    logger.error(f"Failed to update Slack message: {update_data}")
        else:
            # Thinking message failed; post the solution as a new message.
            async with session.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={
                    "channel": channel_id,
                    "thread_ts": message_ts,
                    "blocks": solution_blocks,
                    "text": f"AI Analysis for {pod_label}",
                },
            ) as resp:
                post_data = await resp.json()
                if not post_data.get("ok"):
                    logger.error(f"Failed to post Slack solution: {post_data}")

    except Exception as e:
        logger.error(
            f"ChatOps Slack troubleshoot failed for pod {pod_failure_id}: {e}",
            exc_info=True,
        )
        # Best-effort: post an error notice in the thread.
        if bot_token and session and channel_id and message_ts:
            try:
                async with session.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={
                        "channel": channel_id,
                        "thread_ts": message_ts,
                        "text": (
                            f"❌ AI analysis failed: {str(e)[:200]}. "
                            "Please try the Kure Monitor dashboard."
                        ),
                    },
                ) as _:
                    pass
            except Exception:
                pass


async def _process_teams_troubleshoot(
    db,
    solution_engine,
    pod_failure_id: int,
    webhook_url: str,
) -> None:
    """Background task: generate AI solution and post as a new Teams card."""
    try:
        pod = await db.get_pod_failure_by_id(pod_failure_id)
        if not pod:
            logger.error(f"Pod failure {pod_failure_id} not found for Teams ChatOps")
            return

        solution = await _generate_solution(db, solution_engine, pod_failure_id)

        pod_label = f"{pod.namespace}/{pod.pod_name}"

        # Post the solution as a new Adaptive Card via the same webhook.
        import aiohttp

        card = {
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
                                "text": f"🤖 AI Analysis: {pod_label}",
                            },
                            {
                                "type": "TextBlock",
                                "text": _truncate_for_teams(solution),
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": "Powered by Kure Monitor AI",
                                "size": "Small",
                                "color": "Accent",
                                "spacing": "Medium",
                            },
                        ],
                    },
                }
            ],
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(webhook_url, json=card) as resp:
                if resp.status not in (200, 202):
                    text = await resp.text()
                    logger.error(
                        f"Teams ChatOps reply failed ({resp.status}): {text}"
                    )

    except Exception as e:
        logger.error(
            f"ChatOps Teams troubleshoot failed for pod {pod_failure_id}: {e}",
            exc_info=True,
        )


# =====================================================================
# Formatting helpers
# =====================================================================

def _truncate_for_slack(text: str, max_len: int = 3000) -> str:
    """Truncate text to fit Slack's block text limit (3000 chars)."""
    if len(text) <= max_len:
        return text
    return (
        text[: max_len - 60]
        + "\n\n_…truncated. See full analysis in Kure Monitor dashboard._"
    )


def _truncate_for_teams(text: str, max_len: int = 10000) -> str:
    """Truncate text to fit Teams Adaptive Card body limit."""
    if len(text) <= max_len:
        return text
    return (
        text[: max_len - 60]
        + "\n\n_…truncated. See full analysis in Kure Monitor dashboard._"
    )
