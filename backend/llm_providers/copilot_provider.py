import logging

from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class CopilotProvider(OpenAIProvider):
    """GitHub Models ("GitHub Copilot") provider.

    GitHub Models exposes an OpenAI-compatible chat/completions API at a
    different base URL, authenticated with a GitHub Personal Access Token
    passed as a Bearer token. Because the request/response shape mirrors
    OpenAI exactly, we delegate all behavior to :class:`OpenAIProvider`
    and only override the endpoint URL, provider name, and default model.

    Models use a namespaced slug (e.g. ``openai/gpt-5-mini``,
    ``anthropic/claude-sonnet-4``).
    """

    DEFAULT_BASE_URL = "https://models.github.ai/inference"

    def __init__(self, api_key: str, model: str = None, base_url: str = None):
        # Allow callers to override the base URL (e.g. for enterprise /
        # proxy endpoints); otherwise use the public GitHub Models URL.
        resolved_base = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        # Set API_URL per-instance so each provider instance can target a
        # different base URL without mutating the class attribute.
        self.API_URL = f"{resolved_base}/chat/completions"
        super().__init__(api_key=api_key, model=model, base_url=resolved_base)

    @property
    def provider_name(self) -> str:
        return "copilot"

    @property
    def default_model(self) -> str:
        return "openai/gpt-5-mini"
