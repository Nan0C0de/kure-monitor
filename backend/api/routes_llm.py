from fastapi import APIRouter, HTTPException
import logging

from models.models import (
    LLMConfigCreate, LLMConfigResponse, LLMConfigStatus,
    KyvernoPolicyConfigCreate, KyvernoPolicyResponse,
    KyvernoStatusResponse, KyvernoViolation,
)
from .deps import RouterDeps

logger = logging.getLogger(__name__)


def create_llm_router(deps: RouterDeps) -> APIRouter:
    """LLM status/config/test + Kyverno status/policies/violations/reconcile/install."""
    router = APIRouter()
    db = deps.db
    solution_engine = deps.solution_engine
    websocket_manager = deps.websocket_manager
    policy_engine = deps.policy_engine

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
            valid_providers = ["openai", "anthropic", "claude", "groq", "groq_cloud", "gemini", "google"]
            if config.provider.lower() not in valid_providers:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid provider. Supported: {', '.join(valid_providers)}"
                )

            result = await db.save_llm_config(
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model
            )

            await solution_engine.reinitialize_llm(
                provider=config.provider.lower(),
                api_key=config.api_key,
                model=config.model
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
                model=config.model
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

    # --- Kyverno ---

    @router.get("/admin/kyverno/status")
    async def get_kyverno_status():
        """Get Kyverno installation status and policy/violation counts"""
        try:
            if not policy_engine:
                return KyvernoStatusResponse().dict()
            status = await policy_engine.check_kyverno_status()
            return status
        except Exception as e:
            logger.error(f"Error getting Kyverno status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/kyverno/install")
    async def install_kyverno():
        """Trigger Kyverno installation via Helm"""
        try:
            if not policy_engine:
                raise HTTPException(status_code=503, detail="Policy engine not available")
            result = await policy_engine.install_kyverno()
            if not result["success"]:
                raise HTTPException(status_code=500, detail=result["message"])
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error installing Kyverno: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/kyverno/policies", response_model=list[KyvernoPolicyResponse])
    async def get_kyverno_policies():
        """Get all 20 Kyverno policies with their configuration"""
        try:
            return await db.get_kyverno_policies()
        except Exception as e:
            logger.error(f"Error getting Kyverno policies: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/kyverno/policies/{policy_id}", response_model=KyvernoPolicyResponse)
    async def get_kyverno_policy(policy_id: str):
        """Get a single Kyverno policy"""
        try:
            policy = await db.get_kyverno_policy(policy_id)
            if not policy:
                raise HTTPException(status_code=404, detail=f"Policy '{policy_id}' not found")
            return policy
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting Kyverno policy: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/admin/kyverno/policies/{policy_id}", response_model=KyvernoPolicyResponse)
    async def update_kyverno_policy(policy_id: str, config: KyvernoPolicyConfigCreate):
        """Update Kyverno policy configuration and apply/remove in cluster"""
        try:
            if config.mode not in ("audit", "enforce"):
                raise HTTPException(status_code=400, detail="Mode must be 'audit' or 'enforce'")

            updated = await db.update_kyverno_policy(policy_id, config.dict())
            if not updated:
                raise HTTPException(status_code=404, detail=f"Policy '{policy_id}' not found")

            if policy_engine:
                if config.enabled:
                    success = await policy_engine.apply_policy(policy_id)
                    if not success:
                        logger.warning(f"Failed to apply policy {policy_id} to cluster")
                else:
                    success = await policy_engine.remove_policy(policy_id)
                    if not success:
                        logger.warning(f"Failed to remove policy {policy_id} from cluster")

            await websocket_manager.broadcast_kyverno_policy_change(updated.dict() if hasattr(updated, 'dict') else updated)

            return updated

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating Kyverno policy: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/kyverno/violations", response_model=list[KyvernoViolation])
    async def get_kyverno_violations():
        """Get Kyverno policy violations from PolicyReport CRDs"""
        try:
            if not policy_engine:
                return []
            violations = await policy_engine.get_violations()
            return violations
        except Exception as e:
            logger.error(f"Error getting Kyverno violations: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/kyverno/reconcile")
    async def reconcile_kyverno_policies():
        """Force reconciliation of Kyverno policies with cluster"""
        try:
            if not policy_engine:
                raise HTTPException(status_code=503, detail="Policy engine not available")
            await policy_engine.reconcile()
            return {"message": "Reconciliation complete"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error during Kyverno reconciliation: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return router
