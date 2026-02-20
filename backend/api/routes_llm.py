from fastapi import APIRouter, HTTPException
import logging

from models.models import (
    LLMConfigCreate, LLMConfigResponse, LLMConfigStatus,
)
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_llm_router(deps: RouterDeps) -> APIRouter:
    """LLM status/config/test routes."""
    router = APIRouter()
    db = deps.db
    solution_engine = deps.solution_engine
    websocket_manager = deps.websocket_manager

    # --- LLM Configuration ---

    @router.get("/admin/llm/status", response_model=LLMConfigStatus)
    async def get_llm_status():
        """Get current LLM configuration status"""
        try:
            db_config = await db.get_llm_config()
            if db_config:
                return LLMConfigStatus(
                    configured=True,
                    provider=db_config['provider'],
                    model=db_config['model'],
                    source="database"
                )

            return LLMConfigStatus(configured=False)
        except Exception as e:
            logger.error(f"Error getting LLM status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/llm/config", response_model=LLMConfigResponse)
    async def save_llm_config(config: LLMConfigCreate):
        """Save LLM configuration"""
        try:
            valid_providers = ["openai", "anthropic", "claude", "groq", "groq_cloud", "gemini", "google", "ollama"]
            if config.provider.lower() not in valid_providers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid provider. Supported: {', '.join(valid_providers)}"
                )

            result = await db.save_llm_config(
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url
            )

            await solution_engine.reinitialize_llm(
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url
            )

            logger.info(f"LLM configuration saved: provider={config.provider}")

            return LLMConfigResponse(
                id=result['id'],
                provider=result['provider'],
                model=result['model'],
                configured=True,
                created_at=result['created_at'],
                updated_at=result['updated_at']
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error saving LLM config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/admin/llm/config")
    async def delete_llm_config():
        """Delete LLM configuration (revert to rule-based solutions)"""
        try:
            deleted = await db.delete_llm_config()

            solution_engine.llm_provider = None

            if deleted:
                return {"message": "LLM configuration deleted"}
            else:
                return {"message": "No LLM configuration to delete"}
        except Exception as e:
            logger.error(f"Error deleting LLM config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/llm/test")
    async def test_llm_config(config: LLMConfigCreate):
        """Test LLM configuration without saving"""
        try:
            from services.llm_factory import LLMFactory

            provider = LLMFactory.create_provider(
                provider_name=config.provider.lower(),
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url
            )

            test_response = await provider.generate_solution(
                failure_reason="CrashLoopBackOff",
                failure_message="Test connection to LLM provider",
                pod_context={"name": "test-pod", "namespace": "test"},
                events=[{"type": "Warning", "reason": "BackOff", "message": "Back-off restarting container"}]
            )

            if test_response and test_response.content and len(test_response.content) > 10:
                return {"success": True, "message": "LLM connection successful"}
            else:
                return {"success": False, "message": "LLM returned empty response"}
        except Exception as e:
            logger.error(f"Error testing LLM config: {e}")
            return {"success": False, "message": str(e)}

    return router
