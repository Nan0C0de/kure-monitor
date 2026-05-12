"""Tests for services.advice.explainer.LLMExplainer.

We use a fake :class:`LLMProvider` subclass rather than an
``AsyncMock`` for the whole provider, so that the abstract contract
(``provider_name``, ``default_model``, ``generate_raw`` signature) stays
honest at test time.
"""

from typing import Dict, List, Optional
from unittest.mock import patch

import pytest

from llm_providers.base import LLMProvider, LLMResponse
from services.advice.explainer import LLMExplainer
from services.advice.findings import Finding, Severity

# --------------------------------------------------------------------- helpers


def _finding(**overrides) -> Finding:
    fields = dict(
        detector_id="deployment-should-be-daemonset",
        severity=Severity.MEDIUM,
        category="workload-pattern",
        title="Deployment should be a DaemonSet",
        summary="Workload looks per-node; DaemonSet fits better.",
        resource_kind="Deployment",
        resource_name="node-exporter",
        namespace="monitoring",
        evidence={
            "replicas": 3,
            "anti_affinity_topology_key": "kubernetes.io/hostname",
        },
        recommended_change="Convert to DaemonSet and remove the HPA.",
        confidence=0.9,
    )
    fields.update(overrides)
    return Finding(**fields)


class _FakeProvider(LLMProvider):
    """Captures the last (system_prompt, user_prompt) and returns a
    fixed :class:`LLMResponse` -- or raises if ``raise_with`` is set."""

    def __init__(
        self,
        *,
        response_content: str = "## Why this matters\nbecause.",
        raise_with: Optional[Exception] = None,
    ):
        # Skip super().__init__ -- we don't need an API key for tests
        # and ``default_model`` is provided below.
        self.api_key = "fake"
        self.model = self.default_model
        self._response_content = response_content
        self._raise_with = raise_with
        self.calls: List[Dict[str, str]] = []

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def default_model(self) -> str:
        return "fake-model"

    async def generate_solution(
        self,
        failure_reason,
        failure_message=None,
        events=None,
        container_statuses=None,
        pod_context=None,
    ) -> LLMResponse:  # pragma: no cover - not used in these tests
        return LLMResponse(content="", provider=self.provider_name, model=self.model)

    async def generate_raw(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if self._raise_with is not None:
            raise self._raise_with
        return LLMResponse(
            content=self._response_content,
            provider=self.provider_name,
            model=self.model,
        )


# --------------------------------------------------------------------- tests


@pytest.mark.asyncio
class TestExplainerNoProvider:
    async def test_returns_unchanged_when_provider_is_none(self):
        explainer = LLMExplainer(llm_provider=None)
        finding = _finding()
        result = await explainer.explain(finding)

        assert result is finding
        assert result.explanation is None


@pytest.mark.asyncio
class TestExplainerSuccess:
    async def test_sets_explanation_to_response_content(self):
        provider = _FakeProvider(
            response_content="## Why this matters\nLooks per-node."
        )
        explainer = LLMExplainer(llm_provider=provider)
        finding = _finding()

        result = await explainer.explain(finding)

        assert result is not finding  # new instance
        assert result.explanation == "## Why this matters\nLooks per-node."
        # Original is unchanged.
        assert finding.explanation is None

    async def test_trims_whitespace(self):
        provider = _FakeProvider(response_content="   \n\nhello\n\n   ")
        explainer = LLMExplainer(llm_provider=provider)
        result = await explainer.explain(_finding())
        assert result.explanation == "hello"

    async def test_empty_response_leaves_finding_unchanged(self):
        provider = _FakeProvider(response_content="   \n  ")
        explainer = LLMExplainer(llm_provider=provider)
        finding = _finding()

        result = await explainer.explain(finding)

        assert result is finding
        assert result.explanation is None


@pytest.mark.asyncio
class TestExplainerPromptShape:
    async def test_user_prompt_contains_identifying_fields(self):
        provider = _FakeProvider()
        explainer = LLMExplainer(llm_provider=provider)
        finding = _finding()

        await explainer.explain(finding)

        assert len(provider.calls) == 1
        user_prompt = provider.calls[0]["user"]
        assert finding.detector_id in user_prompt
        assert finding.resource_name in user_prompt
        assert finding.namespace in user_prompt

    async def test_user_prompt_omits_confidence_and_explanation(self):
        provider = _FakeProvider()
        explainer = LLMExplainer(llm_provider=provider)
        # Use a confidence value that would clearly appear if leaked.
        finding = _finding(confidence=0.7777)

        await explainer.explain(finding)

        user_prompt = provider.calls[0]["user"]
        # The confidence value must not be in the prompt.
        assert "0.7777" not in user_prompt
        # Nor should the field name itself appear (defensive).
        assert "confidence" not in user_prompt
        # And we never expose `explanation` as a field key.
        assert "explanation" not in user_prompt

    async def test_user_prompt_ends_with_instruction_line(self):
        provider = _FakeProvider()
        explainer = LLMExplainer(llm_provider=provider)

        await explainer.explain(_finding())

        user_prompt = provider.calls[0]["user"]
        assert user_prompt.rstrip().endswith(
            "Explain the finding above following the rules in the system prompt."
        )

    async def test_system_prompt_contains_anti_invention_guardrail(self):
        provider = _FakeProvider()
        explainer = LLMExplainer(llm_provider=provider)

        await explainer.explain(_finding())

        system_prompt = provider.calls[0]["system"]
        # Assert at least one of the load-bearing guardrails is present so
        # nobody can quietly delete them.
        assert ("only facts" in system_prompt) or ("Do NOT invent" in system_prompt)


@pytest.mark.asyncio
class TestExplainerErrorHandling:
    async def test_llm_error_returns_unchanged_and_increments_error_metric(self):
        provider = _FakeProvider(raise_with=RuntimeError("boom"))
        explainer = LLMExplainer(llm_provider=provider)
        finding = _finding()

        # Spy on the counter the same way solution_engine instruments:
        # patch ``LLM_REQUESTS_TOTAL`` in the explainer module namespace
        # and assert the (provider, status="error") label was bumped.
        with patch("services.advice.explainer.LLM_REQUESTS_TOTAL") as mock_counter:
            result = await explainer.explain(finding)

        assert result is finding
        assert result.explanation is None

        # The counter is called as `.labels(provider=..., status="error").inc()`.
        label_calls = mock_counter.labels.call_args_list
        assert any(
            call.kwargs.get("status") == "error"
            and call.kwargs.get("provider") == "fake"
            for call in label_calls
        ), f"expected an error-labelled increment, got: {label_calls}"
        # And `.inc()` was invoked on the resulting labelled metric.
        mock_counter.labels.return_value.inc.assert_called()


@pytest.mark.asyncio
class TestExplainerTruncation:
    async def test_response_longer_than_4000_chars_is_truncated_with_ellipsis(self):
        long_content = "x" * 5000
        provider = _FakeProvider(response_content=long_content)
        explainer = LLMExplainer(llm_provider=provider)

        result = await explainer.explain(_finding())

        assert result.explanation is not None
        assert len(result.explanation) == 4000
        assert result.explanation.endswith("...")
