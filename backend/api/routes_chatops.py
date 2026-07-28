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

    async def _handle_slack_incoming(request: Request):
        body = await request.body()
        await _verify_slack_signature(request, body, db)

        body_str = body.decode("utf-8", errors="replace").strip()
        payload = None
        if body_str.startswith("payload="):
            form_data = parse_qs(body_str)
            raw = form_data.get("payload", [None])[0]
            if raw:
                try:
                    payload = json.loads(raw)
                except Exception:
                    pass
        if not payload:
            try:
                payload = json.loads(body_str)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

        # 1. Handle URL verification challenge during Slack app setup
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        logger.info(f"DEBUG INCOMING SLACK PAYLOAD: {json.dumps(payload)}")

        # 2. Handle Events API callbacks (e.g. user replies in threads)
        if payload.get("type") == "event_callback":
            event = payload.get("event", {})
            logger.info(f"Received Slack event: {event.get('type')}, subtype: {event.get('subtype')}")
            
            if event.get("bot_id") or event.get("subtype") in (
                "bot_message",
                "message_changed",
                "message_deleted",
            ):
                return {"ok": True}

            thread_ts = event.get("thread_ts")
            channel_id = event.get("channel")
            text = event.get("text", "").strip()
            user_id = event.get("user", "unknown")

            logger.info(f"Processing Slack message event. thread_ts={thread_ts}, channel={channel_id}, text len={len(text)}")

            if not thread_ts or not channel_id or not text:
                logger.info("Ignoring Slack event: missing thread_ts, channel_id, or text")
                return {"ok": True}

            chatops_rec = await db.get_chatops_message_by_message_id(
                provider="slack", message_id=thread_ts
            )
            if chatops_rec:
                logger.info(f"Found chatops_rec for thread_ts {thread_ts}, dispatching reply task.")
                pod_failure_id = chatops_rec["pod_failure_id"]
                asyncio.create_task(
                    _process_slack_chat_reply(
                        db=db,
                        solution_engine=solution_engine,
                        notification_service=notification_service,
                        pod_failure_id=pod_failure_id,
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        user_id=user_id,
                        user_text=text,
                    )
                )
            else:
                logger.info(f"No chatops_rec found for thread_ts {thread_ts}")
            return {"ok": True}

        # 3. Handle interactive component payloads (button clicks)
        actions = payload.get("actions", [])
        if not actions:
            return {"ok": True}
        action = actions[0]
        if action.get("action_id") != "kure_troubleshoot":
            return {"ok": True}

        try:
            button_value = json.loads(action["value"])
        except (KeyError, json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail="Malformed action value")

        pod_failure_id = button_value.get("pod_failure_id")
        if pod_failure_id is None:
            raise HTTPException(status_code=400, detail="Missing pod_failure_id")

        channel_id = payload.get("channel", {}).get("id", "")
        message_ts = payload.get("message", {}).get("ts", "")
        user_name = payload.get("user", {}).get("username", "someone")
        response_url = payload.get("response_url", "")

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
        return {"ok": True}

    @router.post("/chatops/slack/interact")
    async def slack_interaction(request: Request):
        """Handle Slack interactive component payloads and events (unified)."""
        return await _handle_slack_incoming(request)

    @router.post("/chatops/slack/events")
    async def slack_events(request: Request):
        """Handle Slack Events API callbacks and interactive components (unified)."""
        return await _handle_slack_incoming(request)

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

        # Ensure root message mapping is stored for threaded chat replies
        try:
            await db.save_chatops_message(
                pod_failure_id=pod_failure_id,
                provider="slack",
                channel_id=channel_id,
                message_id=message_ts,
            )
        except Exception:
            pass

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


