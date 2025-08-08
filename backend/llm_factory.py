import os
import logging
from typing import Optional
from llm_providers import (
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    GroqProvider
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
    }
    
    @classmethod
    def create_provider(
        self,
        provider_name: str,
        api_key: str,
        model: Optional[str] = None
    ) -> LLMProvider:
        """Create an LLM provider instance"""
        provider_name = provider_name.lower()
        
        if provider_name not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider: {provider_name}. "
                f"Supported providers: {list(self.SUPPORTED_PROVIDERS.keys())}"
            )
        
        provider_class = self.SUPPORTED_PROVIDERS[provider_name]
        return provider_class(api_key=api_key, model=model)
    
    @classmethod
    def create_from_env(self) -> Optional[LLMProvider]:
        """Create LLM provider from environment variables"""
        provider_name = os.getenv("KURE_LLM_PROVIDER")
        api_key = os.getenv("KURE_LLM_API_KEY")
        model = os.getenv("KURE_LLM_MODEL")
        
        if not provider_name or not api_key:
            logger.warning(
                "LLM provider not configured. Set KURE_LLM_PROVIDER and KURE_LLM_API_KEY "
                "environment variables to enable AI-powered solutions."
            )
            return None
        
        try:
            return self.create_provider(provider_name, api_key, model)
        except Exception as e:
            logger.error(f"Failed to create LLM provider: {e}")
            return None
    
    @classmethod
    def get_supported_providers(self) -> list:
        """Get list of supported provider names"""
        return list(self.SUPPORTED_PROVIDERS.keys())