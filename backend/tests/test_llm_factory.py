import pytest
from services.llm_factory import LLMFactory


class TestLLMFactory:

    def test_create_openai_provider(self):
        """Test creating OpenAI provider"""
        provider = LLMFactory.create_provider(
            provider_name='openai',
            api_key='test-key',
            model='gpt-4.1-mini'
        )
        assert provider is not None
        assert provider.provider_name == "openai"
        assert provider.model == "gpt-4.1-mini"

    def test_create_anthropic_provider(self):
        """Test creating Anthropic provider"""
        provider = LLMFactory.create_provider(
            provider_name='anthropic',
            api_key='test-key',
            model='claude-sonnet-4-20250514'
        )
        assert provider is not None
        assert provider.provider_name == "anthropic"

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
            model='gemini-2.0-flash'
        )
        assert provider is not None
        assert provider.provider_name == "gemini"
        assert provider.model == "gemini-2.0-flash"

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
