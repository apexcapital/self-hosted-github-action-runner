import signal
import sys
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from src.api.routes import router
from src.orchestrator import RunnerOrchestrator
from src.utils.logging import setup_logging

# Global orchestrator instance
orchestrator: RunnerOrchestrator = None  # type: ignore


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """FastAPI lifespan context manager."""
    global orchestrator  # pylint: disable=global-statement

    # Setup logging
    setup_logging()
    logger = structlog.get_logger()

    try:
        logger.info("Starting GitHub Actions Runner Orchestrator", version="2.0.0")

        # Initialize orchestrator
        orchestrator = RunnerOrchestrator()
        await orchestrator.start()

        # Store orchestrator in app state for access in routes
        fastapi_app.state.orchestrator = orchestrator

        logger.info("Orchestrator started successfully")
        yield

    except Exception as e:
        logger.error("Failed to start orchestrator", error=str(e))
        raise
    finally:
        logger.info("Shutting down orchestrator")
        if orchestrator:
            await orchestrator.stop()
        logger.info("Orchestrator stopped")


# Create FastAPI app
app = FastAPI(
    title="GitHub Actions Runner Orchestrator",
    description="Dynamic GitHub Actions Runner management system",
    version="2.0.0",
    lifespan=lifespan,
)

# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "orchestrator_running": (
            orchestrator is not None and orchestrator.is_running
            if orchestrator
            else False
        ),
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "GitHub Actions Runner Orchestrator",
        "version": "2.0.0",
        "docs_url": "/docs",
    }


def signal_handler(signum, _):
    """Handle shutdown signals gracefully."""
    logger = structlog.get_logger()
    logger.info("Received shutdown signal", signal=signum)
    sys.exit(0)


if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
        access_log=True,
        reload=False,
    )