async def _process_slack_chat_reply(
    db,
    solution_engine,
    notification_service,
    pod_failure_id: int,
    channel_id: str,
    thread_ts: str,
    user_id: str,
    user_text: str,
) -> None:
    """Background task: process a user's reply in a Slack troubleshooting thread and answer conversationally."""
    bot_token: str | None = None
    session = None
    try:
        if not solution_engine.llm_provider:
            logger.warning("LLM provider not configured for Slack chat reply")
            return

        settings = await db.get_notification_setting("slack")
        if not settings:
            return
        bot_token = settings.config.get("bot_token")
        if not bot_token:
            return

        session = await notification_service._get_session()

        # 1. Post "analyzing follow-up question..." indicator
        thinking_ts = None
        async with session.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {bot_token}"},
            json={
                "channel": channel_id,
                "thread_ts": thread_ts,
                "text": f"💬 <@{user_id}> analyzing follow-up question...",
            },
        ) as resp:
            thinking_data = await resp.json()
            thinking_ts = thinking_data.get("ts")

        # 2. Load pod and build conversational context
        pod = await db.get_pod_failure_by_id(pod_failure_id)
        if not pod:
            return

        chat_session_id = f"slack_{thread_ts}"
        await db.save_chat_message(
            pod.pod_name, pod.namespace, chat_session_id, "user", f"<@{user_id}>: {user_text}"
        )

        history = await db.get_chat_history(pod.pod_name, pod.namespace, chat_session_id)

        system_prompt = (
            "You are Kure Monitor, a helpful Kubernetes AI troubleshooting assistant. "
            "You are participating in a Slack thread helping engineers debug and fix a pod failure. "
            "Be concise, direct, and format your answer in Slack markdown (*bold*, _italics_, and ```code blocks```)."
        )

        context_blocks = [f"Target Pod: {pod.namespace}/{pod.pod_name}"]
        if pod.failure_reason:
            context_blocks.append(f"Failure Reason: {pod.failure_reason}")
        if pod.failure_message:
            context_blocks.append(f"Failure Message: {pod.failure_message}")
        if pod.events:
            events_str = "\n".join([str(e) for e in pod.events[-10:]])
            context_blocks.append(f"Recent Pod Events:\n{events_str}")
        if pod.manifest:
            context_blocks.append(f"Pod Manifest:\n```yaml\n{pod.manifest}\n```")

        logs = await db.get_pod_failure_logs(pod_failure_id)
        if logs:
            for log_entry in logs:
                cname = log_entry.get("container_name", "unknown")
                log_text = log_entry.get("logs", "")
                if log_text:
                    log_lines = log_text.splitlines()[-50:]
                    context_blocks.append(f"Container {cname} Logs:\n" + "\n".join(log_lines))

        history_str = ""
        if len(history) > 1:
            history_lines = []
            for h in history[:-1]:
                role_label = "Engineer" if h["role"] == "user" else "Kure AI"
                history_lines.append(f"{role_label}: {h['text']}")
            history_str = "\n\nPrevious Conversation in this Thread:\n" + "\n".join(history_lines[-10:])

        user_prompt = (
            f"Pod Diagnostic Context:\n{chr(10).join(context_blocks)}"
            f"{history_str}\n\n"
            f"Latest Question from Engineer (<@{user_id}>):\n{user_text}"
        )

        llm_response = await solution_engine.llm_provider.generate_raw(system_prompt, user_prompt)
        reply_text = llm_response.content

        await db.save_chat_message(
            pod.pod_name, pod.namespace, chat_session_id, "assistant", reply_text
        )

        reply_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _truncate_for_slack(reply_text),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Reply to <@{user_id}> • Kure Monitor AI",
                    }
                ],
            },
        ]

        if thinking_ts:
            async with session.post(
                "https://slack.com/api/chat.update",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={
                    "channel": channel_id,
                    "ts": thinking_ts,
                    "blocks": reply_blocks,
                    "text": reply_text[:200],
                },
            ) as _:
                pass
        else:
            async with session.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={
                    "channel": channel_id,
                    "thread_ts": thread_ts,
                    "blocks": reply_blocks,
                    "text": reply_text[:200],
                },
            ) as _:
                pass

    except Exception as e:
        logger.error(f"Slack chat reply failed for pod {pod_failure_id}: {e}", exc_info=True)
        if bot_token and session and channel_id and thread_ts:
            try:
                async with session.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={
                        "channel": channel_id,
                        "thread_ts": thread_ts,
                        "text": f"❌ Could not answer question: {str(e)[:200]}",
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
