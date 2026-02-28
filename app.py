"""PhenomenalLayout application.

Orchestrates Lingo.dev translation services with Dolphin OCR for pixel-perfect
formatting integrity during document translation.
"""

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

import gradio as gr
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import api_router, app_router
from core.state_manager import state
from core.translation_handler import translation_service

# Import refactored components
from ui.gradio_interface import create_gradio_interface

# Ensure required directories exist BEFORE configuring logging so file handlers
# don't fail due to missing paths.
_REQUIRED_DIRECTORIES: list[str] = [
    "static",
    "uploads",
    "downloads",
    ".layout_backups",
    "templates",
    "logs",
]


def _ensure_required_dirs() -> list[str]:
    """Create required directories if missing and return created list."""
    created: list[str] = []
    for directory in _REQUIRED_DIRECTORIES:
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
            created.append(directory)
    return created


# Create directories early
_created_early: list[str] = _ensure_required_dirs()

# Configure logging (logs/ exists now)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/app.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Report any directories created prior to logger setup to keep visibility
if _created_early:
    for _d in _created_early:
        logger.info("Created directory: %s", _d)
    logger.info("All required directories verified/created before logging")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    # Startup logic
    created = _ensure_required_dirs()
    if created:
        for d in created:
            logger.info("Created directory: %s", d)
    logger.info("All required directories verified on startup")

    # Start memory monitoring if enabled
    if os.getenv("ENABLE_MEMORY_MONITORING", "").lower() == "true":
        try:
            from utils.memory_monitor import start_memory_monitoring
            check_interval = float(os.getenv("MEMORY_CHECK_INTERVAL", "60"))
            alert_threshold = float(os.getenv("MEMORY_ALERT_THRESHOLD_MB", "100"))
            start_memory_monitoring(check_interval, alert_threshold)
            logger.info("Memory monitoring enabled")
        except Exception as e:
            logger.warning("Failed to start memory monitoring: %s", e)

    yield

    # Shutdown logic
    with contextlib.suppress(RuntimeError):
        state.cancel_tracked_translation_task()
        task = state.get_tracked_translation_task()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                # Expected during shutdown - handle silently
                pass
            except Exception:
                logger.exception(
                    "Exception during tracked translation task shutdown"
                )
    state.drop_tracked_translation_task()

    # Stop memory monitoring
    try:
        from utils.memory_monitor import stop_memory_monitoring, log_memory_usage
        log_memory_usage("shutdown")
        stop_memory_monitoring()
    except Exception:
        logger.exception("Error stopping memory monitoring")

    try:
        await translation_service.aclose()
    except Exception:
        logger.exception("Failed to shutdown translation service")


# FastAPI app
app = FastAPI(
    title="PhenomenalLayout",
    description=(
        "Advanced layout preservation engine for document translation - "
        "orchestrating Lingo.dev translation services with Dolphin OCR "
        "for pixel-perfect formatting integrity"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(app_router)  # Root and philosophy routes without prefix
app.include_router(api_router, prefix="/api/v1")  # API routes with versioning

# Static files mount
app.mount("/static", StaticFiles(directory="static"), name="static")


def main() -> None:
    """Main application entry point."""
    logger.info("Starting PhenomenalLayout - Advanced Layout Preservation Engine")

    # Create Gradio interface
    gradio_app = create_gradio_interface()

    # Mount Gradio app to FastAPI
    app_with_gradio = gr.mount_gradio_app(app, gradio_app, path="/ui")

    # Start server with Uvicorn
    # Note: Default to localhost; override via HOST and PORT env vars
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app_with_gradio, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
