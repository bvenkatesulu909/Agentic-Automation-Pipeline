"""Example FastAPI application with agentic automation pipeline."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import router as automation_router
from .middleware import IdempotencyMiddleware, RequestLoggingMiddleware
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Agentic Automation Pipeline",
        description="Async task execution with webhooks, retry logic, idempotency, and DLQ handling",
        version="1.0.0",
    )

    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(IdempotencyMiddleware)

    # Include routers
    app.include_router(automation_router)

    # Startup and shutdown events
    @app.on_event("startup")
    async def startup_event():
        logger.info("Starting up agentic automation pipeline")
        logger.info("Redis backends initialized")
        logger.info("Celery app configured")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Shutting down agentic automation pipeline")

    # Health check endpoint
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "agentic-automation-pipeline",
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.automation.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
