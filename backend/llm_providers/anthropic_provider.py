import aiohttp
import json
import logging
from typing import Dict, List, Optional
from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider"""
    
    @property
    def provider_name(self) -> str:
        return "anthropic"
    
    @property
    def default_model(self) -> str:
        return "claude-3-haiku-20240307"
    
    async def generate_solution(
        self,
        failure_reason: str,
        failure_message: Optional[str] = None,
        events: List[Dict] = None,
        container_statuses: List[Dict] = None,
        pod_context: Dict = None
    ) -> LLMResponse:
        """Generate solution using Anthropic Claude API"""
        prompt = self._build_prompt(
            failure_reason, failure_message, events, container_statuses, pod_context
        )
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": self.model,
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": f"You are a Kubernetes expert providing concise, actionable solutions for pod failures.\n\n{prompt}"
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Anthropic API error {response.status}: {error_text}")
                        raise Exception(f"Anthropic API error: {response.status}")
                    
                    data = await response.json()
                    content = data["content"][0]["text"]
                    tokens_used = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
                    
                    return LLMResponse(
                        content=content,
                        provider=self.provider_name,
                        model=self.model,
                        tokens_used=tokens_used
                    )
        
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            # Fallback to basic solution
            return LLMResponse(
                content=f"Failed to generate AI solution for {failure_reason}. Please check pod logs and events manually.",
                provider=self.provider_name,
                model=self.model
            )