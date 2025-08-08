from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
import traceback
from contextlib import asynccontextmanager

from models import PodFailureReport, PodFailureResponse
from solution_engine import SolutionEngine
from database import Database
from websocket import WebSocketManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
db = Database()
solution_engine = SolutionEngine()
websocket_manager = WebSocketManager()

# Global cluster info
cluster_info = {"cluster_name": "k8s-cluster"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db.init_database()
    logger.info("Database initialized")
    yield
    # Shutdown
    await db.close()


app = FastAPI(title="Kure Backend", version="1.0.0", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for better error logging and responses"""
    error_id = id(exc)  # Simple error ID for tracking
    error_traceback = traceback.format_exc()
    
    # Log detailed error information
    logger.error(f"Unhandled exception [ID:{error_id}] in {request.method} {request.url}: {exc}")
    logger.error(f"Traceback [ID:{error_id}]:\n{error_traceback}")
    
    # Return user-friendly error response
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": f"An unexpected error occurred while processing your request",
            "error_type": type(exc).__name__,
            "error_id": error_id,
            "details": str(exc)
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Enhanced HTTP exception handler"""
    logger.warning(f"HTTP {exc.status_code} error in {request.method} {request.url}: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": f"HTTP {exc.status_code} Error",
            "message": exc.detail,
            "path": str(request.url)
        }
    )


@app.post("/api/pods/failed", response_model=PodFailureResponse)
async def report_failed_pod(report: PodFailureReport):
    """Receive failed pod report from agent"""
    logger.info(f"Received failure report for pod: {report.namespace}/{report.pod_name}")
    
    try:
        # Validate required fields
        if not report.pod_name or not report.namespace:
            raise HTTPException(status_code=400, detail="Pod name and namespace are required")
        
        # Generate solution
        pod_context = {
            "name": report.pod_name,
            "namespace": report.namespace,
            "image": getattr(report, 'image', 'Unknown')
        }
        
        logger.info(f"Generating solution for pod {report.namespace}/{report.pod_name}, failure reason: {report.failure_reason}")
        solution = await solution_engine.get_solution(
            reason=report.failure_reason,
            message=report.failure_message,
            events=report.events,
            container_statuses=report.container_statuses,
            pod_context=pod_context
        )

        # Create response
        response = PodFailureResponse(
            **report.dict(),
            solution=solution,
            timestamp=report.creation_timestamp
        )

        # Save to database
        logger.info(f"Saving pod failure to database: {report.namespace}/{report.pod_name}")
        await db.save_pod_failure(response)

        # Notify frontend via WebSocket
        logger.info(f"Broadcasting pod failure via WebSocket: {report.namespace}/{report.pod_name}")
        await websocket_manager.broadcast_pod_failure(response)

        logger.info(f"Successfully processed failed pod: {report.namespace}/{report.pod_name}")
        return response

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        error_msg = f"Failed to process pod failure report for {report.namespace}/{report.pod_name}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Error details: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error while processing pod failure: {str(e)}"
        )


@app.get("/api/pods/failed", response_model=list[PodFailureResponse])
async def get_failed_pods():
    """Get all failed pods from database"""
    try:
        return await db.get_pod_failures()
    except Exception as e:
        logger.error(f"Error getting pod failures: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pods/ignored", response_model=list[PodFailureResponse])
async def get_ignored_pods():
    """Get all ignored pods from database"""
    try:
        return await db.get_pod_failures(include_dismissed=True, dismissed_only=True)
    except Exception as e:
        logger.error(f"Error getting ignored pods: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/pods/failed/{pod_id}")
async def dismiss_pod_failure(pod_id: int):
    """Mark a pod failure as resolved/dismissed"""
    try:
        await db.dismiss_pod_failure(pod_id)
        return {"message": "Pod failure dismissed"}
    except Exception as e:
        logger.error(f"Error dismissing pod failure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/pods/ignored/{pod_id}/restore")
async def restore_pod_failure(pod_id: int):
    """Restore/un-ignore a dismissed pod failure"""
    try:
        await db.restore_pod_failure(pod_id)
        return {"message": "Pod failure restored"}
    except Exception as e:
        logger.error(f"Error restoring pod failure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pods/dismiss-deleted")
async def dismiss_deleted_pod(request: dict):
    """Mark pods as dismissed when they're deleted from Kubernetes"""
    try:
        namespace = request.get("namespace")
        pod_name = request.get("pod_name")
        
        if not namespace or not pod_name:
            raise HTTPException(status_code=400, detail="namespace and pod_name required")
        
        await db.dismiss_deleted_pod(namespace, pod_name)
        
        # Notify frontend via WebSocket that pod was removed
        await websocket_manager.broadcast_pod_deleted(namespace, pod_name)
        
        logger.info(f"Dismissed deleted pod: {namespace}/{pod_name}")
        return {"message": "Deleted pod dismissed"}
    except Exception as e:
        logger.error(f"Error dismissing deleted pod: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pods/{namespace}/{pod_name}/manifest")
async def get_pod_manifest(namespace: str, pod_name: str):
    """Get pod manifest YAML from Kubernetes API"""
    try:
        # This would require Kubernetes client access from backend
        # For now, return placeholder - this should be implemented if needed
        return {"error": "Pod manifest retrieval not implemented yet"}
    except Exception as e:
        logger.error(f"Error getting pod manifest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cluster/register")
async def register_cluster_info(request: dict):
    """Register cluster information from agent"""
    try:
        cluster_name = request.get("cluster_name")
        if not cluster_name:
            raise HTTPException(status_code=400, detail="cluster_name is required")
        
        global cluster_info
        cluster_info["cluster_name"] = cluster_name
        logger.info(f"Registered cluster: {cluster_name}")
        return {"message": "Cluster info registered successfully"}
    except Exception as e:
        logger.error(f"Error registering cluster info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cluster/info")
async def get_cluster_info():
    """Get cluster information"""
    try:
        return cluster_info
    except Exception as e:
        logger.error(f"Error getting cluster info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# WebSocket endpoint
app.include_router(websocket_manager.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
