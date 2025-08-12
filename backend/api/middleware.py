from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import traceback

logger = logging.getLogger(__name__)

def configure_cors(app):
    """Configure CORS middleware"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # React dev server
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

def configure_exception_handlers(app):
    """Configure global exception handlers"""
    
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