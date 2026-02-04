import aiohttp
import logging
from typing import Dict, List, Optional
from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini provider"""

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return "gemini-2.0-flash"

    async def generate_solution(
        self,
        failure_reason: str,
        failure_message: Optional[str] = None,
        events: List[Dict] = None,
        container_statuses: List[Dict] = None,
        pod_context: Dict = None
    ) -> LLMResponse:
        """Generate solution using Google Gemini API"""
        prompt = self._build_prompt(
            failure_reason, failure_message, events, container_statuses, pod_context
        )

        system_instruction = "You are a Kubernetes expert providing concise, actionable solutions for pod failures."

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "maxOutputTokens": 1000,
                "temperature": 0.1
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Gemini API error {response.status}: {error_text}")
                        raise Exception(f"Gemini API error: {response.status}")

                    data = await response.json()
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                    tokens_used = data.get("usageMetadata", {}).get("totalTokenCount")

                    return LLMResponse(
                        content=content,
                        provider=self.provider_name,
                        model=self.model,
                        tokens_used=tokens_used
                    )

        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            raise

    async def generate_raw(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Generate a raw response with custom prompts using Gemini API"""
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "maxOutputTokens": 2000,
                "temperature": 0.1
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Gemini API error {response.status}: {error_text}")
                        raise Exception(f"Gemini API error: {response.status}")

                    data = await response.json()
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                    tokens_used = data.get("usageMetadata", {}).get("totalTokenCount")

                    return LLMResponse(
                        content=content,
                        provider=self.provider_name,
                        model=self.model,
                        tokens_used=tokens_used
                    )

        except Exception as e:
            logger.error(f"Error calling Gemini API (generate_raw): {e}")
            raise
