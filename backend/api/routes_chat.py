from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from .auth import require_service_token
from .deps import RouterDeps

logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    prompt: str
    pod_name: Optional[str] = None
    namespace: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    context_used: bool

def create_chat_ingest_router(deps: RouterDeps) -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_service_token)])
    db = deps.db
    solution_engine = deps.solution_engine

    @router.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest):
        if not solution_engine.llm_provider:
            raise HTTPException(status_code=503, detail="LLM provider not configured")

        # Save user prompt
        if request.pod_name and request.namespace:
            await db.save_chat_message(request.pod_name, request.namespace, "user", request.prompt)

        system_prompt = "You are a helpful Kubernetes AI assistant. Answer the user's questions based on the provided context if applicable."
        context_blocks = []
        context_used = False

        if request.pod_name and request.namespace:
            # Fetch pod failures and find the targeted one
            pods = await db.get_pod_failures(include_dismissed=True)
            matched_pod = next(
                (p for p in pods if p.pod_name == request.pod_name and p.namespace == request.namespace),
                None
            )

            if matched_pod:
                context_used = True
                context_blocks.append(f"Target Pod: {request.namespace}/{request.pod_name}")
                if matched_pod.failure_reason:
                    context_blocks.append(f"Last recorded failure reason: {matched_pod.failure_reason}")
                if matched_pod.failure_message:
                    context_blocks.append(f"Last recorded failure message: {matched_pod.failure_message}")
                
                if matched_pod.events:
                    events_str = "\n".join([str(e) for e in matched_pod.events[-10:]])
                    context_blocks.append(f"Recent Events:\n{events_str}")
                
                if matched_pod.manifest:
                    context_blocks.append(f"Manifest:\n```yaml\n{matched_pod.manifest}\n```")
                
                logs = await db.get_pod_failure_logs(matched_pod.id)
                if logs:
                    logs_blocks = []
                    for log_entry in logs:
                        cname = log_entry.get("container_name", "unknown")
                        log_text = log_entry.get("logs", "")
                        if log_text:
                            # Take last 50 lines to keep prompt size reasonable
                            log_lines = log_text.splitlines()[-50:]
                            logs_blocks.append(f"Container {cname} logs:\n" + "\n".join(log_lines))
                    if logs_blocks:
                        context_blocks.append("Logs:\n" + "\n".join(logs_blocks))

        if context_used:
            user_prompt = f"Context:\n{chr(10).join(context_blocks)}\n\nUser Prompt:\n{request.prompt}"
        else:
            user_prompt = request.prompt
            
        try:
            llm_response = await solution_engine.llm_provider.generate_raw(
                system_prompt, user_prompt
            )

            # Save LLM response
            if request.pod_name and request.namespace:
                await db.save_chat_message(request.pod_name, request.namespace, "assistant", llm_response.content)

            return ChatResponse(
                response=llm_response.content,
                context_used=context_used
            )
        except Exception as e:
            logger.error(f"Chat generation failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate chat response")

    @router.get("/chat/history")
    async def get_chat_history(pod_name: str, namespace: str):
        if not pod_name or not namespace:
            raise HTTPException(status_code=400, detail="pod_name and namespace are required")
        try:
            history = await db.get_chat_history(pod_name, namespace)
            return history
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch chat history")

    @router.get("/chat/sessions")
    async def get_chat_sessions():
        try:
            return await db.get_chat_sessions()
        except Exception as e:
            logger.error(f"Error fetching chat sessions: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch chat sessions")

    @router.delete("/chat/history")
    async def delete_chat_history(pod_name: str, namespace: str):
        if not pod_name or not namespace:
            raise HTTPException(status_code=400, detail="pod_name and namespace are required")
        try:
            await db.delete_chat_history(pod_name, namespace)
            return {"status": "success"}
        except Exception as e:
            logger.error(f"Error deleting chat history: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete chat history")

    return router
