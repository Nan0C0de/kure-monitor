from fastapi import APIRouter, Depends, HTTPException
import logging

from models.models import (
    LLMConfigCreate,
    LLMConfigResponse,
    LLMConfigStatus,
    LLMConfigItemCreate,
    LLMConfigItemUpdate,
    LLMConfigItemResponse,
    LLMConfigsListResponse,
    LLMAvailableItem,
    LLMCustomInstructionsUpdate,
    LLMCustomInstructionsResponse,
)
from .auth import require_write
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_llm_router(deps: RouterDeps) -> APIRouter:
    """LLM status/config/test routes."""
    router = APIRouter(dependencies=[Depends(require_write)])
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
                    provider=db_config["provider"],
                    model=db_config["model"],
                    base_url=db_config.get("base_url"),
                    source="database",
                )

            return LLMConfigStatus(configured=False)
        except Exception as e:
            logger.error(f"Error getting LLM status: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/admin/llm/config", response_model=LLMConfigResponse)
    async def save_llm_config(config: LLMConfigCreate):
        """Save LLM configuration"""
        try:
            from services.llm_factory import LLMFactory
            valid_providers = list(LLMFactory.SUPPORTED_PROVIDERS.keys())
            if config.provider.lower() not in valid_providers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid provider. Supported: {', '.join(valid_providers)}",
                )

            result = await db.save_llm_config(
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
            )

            await solution_engine.reinitialize_llm(
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
            )

            logger.info(f"LLM configuration saved: provider={config.provider}")

            return LLMConfigResponse(
                id=result["id"],
                provider=result["provider"],
                model=result["model"],
                configured=True,
                created_at=result["created_at"],
                updated_at=result["updated_at"],
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error saving LLM config: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.delete("/admin/llm/config")
    async def delete_llm_config():
        """Delete LLM configuration (revert to rule-based solutions)"""
        try:
            deleted = await db.delete_llm_config()

            await solution_engine._swap_llm_provider(None)

            if deleted:
                return {"message": "LLM configuration deleted"}
            else:
                return {"message": "No LLM configuration to delete"}
        except Exception as e:
            logger.error(f"Error deleting LLM config: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/admin/llm/test")
    async def test_llm_config(config: LLMConfigCreate):
        """Test LLM configuration without saving"""
        try:
            from services.llm_factory import LLMFactory

            provider = LLMFactory.create_provider(
                provider_name=config.provider.lower(),
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
            )

            try:
                test_response = await provider.generate_solution(
                    failure_reason="CrashLoopBackOff",
                    failure_message="Test connection to LLM provider",
                    pod_context={"name": "test-pod", "namespace": "test"},
                    events=[
                        {
                            "type": "Warning",
                            "reason": "BackOff",
                            "message": "Back-off restarting container",
                        }
                    ],
                )

                if (
                    test_response
                    and test_response.content
                    and len(test_response.content) > 10
                ):
                    return {"success": True, "message": "LLM connection successful"}
                else:
                    return {"success": False, "message": "LLM returned empty response"}
            finally:
                await provider.close()
        except Exception as e:
            logger.error(f"Error testing LLM config: {e}")
            return {"success": False, "message": str(e)}

    # --- Multi-LLM Management Routes ---

    @router.get("/admin/llm/configs", response_model=LLMConfigsListResponse)
    async def get_all_llm_configs():
        """Get all registered LLM configurations"""
        try:
            configs = await db.get_all_llm_configs()
            default_config = await db.get_default_llm_config()
            return LLMConfigsListResponse(
                configs=[
                    LLMConfigItemResponse(
                        id=c["id"],
                        name=c["name"],
                        provider=c["provider"],
                        model=c["model"],
                        base_url=c["base_url"],
                        is_default=c["is_default"],
                        is_active=c["is_active"],
                        created_at=c["created_at"],
                        updated_at=c["updated_at"],
                    )
                    for c in configs
                ],
                default_config_id=default_config["id"] if default_config else None,
            )
        except Exception as e:
            logger.error(f"Error getting all LLM configs: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/admin/llm/configs", response_model=LLMConfigItemResponse)
    async def create_llm_config_item(config: LLMConfigItemCreate):
        """Register a new LLM provider configuration"""
        try:
            from services.llm_factory import LLMFactory

            valid_providers = list(LLMFactory.SUPPORTED_PROVIDERS.keys())
            if config.provider.lower() not in valid_providers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid provider. Supported: {', '.join(valid_providers)}",
                )

            name = config.name.strip() if config.name else f"{config.provider.capitalize()}"

            result = await db.save_llm_config_item(
                name=name,
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model,
                base_url=config.base_url,
                is_default=bool(config.is_default),
            )

            await solution_engine.reload_providers()
            logger.info(f"Registered new LLM config '{name}' ({config.provider})")

            return LLMConfigItemResponse(
                id=result["id"],
                name=result["name"],
                provider=result["provider"],
                model=result["model"],
                base_url=result["base_url"],
                is_default=result["is_default"],
                is_active=result["is_active"],
                created_at=result["created_at"],
                updated_at=result["updated_at"],
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error registering LLM config: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.put("/admin/llm/configs/{config_id}", response_model=LLMConfigItemResponse)
    async def update_llm_config_item(config_id: int, update: LLMConfigItemUpdate):
        """Update an existing registered LLM configuration"""
        try:
            updated = await db.update_llm_config_item(
                config_id=config_id,
                name=update.name,
                provider=update.provider.lower() if update.provider else None,
                api_key=update.api_key,
                model=update.model,
                base_url=update.base_url,
                is_default=update.is_default,
                is_active=update.is_active,
            )
            if not updated:
                raise HTTPException(status_code=404, detail="LLM configuration not found")

            await solution_engine.reload_providers()
            logger.info(f"Updated LLM config ID={config_id}")

            return LLMConfigItemResponse(
                id=updated["id"],
                name=updated["name"],
                provider=updated["provider"],
                model=updated["model"],
                base_url=updated["base_url"],
                is_default=updated["is_default"],
                is_active=updated["is_active"],
                created_at=updated["created_at"],
                updated_at=updated["updated_at"],
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating LLM config {config_id}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.delete("/admin/llm/configs/{config_id}")
    async def delete_llm_config_item(config_id: int):
        """Delete an LLM configuration by ID"""
        try:
            ok = await db.delete_llm_config_item(config_id)
            if not ok:
                raise HTTPException(status_code=404, detail="LLM configuration not found")

            await solution_engine.reload_providers()
            logger.info(f"Deleted LLM config ID={config_id}")
            return {"message": "LLM configuration deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting LLM config {config_id}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/admin/llm/configs/{config_id}/default")
    async def set_default_llm_config(config_id: int):
        """Designate a specific LLM configuration as the default"""
        try:
            ok = await db.set_default_llm_config(config_id)
            if not ok:
                raise HTTPException(status_code=404, detail="LLM configuration not found")

            await solution_engine.reload_providers()
            logger.info(f"Set LLM config ID={config_id} as default")
            return {"message": f"LLM config {config_id} set as default"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error setting default LLM config {config_id}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/admin/llm/configs/{config_id}/test")
    async def test_registered_llm(config_id: int):
        """Test connectivity of a registered LLM provider"""
        try:
            cfg = await db.get_llm_config_by_id(config_id)
            if not cfg:
                raise HTTPException(status_code=404, detail="LLM configuration not found")

            from services.llm_factory import LLMFactory

            provider = LLMFactory.create_provider(
                provider_name=cfg["provider"],
                api_key=cfg["api_key"],
                model=cfg["model"],
                base_url=cfg["base_url"],
            )

            try:
                test_response = await provider.generate_solution(
                    failure_reason="CrashLoopBackOff",
                    failure_message="Test connection to registered LLM provider",
                    pod_context={"name": "test-pod", "namespace": "test"},
                    events=[
                        {
                            "type": "Warning",
                            "reason": "BackOff",
                            "message": "Back-off restarting container",
                        }
                    ],
                )

                if (
                    test_response
                    and test_response.content
                    and len(test_response.content) > 10
                ):
                    return {"success": True, "message": "LLM connection successful"}
                else:
                    return {"success": False, "message": "LLM returned empty response"}
            finally:
                await provider.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error testing registered LLM {config_id}: {e}")
            return {"success": False, "message": str(e)}

    @router.get("/llm/available", response_model=List[LLMAvailableItem])
    async def get_available_llms():
        """Get list of active LLMs for UI dropdown selectors in Pod Details and Advice"""
        try:
            configs = await db.get_all_llm_configs(active_only=True)
            return [
                LLMAvailableItem(
                    id=c["id"],
                    name=c["name"],
                    provider=c["provider"],
                    model=c["model"],
                    is_default=c["is_default"],
                )
                for c in configs
            ]
        except Exception as e:
            logger.error(f"Error getting available LLMs: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # --- Custom Instructions ---

    @router.get("/admin/llm/instructions", response_model=LLMCustomInstructionsResponse)
    async def get_custom_instructions():
        """Get the current custom instructions for LLM prompts"""
        try:
            instructions = await db.get_app_setting("llm_custom_instructions") or ""
            return LLMCustomInstructionsResponse(
                instructions=instructions,
            )
        except Exception as e:
            logger.error(f"Error getting custom instructions: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.put("/admin/llm/instructions", response_model=LLMCustomInstructionsResponse)
    async def save_custom_instructions(body: LLMCustomInstructionsUpdate):
        """Save or update custom instructions for LLM prompts (max 10,000 characters)"""
        try:
            cleaned = body.instructions.strip()
            # Enforce 10,000 characters maximum
            if len(cleaned) > 10000:
                raise HTTPException(
                    status_code=400,
                    detail="Instructions exceed maximum allowed length of 10,000 characters",
                )

            await db.set_app_setting("llm_custom_instructions", cleaned)
            solution_engine.update_custom_instructions(cleaned)
            logger.info("Custom instructions saved and updated in solution engine")

            return LLMCustomInstructionsResponse(
                instructions=cleaned,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error saving custom instructions: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.delete("/admin/llm/instructions")
    async def delete_custom_instructions():
        """Clear custom instructions for LLM prompts"""
        try:
            await db.set_app_setting("llm_custom_instructions", "")
            solution_engine.update_custom_instructions("")
            return {"message": "Custom instructions deleted"}
        except Exception as e:
            logger.error(f"Error deleting custom instructions: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    return router

