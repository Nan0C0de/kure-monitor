import aiohttp
import json
import logging
from typing import Dict, List, Optional
from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """Groq Cloud provider"""
    
    @property
    def provider_name(self) -> str:
        return "groq"
    
    @property
    def default_model(self) -> str:
        return "llama-3.1-8b-instant"
    
    async def generate_solution(
        self,
        failure_reason: str,
        failure_message: Optional[str] = None,
        events: List[Dict] = None,
        container_statuses: List[Dict] = None,
        pod_context: Dict = None
    ) -> LLMResponse:
        """Generate solution using Groq API"""
        prompt = self._build_prompt(
            failure_reason, failure_message, events, container_statuses, pod_context
        )
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Groq API error {response.status}: {error_text}")
                        raise Exception(f"Groq API error: {response.status}")
                    
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
            logger.error(f"Error calling Groq API: {e}")
            # Fallback to basic solution
            return LLMResponse(
                content=f"AI solution temporarily unavailable (Groq API error). \n\nBasic troubleshooting for {failure_reason}:\n• Run 'kubectl describe pod <pod-name>' for detailed status\n• Check 'kubectl logs <pod-name>' for application errors\n• Verify resource limits and image accessibility",
                provider=self.provider_name,
                model=self.model
            )