import pytest
from services.llm_factory import LLMFactory


class TestLLMFactory:

    def test_create_openai_provider(self):
        """Test creating OpenAI provider"""
        provider = LLMFactory.create_provider(
            provider_name='openai',
            api_key='test-key',
            model='gpt-5-mini'
        )
        assert provider is not None
        assert provider.provider_name == "openai"
        assert provider.model == "gpt-5-mini"

    def test_openai_default_model(self):
        """OpenAI default model should be the latest GA mini model."""
        provider = LLMFactory.create_provider(
            provider_name='openai',
            api_key='test-key'
        )
        assert provider.model == "gpt-5-mini"

    def test_create_anthropic_provider(self):
        """Test creating Anthropic provider"""
        provider = LLMFactory.create_provider(
            provider_name='anthropic',
            api_key='test-key',
            model='claude-sonnet-4-5'
        )
        assert provider is not None
        assert provider.provider_name == "anthropic"
        assert provider.model == "claude-sonnet-4-5"

    def test_create_groq_provider(self):
        """Test creating Groq provider"""
        provider = LLMFactory.create_provider(
            provider_name='groq',
            api_key='test-key'
        )
        assert provider is not None
        assert provider.provider_name == "groq"

    def test_create_provider_with_alias_claude(self):
        """Test creating provider with claude alias"""
        provider = LLMFactory.create_provider(
            provider_name='claude',
            api_key='test-key'
        )
        assert provider is not None
        assert provider.provider_name == "anthropic"

    def test_create_provider_with_alias_groq_cloud(self):
        """Test creating provider with groq_cloud alias"""
        provider = LLMFactory.create_provider(
            provider_name='groq_cloud',
            api_key='test-key'
        )
        assert provider is not None
        assert provider.provider_name == "groq"

    def test_create_gemini_provider(self):
        """Test creating Gemini provider"""
        provider = LLMFactory.create_provider(
            provider_name='gemini',
            api_key='test-key',
            model='gemini-2.5-flash'
        )
        assert provider is not None
        assert provider.provider_name == "gemini"
        assert provider.model == "gemini-2.5-flash"

    def test_create_provider_with_alias_google(self):
        """Test creating provider with google alias"""
        provider = LLMFactory.create_provider(
            provider_name='google',
            api_key='test-key'
        )
        assert provider is not None
        assert provider.provider_name == "gemini"

    def test_invalid_provider(self):
        """Test with invalid provider name"""
        with pytest.raises(ValueError) as exc_info:
            LLMFactory.create_provider(
                provider_name='invalid',
                api_key='test-key'
            )
        assert "Unsupported provider" in str(exc_info.value)

    def test_get_supported_providers(self):
        """Test getting list of supported providers"""
        providers = LLMFactory.get_supported_providers()
        assert 'openai' in providers
        assert 'anthropic' in providers
        assert 'groq' in providers
        assert 'claude' in providers
        assert 'groq_cloud' in providers
        assert 'gemini' in providers
        assert 'google' in providers
        assert 'copilot' in providers
        assert 'github' in providers
        assert 'github_models' in providers

    def test_create_copilot_provider(self):
        """Test creating GitHub Models (Copilot) provider"""
        provider = LLMFactory.create_provider(
            provider_name='copilot',
            api_key='ghp_test-token'
        )
        assert provider is not None
        assert provider.provider_name == "copilot"
        # Default model should be the namespaced GitHub Models slug.
        assert provider.model == "openai/gpt-5-mini"

    def test_create_copilot_provider_with_alias_github(self):
        """Test creating copilot via 'github' alias"""
        provider = LLMFactory.create_provider(
            provider_name='github',
            api_key='ghp_test-token'
        )
        assert provider is not None
        assert provider.provider_name == "copilot"

    def test_create_copilot_provider_with_alias_github_models(self):
        """Test creating copilot via 'github_models' alias"""
        provider = LLMFactory.create_provider(
            provider_name='github_models',
            api_key='ghp_test-token'
        )
        assert provider is not None
        assert provider.provider_name == "copilot"

    def test_copilot_base_url_default(self):
        """Copilot provider should target the GitHub Models inference URL."""
        provider = LLMFactory.create_provider(
            provider_name='copilot',
            api_key='ghp_test-token'
        )
        assert provider.base_url == "https://models.github.ai/inference"
        assert provider.API_URL == "https://models.github.ai/inference/chat/completions"

    def test_copilot_base_url_override(self):
        """Callers can override the base URL (e.g. enterprise endpoints)."""
        provider = LLMFactory.create_provider(
            provider_name='copilot',
            api_key='ghp_test-token',
            base_url='https://models.example.com/inference/'
        )
        # Trailing slash should be stripped.
        assert provider.base_url == "https://models.example.com/inference"
        assert provider.API_URL == "https://models.example.com/inference/chat/completions"

    def test_copilot_accepts_namespaced_model(self):
        """Copilot provider accepts namespaced model slugs."""
        provider = LLMFactory.create_provider(
            provider_name='copilot',
            api_key='ghp_test-token',
            model='anthropic/claude-sonnet-4'
        )
        assert provider.model == "anthropic/claude-sonnet-4"
