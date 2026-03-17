import pytest
from unittest.mock import AsyncMock, Mock, patch
from services.solution_engine import SolutionEngine
from llm_providers.base import LLMResponse


class TestGeneratePodFix:
    """Tests for the generate_pod_fix method on SolutionEngine."""

    @pytest.fixture
    def solution_engine(self):
        return SolutionEngine()

    @pytest.fixture
    def solution_engine_with_llm(self):
        engine = SolutionEngine()
        engine.llm_provider = Mock()
        engine.llm_provider.provider_name = "openai"
        return engine

    @pytest.mark.asyncio
    async def test_generate_pod_fix_no_llm(self, solution_engine):
        """Falls back when no LLM is configured."""
        result = await solution_engine.generate_pod_fix(
            manifest="apiVersion: v1\nkind: Pod",
            failure_reason="ImagePullBackOff",
            failure_message="Failed to pull image",
            events=[],
            solution="Check image name"
        )

        assert result["is_fallback"] is True
        assert result["fixed_manifest"] == ""
        assert "No LLM configured" in result["explanation"]

    @pytest.mark.asyncio
    async def test_generate_pod_fix_no_manifest(self, solution_engine_with_llm):
        """Falls back when manifest is empty."""
        result = await solution_engine_with_llm.generate_pod_fix(
            manifest="",
            failure_reason="CrashLoopBackOff",
            failure_message="Container crashed",
            events=[],
            solution="Check logs"
        )

        assert result["is_fallback"] is True
        assert result["fixed_manifest"] == ""

    @pytest.mark.asyncio
    async def test_generate_pod_fix_success(self, solution_engine_with_llm):
        """Successfully generates a fixed manifest."""
        llm_response = LLMResponse(
            content="""```yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
  - name: app
    image: nginx:1.25
```
---EXPLANATION---
Changed image tag from 'nonexistent:latest' to 'nginx:1.25' to fix ImagePullBackOff.""",
            provider="openai",
            model="gpt-4.1-mini",
        )

        solution_engine_with_llm.llm_provider.generate_raw = AsyncMock(return_value=llm_response)

        result = await solution_engine_with_llm.generate_pod_fix(
            manifest="apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod\nspec:\n  containers:\n  - name: app\n    image: nonexistent:latest",
            failure_reason="ImagePullBackOff",
            failure_message="Failed to pull image 'nonexistent:latest'",
            events=[{"type": "Warning", "reason": "Failed", "message": "Failed to pull image"}],
            solution="Check if the image exists in the registry"
        )

        assert result["is_fallback"] is False
        assert "nginx:1.25" in result["fixed_manifest"]
        assert "image tag" in result["explanation"].lower() or "Changed" in result["explanation"]

    @pytest.mark.asyncio
    async def test_generate_pod_fix_llm_error(self, solution_engine_with_llm):
        """Falls back when LLM call fails."""
        solution_engine_with_llm.llm_provider.generate_raw = AsyncMock(
            side_effect=Exception("API timeout")
        )

        result = await solution_engine_with_llm.generate_pod_fix(
            manifest="apiVersion: v1\nkind: Pod",
            failure_reason="CrashLoopBackOff",
            failure_message="Container crashed",
            events=[],
            solution="Check logs"
        )

        assert result["is_fallback"] is True
        assert "Failed to generate fix" in result["explanation"]

    @pytest.mark.asyncio
    async def test_generate_pod_fix_no_yaml_in_response(self, solution_engine_with_llm):
        """Handles LLM response with no parseable YAML block."""
        llm_response = LLMResponse(
            content="I cannot fix this manifest because the issue requires external resources.",
            provider="openai",
            model="gpt-4.1-mini",
        )
        solution_engine_with_llm.llm_provider.generate_raw = AsyncMock(return_value=llm_response)

        result = await solution_engine_with_llm.generate_pod_fix(
            manifest="apiVersion: v1\nkind: Pod",
            failure_reason="Pending",
            failure_message="Insufficient cpu",
            events=[],
            solution="Scale cluster"
        )

        assert result["is_fallback"] is False
        assert result["fixed_manifest"] == ""
        # The whole response becomes the explanation when no structured output
        assert "cannot fix" in result["explanation"].lower()

    # --- _format_events_for_prompt ---

    def test_format_events_for_prompt_empty(self, solution_engine):
        """Returns fallback text for empty events list."""
        result = solution_engine._format_events_for_prompt([])
        assert result == "No events available"

    def test_format_events_for_prompt_none(self, solution_engine):
        """Returns fallback text for None events."""
        result = solution_engine._format_events_for_prompt(None)
        assert result == "No events available"

    def test_format_events_for_prompt_dict_events(self, solution_engine):
        """Formats dict-style events."""
        events = [
            {"type": "Warning", "reason": "Failed", "message": "Image pull failed"},
            {"type": "Normal", "reason": "Pulling", "message": "Pulling image"},
        ]
        result = solution_engine._format_events_for_prompt(events)
        assert "Warning Failed" in result
        assert "Image pull failed" in result
        assert "Normal Pulling" in result
