from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from LLM provider"""
    content: str
    provider: str
    model: str
    tokens_used: Optional[int] = None
    cost: Optional[float] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    def __init__(self, api_key: str, model: str = None, base_url: str = None):
        self.api_key = api_key
        self.model = model or self.default_model
        if base_url is not None:
            self.base_url = base_url
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider"""
        pass
    
    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for this provider"""
        pass
    
    @abstractmethod
    async def generate_solution(
        self,
        failure_reason: str,
        failure_message: Optional[str] = None,
        events: List[Dict] = None,
        container_statuses: List[Dict] = None,
        pod_context: Dict = None
    ) -> LLMResponse:
        """Generate a solution for the Kubernetes issue"""
        pass

    @abstractmethod
    async def generate_raw(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> LLMResponse:
        """Generate a raw response with custom system and user prompts"""
        pass
    
    def _build_prompt(
        self,
        failure_reason: str,
        failure_message: Optional[str] = None,
        events: List[Dict] = None,
        container_statuses: List[Dict] = None,
        pod_context: Dict = None
    ) -> str:
        """Build the prompt for the LLM"""
        prompt = f"""You are a Kubernetes expert helping to diagnose and fix pod failures.

Pod Failure Details:
- Failure Reason: {failure_reason}"""
        
        if failure_message:
            prompt += f"\n- Failure Message: {failure_message}"
        
        if pod_context:
            prompt += f"\n- Pod Name: {pod_context.get('name', 'Unknown')}"
            prompt += f"\n- Namespace: {pod_context.get('namespace', 'Unknown')}"
            prompt += f"\n- Image: {pod_context.get('image', 'Unknown')}"
        
        if events:
            prompt += "\n\nRecent Events:"
            for event in events[-5:]:  # Last 5 events
                prompt += f"\n- {event.get('type', 'Unknown')} {event.get('reason', '')}: {event.get('message', '')}"
        
        if container_statuses:
            prompt += "\n\nContainer Statuses:"
            for status in container_statuses:
                prompt += f"\n- {status.get('name', 'Unknown')}: restart_count={status.get('restart_count', 0)}"
                if status.get('last_state'):
                    prompt += f", last_state={status['last_state']}"
        
        prompt += """

Please provide a clear, well-formatted response. Use proper line breaks and formatting:

## What's Wrong
Explain the issue in simple terms.

## How to Fix It
1. First step - clear explanation
2. Second step - clear explanation  
3. Additional steps as needed

## Prevention Tips
- Key prevention measure 1
- Key prevention measure 2
- Additional tips as needed

## Useful Commands
- `kubectl describe pod <pod-name>` - Shows detailed pod status
- `kubectl logs <pod-name>` - Shows container logs
- Additional relevant commands

IMPORTANT: Use proper line breaks between sections and list items. Keep explanations clear and concise."""
        
        return prompt