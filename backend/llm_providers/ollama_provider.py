import aiohttp
import logging
from typing import Dict, List, Optional
from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider (OpenAI-compatible API)"""

    def __init__(self, api_key: str, model: str = None, base_url: str = None):
        self.base_url = (base_url or "http://ollama:11434").rstrip("/")
        super().__init__(api_key=api_key, model=model)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def default_model(self) -> str:
        return "llama3.2"

    async def generate_solution(
        self,
        failure_reason: str,
        failure_message: Optional[str] = None,
        events: List[Dict] = None,
        container_statuses: List[Dict] = None,
        pod_context: Dict = None
    ) -> LLMResponse:
        """Generate solution using Ollama API"""
        prompt = self._build_prompt(
            failure_reason, failure_message, events, container_statuses, pod_context
        )

        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a Kubernetes expert providing concise, actionable solutions for pod failures."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.1
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama API error {response.status}: {error_text}")
                        raise Exception(f"Ollama API error: {response.status}")

                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    tokens_used = data.get("usage", {}).get("total_tokens")

                    return LLMResponse(
                        content=content,
                        provider=self.provider_name,
                        model=self.model,
                        tokens_used=tokens_used
                    )

        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            raise

    async def generate_raw(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Generate a raw response with custom prompts using Ollama API"""
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 2000,
            "temperature": 0.1
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama API error {response.status}: {error_text}")
                        raise Exception(f"Ollama API error: {response.status}")

                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    tokens_used = data.get("usage", {}).get("total_tokens")

                    return LLMResponse(
                        content=content,
                        provider=self.provider_name,
                        model=self.model,
                        tokens_used=tokens_used
                    )

        except Exception as e:
            logger.error(f"Error calling Ollama API (generate_raw): {e}")
            raise
