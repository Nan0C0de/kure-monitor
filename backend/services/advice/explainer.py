"""LLMExplainer -- turns a :class:`Finding` into a plain-English explanation.

The explainer is the *only* place where LLM output touches a Finding. Its
prompt is engineered to prevent the model from fabricating Kubernetes
facts that are not present in the finding's ``evidence`` dict.

The explainer NEVER raises:
* No provider configured -> finding returned unchanged.
* LLM call fails -> finding returned unchanged, error counted in
  :data:`services.prometheus_metrics.LLM_REQUESTS_TOTAL`.
* Empty response -> finding returned unchanged.

LLM calls are instrumented with the same Prometheus metrics
(``LLM_REQUESTS_TOTAL`` / ``LLM_REQUEST_DURATION_SECONDS``) that
:mod:`services.solution_engine` uses, so dashboards aggregate the two
features under one provider label.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from llm_providers.base import LLMProvider
from services.prometheus_metrics import (
    LLM_REQUEST_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
)

from .findings import Finding

logger = logging.getLogger(__name__)


# Hard cap on the stored explanation length. The LLM is asked to stay
# under 180 words; this is a defensive truncation if it misbehaves.
_MAX_EXPLANATION_CHARS = 4000
_ELLIPSIS = "..."


_SYSTEM_PROMPT = (
    "You are explaining ONE Kubernetes architectural finding to an engineer.\n"
    "\n"
    "You MUST use only facts that appear in the Finding JSON below. Do NOT "
    "invent replica counts, image names, container names, ports, labels, or "
    "any field not present in `evidence`.\n"
    "\n"
    "If a fact you would want to mention is not in the evidence, omit it or "
    "say 'not specified'. Do NOT guess.\n"
    "\n"
    "Do NOT recommend changes beyond what the Finding's `recommended_change` "
    "field already says -- you may rephrase it, but do not add new "
    "recommendations.\n"
    "\n"
    "Keep the explanation under 180 words.\n"
    "\n"
    "Output three sections with these exact headers: `## Why this matters`, "
    "`## Evidence`, `## Recommended change`."
)


# Fields included in the user prompt's redacted finding dump. ``explanation``
# is excluded (would always be ``None`` at this point and inviting it back
# in would let the LLM echo prior guesses). ``confidence`` is excluded
# because it isn't useful to the LLM and invites speculation about
# certainty.
_PROMPT_FIELDS = (
    "detector_id",
    "category",
    "severity",
    "resource_kind",
    "resource_name",
    "namespace",
    "title",
    "summary",
    "evidence",
    "recommended_change",
)


class LLMExplainer:
    """Adds an LLM-generated narrative to a :class:`Finding`."""

    def __init__(self, llm_provider: Optional[any]):
        self.llm_provider = llm_provider

    async def explain(self, finding: Finding) -> Finding:
        """Return a Finding with :attr:`Finding.explanation` populated.

        Supports a single LLMProvider or a list of (id, provider) tuples for failover.
        On any failure path -- no provider, LLM error, empty response --
        the original finding is returned unchanged. Never raises.
        """
        if not self.llm_provider:
            return finding

        # Normalize into list of providers for failover support
        if isinstance(self.llm_provider, list):
            providers = [p[1] if isinstance(p, tuple) else p for p in self.llm_provider]
        else:
            providers = [self.llm_provider]

        user_prompt = self._build_user_prompt(finding)

        for provider in providers:
            if not provider:
                continue
            provider_name = provider.provider_name
            start_time = time.monotonic()

            try:
                llm_response = await provider.generate_raw(
                    _SYSTEM_PROMPT, user_prompt
                )

                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="success").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                    duration
                )

                content = (llm_response.content or "").strip()
                if not content:
                    continue

                if len(content) > _MAX_EXPLANATION_CHARS:
                    content = content[: _MAX_EXPLANATION_CHARS - len(_ELLIPSIS)] + _ELLIPSIS

                return finding.with_explanation(content)

            except Exception as e:
                duration = time.monotonic() - start_time
                LLM_REQUESTS_TOTAL.labels(provider=provider_name, status="error").inc()
                LLM_REQUEST_DURATION_SECONDS.labels(provider=provider_name).observe(
                    duration
                )
                logger.warning(
                    "LLM explanation generation failed with provider %s for finding %s/%s: %s",
                    provider_name,
                    finding.detector_id,
                    finding.resource_name,
                    e,
                )

        return finding

    @staticmethod
    def _build_user_prompt(finding: Finding) -> str:
        """Assemble the user prompt: a redacted JSON dump of the finding
        followed by a literal instruction line."""
        payload = {
            "detector_id": finding.detector_id,
            "category": finding.category,
            "severity": finding.severity.value,
            "resource_kind": finding.resource_kind,
            "resource_name": finding.resource_name,
            "namespace": finding.namespace,
            "title": finding.title,
            "summary": finding.summary,
            "evidence": finding.evidence,
            "recommended_change": finding.recommended_change,
        }
        # ``sort_keys=False`` keeps the field order deterministic and
        # matching :data:`_PROMPT_FIELDS` ordering for easier eyeballing.
        as_json = json.dumps(payload, indent=2, default=str)
        return (
            "```json\n"
            f"{as_json}\n"
            "```\n"
            "\n"
            "Explain the finding above following the rules in the system prompt."
        )
