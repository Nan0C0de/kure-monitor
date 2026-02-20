import logging
from typing import Optional
from llm_providers import (
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    GroqProvider,
    GeminiProvider,
    OllamaProvider
)

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM providers based on configuration"""

    SUPPORTED_PROVIDERS = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "claude": AnthropicProvider,  # Alias for anthropic
        "groq": GroqProvider,
        "groq_cloud": GroqProvider,  # Alias for groq
        "gemini": GeminiProvider,
        "google": GeminiProvider,  # Alias for gemini
        "ollama": OllamaProvider,
    }

    @classmethod
    def create_provider(
        self,
        provider_name: str,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ) -> LLMProvider:
        """Create an LLM provider instance"""
        provider_name = provider_name.lower()

        if provider_name not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider: {provider_name}. "
                f"Supported providers: {list(self.SUPPORTED_PROVIDERS.keys())}"
            )

        provider_class = self.SUPPORTED_PROVIDERS[provider_name]
        kwargs = {"api_key": api_key, "model": model}
        if base_url:
            kwargs["base_url"] = base_url
        return provider_class(**kwargs)

    @classmethod
    def get_supported_providers(self) -> list:
        """Get list of supported provider names"""
        return list(self.SUPPORTED_PROVIDERS.keys())