"""FastAPI application entry point."""

import asyncio
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.backend.api.routes import router as api_router
from src.backend.api.webhooks import router as webhook_router
from src.backend.config import settings
from src.backend.database import close_db, init_db
from src.backend.utils.background_tasks import (
    cleanup_old_logs,
    retry_failed_webhooks,
    schedule_periodic_task,
)
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle events.

    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info("Starting AI Agent Orchestration System")
    logger.info(f"Application: {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Log level: {settings.LOG_LEVEL}")

    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}", exc_info=True)
        raise

    # Schedule periodic tasks
    # Retry failed webhooks every 5 minutes
    schedule_periodic_task(retry_failed_webhooks, interval_seconds=300, task_name="retry_failed_webhooks")

    # Cleanup old logs daily (every 24 hours)
    schedule_periodic_task(cleanup_old_logs, interval_seconds=86400, task_name="cleanup_old_logs")

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down AI Agent Orchestration System")
    await close_db()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-ready AI Agent Orchestration System with webhook support",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    debug=settings.DEBUG,
)

# Add exception handler for better error messages
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to return detailed error messages."""
    logger.error(
        f"Unhandled exception: {str(exc)}",
        exc_info=True,
        extra={"path": str(request.url), "method": request.method},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "message": str(exc),
            "detail": str(exc) if settings.DEBUG else "Internal server error",
        },
    )

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router, prefix=settings.API_PREFIX)
app.include_router(webhook_router, prefix="/webhook")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


# Graceful shutdown handler
def shutdown_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown")
    # FastAPI's lifespan will handle the shutdown


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


def main() -> None:
    """Main entry point for the application."""
    import uvicorn

    uvicorn.run(
        "src.backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_config=None,  # Use our custom logging
    )


if __name__ == "__main__":
    main()

