import pytest
from unittest.mock import Mock, patch
from services.llm_factory import LLMFactory


class TestLLMFactory:
    
    def test_create_openai_provider(self):
        """Test creating OpenAI provider"""
        with patch.dict('os.environ', {
            'KURE_LLM_PROVIDER': 'openai',
            'KURE_LLM_API_KEY': 'test-key',
            'KURE_LLM_MODEL': 'gpt-4o-mini'
        }):
            provider = LLMFactory.create_from_env()
            assert provider is not None
            assert provider.provider_name == "openai"
            assert provider.model == "gpt-4o-mini"

    def test_create_anthropic_provider(self):
        """Test creating Anthropic provider"""
        with patch.dict('os.environ', {
            'KURE_LLM_PROVIDER': 'anthropic',
            'KURE_LLM_API_KEY': 'test-key',
            'KURE_LLM_MODEL': 'claude-3-haiku-20240307'
        }):
            provider = LLMFactory.create_from_env()
            assert provider is not None
            assert provider.provider_name == "anthropic"

    def test_create_groq_provider(self):
        """Test creating Groq provider"""
        with patch.dict('os.environ', {
            'KURE_LLM_PROVIDER': 'groq',
            'KURE_LLM_API_KEY': 'test-key'
        }):
            provider = LLMFactory.create_from_env()
            assert provider is not None
            assert provider.provider_name == "groq"

    def test_no_provider_configured(self):
        """Test when no LLM provider is configured"""
        with patch.dict('os.environ', {}, clear=True):
            provider = LLMFactory.create_from_env()
            assert provider is None

    def test_missing_api_key(self):
        """Test when provider is set but API key is missing"""
        with patch.dict('os.environ', {
            'KURE_LLM_PROVIDER': 'openai'
            # No API key
        }):
            provider = LLMFactory.create_from_env()
            assert provider is None

    def test_invalid_provider(self):
        """Test with invalid provider name"""
        with patch.dict('os.environ', {
            'KURE_LLM_PROVIDER': 'invalid',
            'KURE_LLM_API_KEY': 'test-key'
        }):
            provider = LLMFactory.create_from_env()
            assert provider is None