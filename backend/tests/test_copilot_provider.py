"""Unit tests for CopilotProvider (GitHub Models).

CopilotProvider is a thin subclass of OpenAIProvider that targets the
OpenAI-compatible GitHub Models inference endpoint. These tests mock the
aiohttp layer so the real GitHub API is never hit.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_providers import CopilotProvider, OpenAIProvider
from llm_providers.base import LLMResponse


def _mock_chat_completion_response(
    content: str = "## What's Wrong\nbad image\n",
    total_tokens: int = 42,
) -> MagicMock:
    """Build a MagicMock mimicking an aiohttp response context manager."""
    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(return_value={
        "choices": [{"message": {"content": content}}],
        "usage": {"total_tokens": total_tokens},
    })
    resp.text = AsyncMock(return_value="")

    post_ctx = MagicMock()
    post_ctx.__aenter__ = AsyncMock(return_value=resp)
    post_ctx.__aexit__ = AsyncMock(return_value=False)
    return post_ctx


class TestCopilotProviderBasics:
    def test_is_openai_subclass(self):
        """CopilotProvider should delegate OpenAI-compatible behavior."""
        assert issubclass(CopilotProvider, OpenAIProvider)

    def test_provider_name(self):
        provider = CopilotProvider(api_key="ghp_test")
        assert provider.provider_name == "copilot"

    def test_default_model(self):
        provider = CopilotProvider(api_key="ghp_test")
        assert provider.model == "openai/gpt-5-mini"

    def test_default_base_url(self):
        provider = CopilotProvider(api_key="ghp_test")
        assert provider.base_url == "https://models.github.ai/inference"
        assert provider.API_URL == (
            "https://models.github.ai/inference/chat/completions"
        )

    def test_base_url_override_strips_trailing_slash(self):
        provider = CopilotProvider(
            api_key="ghp_test",
            base_url="https://models.example.com/inference/",
        )
        assert provider.base_url == "https://models.example.com/inference"
        assert provider.API_URL == (
            "https://models.example.com/inference/chat/completions"
        )

    def test_namespaced_model_override(self):
        provider = CopilotProvider(
            api_key="ghp_test",
            model="anthropic/claude-sonnet-4",
        )
        assert provider.model == "anthropic/claude-sonnet-4"


class TestCopilotProviderRequests:
    @pytest.mark.asyncio
    async def test_generate_solution_hits_github_models_url(self):
        """generate_solution must POST to the GitHub Models endpoint with
        the PAT as a Bearer token, not to api.openai.com."""
        provider = CopilotProvider(api_key="ghp_test-token")

        post_ctx = _mock_chat_completion_response(content="solution body")
        session = MagicMock()
        session.post = MagicMock(return_value=post_ctx)
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "llm_providers.openai_provider.aiohttp.ClientSession",
            return_value=session_ctx,
        ):
            result = await provider.generate_solution(
                failure_reason="CrashLoopBackOff",
                failure_message="container crashed",
                pod_context={"name": "pod", "namespace": "ns"},
            )

        assert isinstance(result, LLMResponse)
        assert result.provider == "copilot"
        assert result.model == "openai/gpt-5-mini"
        assert result.content == "solution body"

        # Verify URL and auth header.
        assert session.post.call_count == 1
        call_args = session.post.call_args
        assert call_args.args[0] == (
            "https://models.github.ai/inference/chat/completions"
        )
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer ghp_test-token"
        assert headers["Content-Type"] == "application/json"
        # Model slug should be passed through unchanged.
        assert call_args.kwargs["json"]["model"] == "openai/gpt-5-mini"

    @pytest.mark.asyncio
    async def test_generate_raw_hits_github_models_url(self):
        provider = CopilotProvider(
            api_key="ghp_test-token",
            model="anthropic/claude-sonnet-4",
        )

        post_ctx = _mock_chat_completion_response(content="raw body")
        session = MagicMock()
        session.post = MagicMock(return_value=post_ctx)
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "llm_providers.openai_provider.aiohttp.ClientSession",
            return_value=session_ctx,
        ):
            result = await provider.generate_raw(
                system_prompt="system",
                user_prompt="user",
            )

        assert result.content == "raw body"
        assert result.provider == "copilot"
        assert session.post.call_args.args[0] == (
            "https://models.github.ai/inference/chat/completions"
        )
        assert session.post.call_args.kwargs["json"]["model"] == (
            "anthropic/claude-sonnet-4"
        )

    @pytest.mark.asyncio
    async def test_api_error_is_propagated(self):
        provider = CopilotProvider(api_key="ghp_test-token")

        resp = MagicMock()
        resp.status = 401
        resp.text = AsyncMock(return_value="Unauthorized")
        resp.json = AsyncMock(return_value={})
        post_ctx = MagicMock()
        post_ctx.__aenter__ = AsyncMock(return_value=resp)
        post_ctx.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.post = MagicMock(return_value=post_ctx)
        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "llm_providers.openai_provider.aiohttp.ClientSession",
            return_value=session_ctx,
        ):
            with pytest.raises(Exception):
                await provider.generate_solution(
                    failure_reason="CrashLoopBackOff",
                )
