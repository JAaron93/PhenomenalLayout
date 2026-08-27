"""FastAPI route handlers for document translation API."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import json
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from api.auth import UserRole, get_current_user_dependency, is_auth_enabled

from services.byok_credentials_manager import BYOKCredentialsManager, GuideStep, ValidationResult
from services.cost_estimator import CostQuote, GCPCostEstimator
from services.user_vocabulary_store import TermPreference, UserVocabularyStore
from services.book_translation_orchestrator import (
    BookJobHandle,
    BookScanResult,
    BookTranslationOrchestrator,
    CompletionSummary,
    FallbackResult,
)

from api.memory_routes import router as memory_router
from core.state_manager import state, translation_jobs
from core.translation_handler import (
    document_processor,
    file_handler,
    language_detector,
    neologism_detector,
    philosophy_translation_service,
    process_advanced_translation_job,
    user_choice_manager,
)
from dolphin_ocr.errors import get_error_message
from models.neologism_models import (
    ConfidenceFactors,
    DetectedNeologism,
    MorphologicalAnalysis,
    NeologismType,
    PhilosophicalContext,
)
from models.user_choice_models import (
    ChoiceScope,
    ChoiceType,
)
from utils import pdf_validator
from utils.language_utils import extract_text_sample_for_language_detection

# Default endpoints for legacy configuration compatibility (ADR 0001)
DEFAULT_MODAL_ENDPOINT: str = (
    "https://modal-labs--dolphin-ocr-service-dolphin-ocr-endpoint.modal.run"
)
DEFAULT_LOCAL_ENDPOINT: str = "http://localhost:8501/layout"

# Import services for configuration endpoints
from services.philosophy_enhanced_translation_service import (
    translate_with_philosophy_awareness,
)
from services.neologism_detector import merge_neologism_analyses
from services.pdf_quality_validator import PDFQualityValidator
from services.confidence_scorer import ConfidenceScorer

logger: logging.Logger = logging.getLogger(__name__)

# Templates
templates: Jinja2Templates = Jinja2Templates(directory="templates")

# Create APIRouter instances
api_router: APIRouter = APIRouter()
app_router: APIRouter = APIRouter()

# Include memory monitoring routes
api_router.include_router(memory_router)

# Type aliases for better readability
ChoiceData = dict[str, Any]
ExportData = dict[str, Any]
ImportData = dict[str, Any]
UploadResponse = dict[str, Any]
TranslationResponse = dict[str, Any]
JobStatusResponse = dict[str, Any]
NeologismResponse = dict[str, Any]
ProgressResponse = dict[str, Any]
TerminologyResponse = dict[str, str]


@app_router.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint."""
    return {
        "message": "Advanced Document Translator API",
        "ui_url": "/ui",
        "philosophy_ui_url": "/philosophy",
        "version": "2.0.0",
        "features": [
            "Advanced PDF processing",
            "Image-text overlay preservation",
            "High-resolution rendering",
            "Comprehensive format support",
            "Philosophy-enhanced neologism detection",
            "User choice management for translations",
        ],
    }


@app_router.get("/philosophy", response_class=HTMLResponse)
async def philosophy_interface(request: Request) -> HTMLResponse:
    """Philosophy-enhanced translation interface."""
    return templates.TemplateResponse(
        "philosophy_interface.html",
        {"request": request},
    )


# Dolphin OCR Configuration Endpoints
# Use a module-level dictionary to store runtime configuration instead of mutating os.environ
_dolphin_config = {
    "DOLPHIN_ENDPOINT_TYPE": "modal",
    "DOLPHIN_LOCAL_ENDPOINT": DEFAULT_LOCAL_ENDPOINT,
    "DOLPHIN_ENDPOINT": DEFAULT_MODAL_ENDPOINT,
    "DOLPHIN_TIMEOUT_SECONDS": "300"
}

# Initialize with environment variables
import os
for key in _dolphin_config:
    if os.getenv(key):
        _dolphin_config[key] = os.getenv(key)


@api_router.get("/config/dolphin")
async def get_dolphin_configuration() -> dict[str, Any]:
    """Get Dolphin OCR service configuration."""
    endpoint_type = _dolphin_config["DOLPHIN_ENDPOINT_TYPE"].lower()
    local_endpoint = _dolphin_config["DOLPHIN_LOCAL_ENDPOINT"]
    modal_endpoint = _dolphin_config["DOLPHIN_ENDPOINT"]
    timeout = _dolphin_config["DOLPHIN_TIMEOUT_SECONDS"]
    
    # Determine active endpoint
    if endpoint_type == "local":
        active_endpoint = local_endpoint
    else:
        active_endpoint = modal_endpoint
    
    return {
        "endpoint_type": endpoint_type,
        "local_endpoint": local_endpoint,
        "modal_endpoint": modal_endpoint,
        "active_endpoint": active_endpoint,
        "timeout_seconds": timeout,
        "available_endpoint_types": ["modal", "local"],
    }


@api_router.post("/config/dolphin")
async def update_dolphin_configuration(config_data: dict[str, Any]) -> dict[str, Any]:
    """Update Dolphin OCR service configuration.
    
    Note: This only updates the runtime configuration in memory. For persistent changes,
    update the environment variables in your deployment configuration.
    """
    valid_keys = {"DOLPHIN_ENDPOINT_TYPE", "DOLPHIN_LOCAL_ENDPOINT", "DOLPHIN_TIMEOUT_SECONDS", "DOLPHIN_ENDPOINT"}
    updated_keys = []
    
    for key, value in config_data.items():
        if key in valid_keys:
            _dolphin_config[key] = str(value)
            updated_keys.append(key)
    
    if updated_keys:
        return {
            "success": True,
            "message": f"Updated configuration: {', '.join(updated_keys)}",
            "note": "Runtime changes will take effect on next request",
        }
    else:
        return {
            "success": False,
            "message": "No valid configuration keys provided",
            "valid_keys": list(valid_keys),
        }


# Philosophy Terminology Management Endpoints
@api_router.get("/philosophy/terminology")
async def get_terminology_map() -> dict[str, Any]:
    """Get the current philosophical terminology map."""
    try:
        # Access the philosophical context analyzer from neologism_detector
        analyzer = neologism_detector.philosophical_context_analyzer
        terminology_map = analyzer.terminology_map
        
        return {
            "terminology_map": terminology_map,
            "term_count": len(terminology_map),
        }
    except Exception as e:
        logger.error("Error getting terminology map: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/philosophy/terminology")
async def update_terminology_map(terminology_data: dict[str, Any]) -> dict[str, Any]:
    """Update the philosophical terminology map with new terms.
    
    This enables runtime terminology management for philosophy-aware translation.
    """
    try:
        new_terms = terminology_data.get("terminology", {})
        
        if not isinstance(new_terms, dict):
            raise HTTPException(
                status_code=400, 
                detail="Terminology must be a dictionary mapping terms to translations"
            )
        
        # Access the philosophical context analyzer from neologism_detector
        analyzer = neologism_detector.philosophical_context_analyzer
        
        # Update the terminology map
        analyzer.update_terminology_map(new_terms)
        
        return {
            "success": True,
            "message": f"Updated terminology map with {len(new_terms)} new terms",
            "total_terms": len(analyzer.terminology_map),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating terminology map: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# Philosophy-Enhanced Translation Configuration Endpoints
@api_router.get("/philosophy/config")
async def get_philosophy_translation_config() -> dict[str, Any]:
    """Get philosophy-enhanced translation service configuration."""
    try:
        config = philosophy_translation_service.get_statistics().get("configuration", {})
        
        return {
            "preserve_neologisms_by_default": config.get("preserve_neologisms_by_default", True),
            "neologism_confidence_threshold": config.get("neologism_confidence_threshold", 0.5),
            "chunk_size": config.get("chunk_size", 2000),
            "available_providers": philosophy_translation_service.get_available_providers(),
        }
    except Exception as e:
        logger.error("Error getting philosophy translation config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/philosophy/config")
async def update_philosophy_translation_config(config_data: dict[str, Any]) -> dict[str, Any]:
    """Update philosophy-enhanced translation service configuration."""
    try:
        # Map API keys to service parameter names
        param_mapping = {
            "preserve_neologisms_by_default": "preserve_neologisms_by_default",
            "neologism_confidence_threshold": "neologism_confidence_threshold",
            "chunk_size": "chunk_size",
        }
        
        # Build kwargs for update_configuration
        kwargs = {}
        for api_key, param_name in param_mapping.items():
            if api_key in config_data:
                kwargs[param_name] = config_data[api_key]
        
        if kwargs:
            philosophy_translation_service.update_configuration(**kwargs)
            return {
                "success": True,
                "message": f"Updated configuration: {', '.join(kwargs.keys())}",
            }
        else:
            return {
                "success": False,
                "message": "No valid configuration keys provided",
                "valid_keys": list(param_mapping.keys()),
            }
    except Exception as e:
        logger.error("Error updating philosophy translation config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/philosophy/translate")
async def translate_with_philosophy(
    translation_data: dict[str, Any],
) -> dict[str, Any]:
    """Translate text with philosophy awareness.
    
    This endpoint uses the philosophy-enhanced translation service to detect
    and preserve neologisms while applying user choices.
    """
    try:
        text = translation_data.get("text", "")
        source_lang = translation_data.get("source_language", "de")
        target_lang = translation_data.get("target_language", "en")
        provider = translation_data.get("provider", "auto")
        session_id = translation_data.get("session_id")
        
        if not text:
            raise HTTPException(
                status_code=400,
                detail="Text is required for translation"
            )
        
        result = await translate_with_philosophy_awareness(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            provider=provider,
            session_id=session_id,
            service=philosophy_translation_service,
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in philosophy-aware translation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# Neologism Analysis Utilities
@api_router.post("/philosophy/merge-analyses")
async def merge_neologism_analyses_endpoint(
    merge_data: dict[str, Any],
) -> dict[str, Any]:
    """Merge multiple neologism analyses into a single comprehensive analysis.
    
    This is useful for batch processing or combining results from different
    detection passes.
    """
    try:
        analyses = merge_data.get("analyses", [])
        
        if not analyses:
            raise HTTPException(
                status_code=400,
                detail="No analyses provided for merging"
            )
        
        if not isinstance(analyses, list):
            raise HTTPException(
                status_code=400,
                detail="Analyses must be a list"
            )
        
        merged = merge_neologism_analyses(analyses)
        
        return {
            "success": True,
            "merged_analysis": merged.to_dict() if hasattr(merged, 'to_dict') else merged,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error merging neologism analyses: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# Philosophy API Endpoints
@api_router.post("/philosophy/choice")
async def save_user_choice(choice_data: ChoiceData) -> dict[str, Any]:
    """Save a user choice for a neologism."""
    try:
        # Extract choice data with explicit validation
        term_raw = choice_data.get("term")
        if not isinstance(term_raw, str) or not term_raw.strip():
            raise HTTPException(
                status_code=400, detail="Term must be a non-empty string"
            )
        term: str = term_raw

        choice_value: str = str(choice_data.get("choice", "preserve"))
        custom_translation: str = str(choice_data.get("custom_translation", ""))
        notes: str = str(choice_data.get("notes", ""))

        session_id: str | None = choice_data.get("session_id")

        # Create a simple neologism representation
        neologism: DetectedNeologism = DetectedNeologism(
            term=term,
            confidence=0.8,
            neologism_type=NeologismType.PHILOSOPHICAL_TERM,
            start_pos=0,
            end_pos=len(term),
            sentence_context="Context sentence",
            morphological_analysis=MorphologicalAnalysis(),
            philosophical_context=PhilosophicalContext(),
            confidence_factors=ConfidenceFactors(),
        )

        # Map choice string to ChoiceType
        choice_type_mapping: dict[str, ChoiceType] = {
            "preserve": ChoiceType.PRESERVE,
            "translate": ChoiceType.TRANSLATE,
            "custom": ChoiceType.CUSTOM_TRANSLATION,
        }

        choice_type: ChoiceType = choice_type_mapping.get(
            choice_value,
            ChoiceType.PRESERVE,
        )

        # Save the choice
        user_choice = user_choice_manager.make_choice(
            neologism=neologism,
            choice_type=choice_type,
            translation_result=custom_translation,
            session_id=session_id,
            choice_scope=ChoiceScope.CONTEXTUAL,
            user_notes=notes,
        )

        return {
            "success": True,
            "choice_id": user_choice.choice_id,
            "message": "Choice saved successfully",
        }

    except HTTPException as he:
        # Preserve client-facing HTTP errors (e.g., 400 validation)
        # Avoid logging potentially sensitive user-provided detail wholesale
        detail = getattr(he, "detail", None)
        err_code = detail.get("error_code") if isinstance(detail, dict) else None
        logger.warning(
            "HTTP %s error saving user choice",
            getattr(he, "status_code", "error"),
            extra={"error_code": err_code},
        )
        raise he
    except Exception as e:
        logger.error("Error saving user choice: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@api_router.get("/philosophy/neologisms")
async def get_detected_neologisms(
    _session_id: str | None = None,
) -> NeologismResponse:
    """Get detected neologisms for the current session.

    Args:
        _session_id: Session identifier (reserved for future use)
    """
    try:
        # Return neologisms from state
        neologisms: list[DetectedNeologism] = (
            state.neologism_analysis.get("detected_neologisms", [])
            if state.neologism_analysis
            else []
        )
        total: int = len(neologisms)
        return {"neologisms": neologisms, "total": total}
    except Exception as e:
        logger.error("Error getting neologisms: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@api_router.get("/philosophy/progress")
async def get_philosophy_progress() -> ProgressResponse:
    """Get current philosophy processing progress."""
    try:
        total_neologisms: int = 0
        if state.neologism_analysis and isinstance(state.neologism_analysis, dict):
            detected: list[Any] = state.neologism_analysis.get(
                "detected_neologisms", []
            )
            if isinstance(detected, list):
                total_neologisms = len(detected)

        processed_neologisms: int = 0
        if isinstance(state.user_choices, list):
            processed_neologisms = sum(
                1
                for choice in state.user_choices
                if isinstance(choice, dict) and choice.get("processed", False)
            )
        return {
            "total_neologisms": total_neologisms,
            "processed_neologisms": processed_neologisms,
            "choices_made": len(state.user_choices),
            "session_id": state.session_id,
            "philosophy_mode": state.philosophy_mode,
        }
    except Exception as e:
        logger.error("Error getting progress: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@api_router.post("/philosophy/export-choices", response_model=None)
async def export_user_choices(
    export_data: ExportData,
) -> FileResponse | dict[str, Any]:
    """Export user choices to JSON."""
    try:
        session_id: str | None = export_data.get("session_id")

        if session_id:
            export_file_path: str | None = user_choice_manager.export_session_choices(session_id)
        else:
            export_file_path: str | None = user_choice_manager.export_all_choices()

        if export_file_path:
            return FileResponse(
                export_file_path,
                media_type="application/json",
                filename=(
                    "philosophy-choices-"
                    f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
                    ".json"
                ),
            )
        else:
            raise HTTPException(status_code=500, detail="Export failed")

    except Exception as e:
        logger.error("Error exporting choices: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@api_router.post("/philosophy/import-choices")
async def import_user_choices(import_data: ImportData) -> dict[str, Any]:
    """Import user choices from dictionary."""
    try:
        choices: dict[str, Any] = import_data.get("choices", {})
        session_id: str | None = import_data.get("session_id")

        # Validate that choices is a dictionary
        if not isinstance(choices, dict):
            raise HTTPException(
                status_code=400, detail="'choices' must be a dictionary"
            )

        # Use the new dictionary-accepting method
        count: int = user_choice_manager.import_choices_from_dict(choices, session_id)

        return {
            "success": True,
            "count": count,
            "message": f"Imported {count} choices successfully",
        }

    except ValueError as e:
        logger.error("Validation error importing choices: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error importing choices: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@api_router.get("/philosophy/terminology")
async def get_terminology() -> TerminologyResponse:
    """Get current terminology database."""
    try:
        # Get terminology from neologism detector
        terminology: dict[str, str] = neologism_detector.terminology_map
        return terminology

    except Exception as e:
        logger.error("Error getting terminology: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:  # noqa: B008
    """Enhanced upload endpoint with advanced processing."""
    try:
        # Save file first so validators can inspect header and structure
        file_path: str = file_handler.save_upload_file(file)

        # Basic format validation
        fmt = pdf_validator.validate_pdf_extension_and_header(file_path)
        if not fmt.ok:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "DOLPHIN_005",
                    "message": "Only PDF format supported",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "context": {"path": Path(file_path).name},
                },
            )

        # Encryption check
        enc = pdf_validator.detect_pdf_encryption(file_path)
        if enc.is_encrypted:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "DOLPHIN_014",
                    "message": get_error_message("DOLPHIN_014"),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "context": {"path": Path(file_path).name},
                },
            )

        # Process with advanced extraction
        content: dict[str, Any] = await document_processor.extract_content(file_path)

        # Detect language using the utility function
        sample_text: str = (
            extract_text_sample_for_language_detection(content) or ""
        ).strip()
        detected_lang: str | None = (
            language_detector.detect_language_from_text(sample_text)
            if sample_text
            else None
        )

        # Clean metadata access pattern with comprehensive object-to-dict conversion
        def _looks_like_fs_path(value: Any) -> bool:
            """Heuristic: True for probable filesystem paths, False for URLs and generic strings."""
            if not isinstance(value, (str, Path)):
                return False
            s = str(value).strip()
            if not s:
                return False
            lower = s.lower()
            # Treat common URL-like schemes as non-filesystem
            if lower.startswith(("http://", "https://", "ftp://", "s3://", "gs://")):
                return False
            # Unix-style absolute or relative
            if s.startswith(("/", "./", "../", "~")):
                return True
            # Generic presence of separators suggesting a path (but not just a lone slash)
            if ("/" in s or "\\" in s) and any(
                part not in ("", ".", "..") for part in s.replace("\\", "/").split("/")
            ):
                return True
            return False

        def sanitize_metadata(obj: Any) -> Any:
            """Recursively sanitize metadata by removing path-like keys and values."""
            # Define disallowed key patterns (case-insensitive)
            disallowed_keys = {
                "path",
                "file_path",
                "filepath",
                "full_path",
                "directory",
            }

            if isinstance(obj, dict):
                sanitized: dict[str, Any] = {}
                for k, v in obj.items():
                    # Drop if key is path-like or the value itself resembles a filesystem path
                    if k.casefold() in disallowed_keys or _looks_like_fs_path(v):
                        continue
                    sanitized[k] = sanitize_metadata(v)
                return sanitized
            elif isinstance(obj, list):
                sanitized_list: list[Any] = []
                for item in obj:
                    if _looks_like_fs_path(item):
                        # Preserve shape but avoid leaking server paths
                        sanitized_list.append(Path(str(item)).name)
                    else:
                        sanitized_list.append(sanitize_metadata(item))
                return sanitized_list
            elif hasattr(obj, "__dict__"):
                sanitized_obj = {
                    k: v
                    for k, v in obj.__dict__.items()
                    if not k.startswith("_")
                    and k.casefold()
                    not in {"path", "file_path", "filepath", "full_path", "directory"}
                    and not _looks_like_fs_path(v)
                }
                return sanitized_obj
            else:
                return obj

        # Do not expose server filesystem paths. Use a safe identifier (basename) instead.
        upload_id: str = Path(file_path).name

        # Get and sanitize metadata
        metadata: Any = content.get("metadata")
        metadata_dict: dict[str, Any] = sanitize_metadata(metadata) if metadata else {}
        return {
            "message": "File processed with advanced extraction",
            "filename": file.filename,
            "detected_language": detected_lang or "unknown",
            "upload_id": upload_id,
            "content_type": content.get("type", "document"),
            "metadata": metadata_dict,
        }

    except HTTPException:
        # Allow previously constructed HTTP errors to pass through
        raise
    except Exception as e:
        logger.exception("Enhanced upload error: %s", e)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "DOLPHIN_002",
                "message": get_error_message("DOLPHIN_002"),
                "timestamp": datetime.now(UTC).isoformat(),
                "filename": Path(file.filename).name
                if getattr(file, "filename", None)
                else None,
            },
        ) from e


@api_router.post("/translate")
async def translate_document(
    background_tasks: BackgroundTasks,
    file_path: str,
    source_language: str,
    target_language: str,
) -> TranslationResponse:
    """Enhanced translation endpoint."""
    try:
        import uuid

        job_id: str = str(uuid.uuid4())

        # Create job entry with enhanced info
        translation_jobs[job_id] = {
            "status": "started",
            "progress": 0,
            "file_path": file_path,
            "source_language": source_language,
            "target_language": target_language,
            "created_at": datetime.now(UTC),
            "output_file": None,
            "error": None,
            "processing_type": "advanced",
            "format_preservation": True,
        }

        # Start background translation with advanced processing
        background_tasks.add_task(
            process_advanced_translation_job,
            job_id,
            file_path,
            source_language,
            target_language,
        )

        return {
            "job_id": job_id,
            "status": "started",
            "type": "advanced",
        }

    except Exception as e:
        logger.error(f"Enhanced translation start error: {e!s}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@api_router.get("/status/{job_id}")
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Get enhanced job status."""
    if job_id not in translation_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return translation_jobs[job_id]


@api_router.get("/download/{job_id}")
async def download_result(job_id: str) -> FileResponse:
    """Download translated file with enhanced metadata."""
    if job_id not in translation_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job: dict[str, Any] = translation_jobs[job_id]
    if (job["status"] != "completed") or (not job["output_file"]):
        raise HTTPException(
            status_code=400,
            detail="Translation not completed",
        )
    try:
        return FileResponse(
            job["output_file"],
            media_type="application/octet-stream",
            filename=Path(job["output_file"]).name,
            headers={
                "X-Processing-Type": "advanced",
                "X-Format-Preserved": "true",
            },
        )
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=404, detail="Output file not found") from None


# PDF Quality Validation Endpoint
@api_router.post("/pdf/validate-quality")
async def validate_pdf_quality(
    validation_data: dict[str, Any],
) -> dict[str, Any]:
    """Validate PDF reconstruction quality.
    
    This endpoint checks how well a reconstructed PDF matches the original
    in terms of text preservation, layout, and optionally font preservation.
    """
    try:
        original_pdf = validation_data.get("original_pdf")
        reconstructed_pdf = validation_data.get("reconstructed_pdf")
        
        if not original_pdf:
            raise HTTPException(
                status_code=400,
                detail="original_pdf path is required"
            )
        
        if not reconstructed_pdf:
            raise HTTPException(
                status_code=400,
                detail="reconstructed_pdf path is required"
            )
        
        # Optional validation parameters
        min_text_length_score = validation_data.get("min_text_length_score", 0.9)
        min_layout_score = validation_data.get("min_layout_score", 0.7)
        require_font_preservation = validation_data.get("require_font_preservation", False)
        min_font_match_ratio = validation_data.get("min_font_match_ratio", 0.8)
        
        # Initialize validator and run validation
        validator = PDFQualityValidator()
        
        result = validator.validate_pdf_reconstruction_quality(
            original_pdf=original_pdf,
            reconstructed_pdf=reconstructed_pdf,
            min_text_length_score=min_text_length_score,
            min_layout_score=min_layout_score,
            require_font_preservation=require_font_preservation,
            min_font_match_ratio=min_font_match_ratio,
        )
        
        return {
            "success": True,
            "validation_result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error validating PDF quality: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# Confidence Scorer Endpoints
@api_router.get("/confidence/scorer-info")
async def get_confidence_scorer_info() -> dict[str, Any]:
    """Get information about the confidence scorer and its configuration."""
    try:
        scorer = ConfidenceScorer()
        
        return {
            "confidence_threshold": scorer.confidence_threshold,
            "philosophical_indicators_count": len(scorer.philosophical_indicators),
            "pattern_types": list(scorer.german_morphological_patterns.keys()),
        }
    except Exception as e:
        logger.error("Error getting confidence scorer info: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/confidence/scorer-config")
async def update_confidence_scorer_config(
    config_data: dict[str, Any],
) -> dict[str, Any]:
    """Update confidence scorer configuration."""
    try:
        scorer = ConfidenceScorer()
        
        updated = []
        
        # Update threshold if provided
        if "confidence_threshold" in config_data:
            threshold = config_data["confidence_threshold"]
            if isinstance(threshold, (int, float)):
                scorer.set_confidence_threshold(threshold)
                updated.append("confidence_threshold")
        
        # Update patterns if provided
        if "patterns" in config_data:
            patterns = config_data["patterns"]
            if isinstance(patterns, dict):
                scorer.update_patterns(patterns)
                updated.append("patterns")
        
        # Update philosophical indicators if provided
        if "philosophical_indicators" in config_data:
            indicators = config_data["philosophical_indicators"]
            if isinstance(indicators, (list, set)):
                scorer.update_philosophical_indicators(set(indicators))
                updated.append("philosophical_indicators")
        
        if updated:
            return {
                "success": True,
                "message": f"Updated configuration: {', '.join(updated)}",
            }
        else:
            return {
                "success": False,
                "message": "No valid configuration keys provided",
                "valid_keys": ["confidence_threshold", "patterns", "philosophical_indicators"],
            }
    except Exception as e:
        logger.error("Error updating confidence scorer config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/confidence/calculate")
async def calculate_confidence(
    confidence_data: dict[str, Any],
) -> dict[str, Any]:
    """Calculate confidence factors for a term."""
    try:
        term = confidence_data.get("term", "")
        
        if not term:
            raise HTTPException(
                status_code=400,
                detail="term is required"
            )
        
        scorer = ConfidenceScorer()
        
        # Calculate confidence factors
        morph_data = confidence_data.get("morphological", {})
        phil_data = confidence_data.get("philosophical", {})
        try:
            morph = MorphologicalAnalysis(**morph_data) if morph_data else MorphologicalAnalysis()
            phil = PhilosophicalContext(**phil_data) if phil_data else PhilosophicalContext()
        except (TypeError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid morphological or philosophical data: {e}"
            )
        factors = scorer.calculate_confidence_factors(term, morph, phil)
        
        # Get final confidence and breakdown
        final_confidence = scorer.calculate_final_confidence(factors)
        breakdown = scorer.get_confidence_breakdown(factors)
        
        return {
            "term": term,
            "final_confidence": final_confidence,
            "confidence_factors": factors.__dict__ if hasattr(factors, '__dict__') else {},
            "confidence_breakdown": breakdown,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error calculating confidence: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# ===========================================================================
# Track 5: GCP Migration Endpoints (TASK-5.2)
# ===========================================================================

_cost_estimator: GCPCostEstimator | None = None
_byok_manager: BYOKCredentialsManager | None = None
_user_vocabulary_store: UserVocabularyStore | None = None
_book_orchestrator: BookTranslationOrchestrator | None = None


def get_cost_estimator() -> GCPCostEstimator:
    """Return singleton GCPCostEstimator instance."""
    global _cost_estimator
    if _cost_estimator is None:
        _cost_estimator = GCPCostEstimator()
    return _cost_estimator


def get_byok_credentials_manager() -> BYOKCredentialsManager:
    """Return singleton BYOKCredentialsManager instance."""
    global _byok_manager
    if _byok_manager is None:
        _byok_manager = BYOKCredentialsManager()
    return _byok_manager


def get_user_vocabulary_store() -> UserVocabularyStore:
    """Return singleton UserVocabularyStore instance."""
    global _user_vocabulary_store
    if _user_vocabulary_store is None:
        _user_vocabulary_store = UserVocabularyStore()
    return _user_vocabulary_store


def get_book_orchestrator() -> BookTranslationOrchestrator:
    """Return singleton BookTranslationOrchestrator instance."""
    global _book_orchestrator
    if _book_orchestrator is None:
        _book_orchestrator = BookTranslationOrchestrator(
            credentials_manager=get_byok_credentials_manager(),
            vocabulary_store=get_user_vocabulary_store(),
            cost_estimator=get_cost_estimator(),
        )
    return _book_orchestrator


@api_router.post("/cost/estimate")
async def estimate_cost(
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Zero-auth GCP translation and storage budget estimator."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported for cost estimation")
    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        quote = get_cost_estimator().estimate_book_cost(contents)
        return {
            "total_pages": quote.total_pages,
            "file_size_mb": quote.file_size_mb,
            "base_cost": quote.base_cost,
            "staging_overhead_cost": quote.staging_overhead_cost,
            "storage_cost_1mo": quote.storage_cost_1mo,
            "storage_cost_12mo": quote.storage_cost_12mo,
            "free_tier_covered": quote.free_tier_covered,
            "total_estimate": quote.total_estimate,
            "tolerance_range": list(quote.tolerance_range),
            "estimation_time_sec": quote.estimation_time_sec,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Error calculating cost estimate: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/byok/onboarding-guide")
async def get_onboarding_guide() -> dict[str, Any]:
    """Interactive 6-step GCP BYOK onboarding guide with console links and gcloud script."""
    try:
        mgr = get_byok_credentials_manager()
        steps = mgr.get_onboarding_guide()
        steps_data = [
            {
                "step_number": s.step_number,
                "title": s.title,
                "description": s.description,
                "console_link": s.console_link,
                "gcloud_snippet": getattr(s, "gcloud_command", getattr(s, "gcloud_snippet", "")),
                "gcloud_command": getattr(s, "gcloud_command", getattr(s, "gcloud_snippet", "")),
            }
            for s in steps
        ]
        gcloud_script = getattr(
            mgr,
            "generate_gcloud_setup_script",
            lambda: "\n".join(
                getattr(s, "gcloud_command", getattr(s, "gcloud_snippet", ""))
                for s in steps
                if getattr(s, "gcloud_command", getattr(s, "gcloud_snippet", None))
            ),
        )()
        return {
            "steps": steps_data,
            "gcloud_script": gcloud_script,
        }
    except Exception as exc:
        logger.error("Error retrieving onboarding guide: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


def _verify_resource_ownership(
    requested_user_id: str,
    current_user: dict[str, Any] | None,
) -> None:
    """Ensure authenticated caller owns the requested resource or possesses admin role.

    Prevents shared state collisions and unauthorized cross-tenant mutations:
    - Shared anonymous namespaces ('anonymous', 'default_user', 'local_user') are rejected
      to ensure every visitor/session maintains isolated credentials, vocabulary, and jobs.
    - When authentication is disabled in config (is_auth_enabled() is False), permits local dev
      workflows with distinct user IDs bound to the caller's identity.
    - When authentication is enabled:
      - Rejects unauthenticated callers with 401 UNAUTHORIZED.
      - Authenticated administrators (UserRole.ADMIN) have global resource access.
      - Authenticated non-admin callers must possess a non-empty identity matching requested_user_id.
    """
    # Prohibit shared anonymous namespaces that cause multi-tenant state collision
    shared_namespaces = ("anonymous", "default_user", "local_user")
    if requested_user_id.lower() in shared_namespaces:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid user_id '{requested_user_id}': Shared anonymous namespaces are prohibited "
                "to isolate user credentials, vocabulary, and jobs. Please provide a distinct user identifier."
            ),
        )

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    is_authenticated = bool(current_user.get("authenticated", False))
    role = current_user.get("role")
    auth_uid = current_user.get("user_id")

    # When authentication is globally disabled (local dev mode):
    # Enforce binding to the caller's own identity so visitors cannot tamper with other namespaces.
    if not is_auth_enabled():
        if auth_uid and auth_uid != requested_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Caller identity '{auth_uid}' cannot access resources for '{requested_user_id}'.",
            )
        return

    # Reject unauthenticated/anonymous access to any user state
    if not is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Unauthenticated callers cannot access or modify user credentials, vocabulary, or jobs",
        )

    # Authenticated admin has global resource access
    if role == UserRole.ADMIN:
        return

    # Authenticated non-admin must match requested user ID and cannot be empty
    if not auth_uid or auth_uid != requested_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Cannot access or modify resources belonging to user '{requested_user_id}'",
        )


@api_router.post("/byok/credentials")
async def set_byok_credentials(
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Store BYOK credentials in session memory and validate them via zero-cost API calls."""
    user_id = payload.get("user_id", "").strip()
    project_id = payload.get("project_id", "").strip()
    bucket_name = payload.get("bucket_name", "").strip()
    sa_json = payload.get("sa_json") or payload.get("service_account_json")

    if not user_id or not project_id or not bucket_name or not sa_json:
        raise HTTPException(status_code=400, detail="user_id, project_id, bucket_name, and sa_json are required")

    _verify_resource_ownership(user_id, current_user)

    try:
        mgr = get_byok_credentials_manager()
        mgr.set_credentials(
            user_id=user_id,
            project_id=project_id,
            bucket_name=bucket_name,
            service_account_json=sa_json,
        )
        val = mgr.validate_credentials(user_id)
        is_valid = getattr(val, "is_valid", getattr(val, "status", "") == "VALID")
        trans_ok = getattr(val, "translation_api_ok", getattr(val, "translation_check_passed", False))
        stor_ok = getattr(val, "storage_bucket_ok", getattr(val, "storage_check_passed", False))
        details = getattr(val, "details", getattr(val, "error_details", "OK" if is_valid else "Validation failed"))
        proj = getattr(val, "project_id", project_id)
        bkt = getattr(val, "bucket_name", bucket_name)
        return {
            "is_valid": is_valid,
            "status": "VALID" if is_valid else "INVALID",
            "project_id": proj,
            "bucket_name": bkt,
            "translation_api_ok": trans_ok,
            "storage_bucket_ok": stor_ok,
            "translation_check_passed": trans_ok,
            "storage_check_passed": stor_ok,
            "details": details,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error setting BYOK credentials: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/byok/validate")
async def validate_byok_credentials(
    user_id: str = Query(..., description="User identifier to validate"),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Run dual non-billable validation on user's active session credentials."""
    _verify_resource_ownership(user_id, current_user)
    try:
        mgr = get_byok_credentials_manager()
        val = mgr.validate_credentials(user_id)
        is_valid = getattr(val, "is_valid", getattr(val, "status", "") == "VALID")
        trans_ok = getattr(val, "translation_api_ok", getattr(val, "translation_check_passed", False))
        stor_ok = getattr(val, "storage_bucket_ok", getattr(val, "storage_check_passed", False))
        details = getattr(val, "details", getattr(val, "error_details", "OK" if is_valid else "Validation failed"))
        proj = getattr(val, "project_id", getattr(mgr, "get_project_id", lambda u: "")(user_id) if hasattr(mgr, "has_credentials") and mgr.has_credentials(user_id) else "")
        bkt = getattr(val, "bucket_name", getattr(mgr, "get_bucket_name", lambda u: "")(user_id) if hasattr(mgr, "has_credentials") and mgr.has_credentials(user_id) else "")
        return {
            "is_valid": is_valid,
            "status": "VALID" if is_valid else "INVALID",
            "project_id": proj,
            "bucket_name": bkt,
            "translation_api_ok": trans_ok,
            "storage_bucket_ok": stor_ok,
            "translation_check_passed": trans_ok,
            "storage_check_passed": stor_ok,
            "details": details,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error validating credentials for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.delete("/byok/credentials")
async def clear_byok_credentials(
    user_id: str = Query(..., description="User identifier to clear"),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Evict session credentials from memory."""
    _verify_resource_ownership(user_id, current_user)
    try:
        mgr = get_byok_credentials_manager()
        if hasattr(mgr, "clear_credentials"):
            mgr.clear_credentials(user_id)
        return {"success": True, "message": f"Credentials cleared for user '{user_id}'"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error clearing credentials: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/book/pre-scan")
async def pre_scan_book_endpoint(
    user_id: str = Form(...),
    max_pages: int | None = Form(None),
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Pre-scan book PDF for neologisms, Fraktur OCR confidence rating, and vocabulary recall."""
    _verify_resource_ownership(user_id, current_user)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        orch = get_book_orchestrator()
        result = orch.pre_scan_book(user_id=user_id, source=contents, max_pages=max_pages)

        # Convert dataclasses to dicts
        prefilled = {k: v.to_dict() if hasattr(v, "to_dict") else v.__dict__ for k, v in result.prefilled_terms.items()}
        quote_dict = {
            "total_pages": result.cost_quote.total_pages,
            "file_size_mb": result.cost_quote.file_size_mb,
            "base_cost": result.cost_quote.base_cost,
            "staging_overhead_cost": result.cost_quote.staging_overhead_cost,
            "storage_cost_1mo": result.cost_quote.storage_cost_1mo,
            "storage_cost_12mo": result.cost_quote.storage_cost_12mo,
            "free_tier_covered": result.cost_quote.free_tier_covered,
            "total_estimate": result.cost_quote.total_estimate,
            "tolerance_range": list(result.cost_quote.tolerance_range),
            "estimation_time_sec": result.cost_quote.estimation_time_sec,
        }
        ocr_conf_dict = {
            "confidence_score": result.ocr_confidence.confidence_score,
            "script_type": result.ocr_confidence.script_type,
            "recommended_action": result.ocr_confidence.recommended_action,
            "preview_recommended": result.ocr_confidence.preview_recommended,
        }
        script_dict = {
            "script_type": result.script_analysis.script_type.value if hasattr(result.script_analysis.script_type, "value") else str(result.script_analysis.script_type),
            "ocr_confidence_score": result.script_analysis.ocr_confidence_score,
            "fraktur_ratio": result.script_analysis.fraktur_ratio,
            "recommended_action": result.script_analysis.recommended_action,
            "font_descriptors": result.script_analysis.font_descriptors,
            "ligature_counts": result.script_analysis.ligature_counts,
        }

        return {
            "total_pages": result.total_pages,
            "script_analysis": script_dict,
            "ocr_confidence": ocr_conf_dict,
            "detected_neologisms": [
                getattr(n, "to_dict", lambda: n.__dict__ if hasattr(n, "__dict__") else str(n))()
                for n in result.detected_neologisms
            ],
            "prefilled_terms": prefilled,
            "cost_quote": quote_dict,
            "sample_text": result.sample_text,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Pre-scan failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/vocabulary/{user_id}")
async def get_user_vocabulary_endpoint(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Retrieve saved terminology memory preferences for *user_id*."""
    _verify_resource_ownership(user_id, current_user)
    try:
        store = get_user_vocabulary_store()
        prefs = store.get_user_preferences(user_id) if hasattr(store, "get_user_preferences") else store.get_preferences(user_id)
        return {k: v.to_dict() if hasattr(v, "to_dict") else v.__dict__ for k, v in prefs.items()}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching vocabulary for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/vocabulary/{user_id}")
async def save_user_vocabulary_endpoint(
    user_id: str,
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Save or update user terminology memory preference."""
    _verify_resource_ownership(user_id, current_user)
    german_term = payload.get("german_term", "").strip()
    preferred_translation = payload.get("preferred_translation", "").strip()
    notes = payload.get("notes", "")
    keep_untranslated = bool(payload.get("keep_untranslated", False))
    confidence = float(payload.get("confidence", 1.0))

    if not german_term or not preferred_translation:
        raise HTTPException(status_code=400, detail="german_term and preferred_translation are required")

    try:
        store = get_user_vocabulary_store()
        saved = store.save_preference(
            user_id=user_id,
            german_term=german_term,
            preferred_translation=preferred_translation,
            notes=notes,
            keep_untranslated=keep_untranslated,
            confidence=confidence,
        )
        if hasattr(saved, "to_dict"):
            res = saved.to_dict()
            if isinstance(res, dict):
                return res
        if hasattr(saved, "__dict__") and isinstance(saved.__dict__, dict):
            return {k: v for k, v in saved.__dict__.items() if not k.startswith("_")}
        return {
            "german_term": german_term,
            "preferred_translation": preferred_translation,
            "notes": notes,
            "keep_untranslated": keep_untranslated,
            "confidence": confidence,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error saving vocabulary preference: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/vocabulary/{user_id}/bulk")
async def bulk_save_vocabulary_endpoint(
    user_id: str,
    payload: Any = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Bulk save or update user terminology preferences."""
    _verify_resource_ownership(user_id, current_user)
    if isinstance(payload, dict):
        preferences = payload.get("preferences", payload)
    else:
        preferences = payload
    try:
        store = get_user_vocabulary_store()
        count = store.bulk_save_preferences(user_id, preferences)
        return {"saved_count": count}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in bulk saving preferences: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/vocabulary/{user_id}/import")
async def import_vocabulary_tsv_endpoint(
    user_id: str,
    payload: Any = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Import terminology from RFC 4180 TSV content."""
    _verify_resource_ownership(user_id, current_user)
    if isinstance(payload, dict):
        tsv_content = payload.get("tsv_content", "")
    elif isinstance(payload, bytes):
        tsv_content = payload.decode("utf-8")
    else:
        tsv_content = str(payload)
    try:
        store = get_user_vocabulary_store()
        if hasattr(store, "import_rfc4180_tsv"):
            imported = store.import_rfc4180_tsv(user_id, tsv_content)
        elif hasattr(store, "import_tsv"):
            imported = store.import_tsv(user_id, tsv_content)
        else:
            imported = 0
        count = len(imported) if isinstance(imported, (list, dict, set)) else int(imported or 0)
        return {"imported_count": count}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error importing TSV vocabulary: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/vocabulary/{user_id}/export")
async def export_vocabulary_tsv_endpoint(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> Response:
    """Export user terminology preferences as RFC 4180 TSV."""
    _verify_resource_ownership(user_id, current_user)
    try:
        store = get_user_vocabulary_store()
        if hasattr(store, "export_tsv"):
            tsv_content = store.export_tsv(user_id)
        elif hasattr(store, "export_rfc4180_tsv"):
            tsv_content = store.export_rfc4180_tsv(user_id)
        else:
            tsv_content = b"de\ten\n"
        return Response(
            content=tsv_content,
            media_type="text/tab-separated-values",
            headers={"Content-Disposition": f"attachment; filename={user_id}_vocabulary.tsv"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error exporting TSV vocabulary: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/book/translate")
async def start_batch_translation_endpoint(
    user_id: str = Form(...),
    session_id: str = Form(...),
    book_id: str = Form(...),
    user_choices: str | None = Form(None),
    source_lang: str = Form("de"),
    target_lang: str = Form("en-US"),
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Stage book in GCS, synchronize session glossary, and dispatch asynchronous batch translation."""
    _verify_resource_ownership(user_id, current_user)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        parsed_choices = json.loads(user_choices) if user_choices else None

        orch = get_book_orchestrator()
        state = orch.start_book_translation(
            user_id=user_id,
            session_id=session_id,
            book_id=book_id,
            source=contents,
            user_choices=parsed_choices,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        return state.to_dict() if hasattr(state, "to_dict") else state.__dict__
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.error("Failed starting book batch translation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


def _verify_job_ownership(session_id: str, requested_user_id: str, orch: Any) -> None:
    """Verify that a stored job session belongs to requested_user_id.

    Prevents prefix-matching collision vulnerabilities where a caller with user_id 'user'
    could match and manipulate a session belonging to 'user_victim'.
    """
    recovery_mgr = getattr(orch, "recovery_manager", None)
    if recovery_mgr is not None:
        finder = getattr(recovery_mgr, "_find_job_by_session", None)
        if callable(finder):
            try:
                res = finder(session_id)
                if isinstance(res, tuple) and len(res) >= 2:
                    _path, state = res[0], res[1]
                    if state is not None and getattr(state, "user_id", None):
                        if state.user_id != requested_user_id:
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Access denied: Job session '{session_id}' belongs to another user",
                            )
            except HTTPException:
                raise
            except Exception:
                pass


@api_router.get("/book/status/{session_id}")
async def get_book_status_endpoint(
    session_id: str,
    user_id: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Poll live LRO progress and synchronize with BatchJobRecoveryManager."""
    _verify_resource_ownership(user_id, current_user)
    try:
        orch = get_book_orchestrator()
        _verify_job_ownership(session_id, user_id, orch)
        update = orch.poll_translation_progress(user_id=user_id, session_id=session_id)
        return {
            "operation_name": update.operation_name,
            "state": update.state,
            "total_pages": update.total_pages,
            "translated_pages": update.translated_pages,
            "failed_pages": update.failed_pages,
            "completion_pct": update.completion_pct,
            "is_done": update.is_done,
            "error_message": update.error_message,
        }
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Error polling progress for %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/book/resume/{session_id}")
async def resume_book_job_endpoint(
    session_id: str,
    user_id: str = Query(..., description="Owner user identifier of the job session"),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Reconnect to active or interrupted LRO job scoped to authorized user."""
    _verify_resource_ownership(user_id, current_user)
    try:
        orch = get_book_orchestrator()
        _verify_job_ownership(session_id, user_id, orch)
        state = orch.resume_job(session_id=session_id, user_id=user_id)
        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"No active job found for session '{session_id}' and user '{user_id}'",
            )
        if hasattr(state, "user_id") and state.user_id and state.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Resumed job belongs to another user",
            )
        return state.to_dict() if hasattr(state, "to_dict") else state.__dict__
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Error resuming job %s for user %s: %s", session_id, user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/book/jobs/{user_id}")
async def list_user_jobs_endpoint(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> list[dict[str, Any]]:
    """List active or recent batch translation jobs for *user_id*."""
    _verify_resource_ownership(user_id, current_user)
    try:
        orch = get_book_orchestrator()
        if hasattr(orch, "list_user_jobs"):
            jobs = orch.list_user_jobs(user_id)
        else:
            jobs = orch.recovery_manager.list_active_jobs(user_id)
        return [j.to_dict() if hasattr(j, "to_dict") else (j.__dict__ if hasattr(j, "__dict__") else dict(j)) for j in jobs]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error listing jobs for %s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/book/complete/{session_id}")
async def complete_job_endpoint(
    session_id: str,
    user_id: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Evaluate completed job and trigger session glossary cleanup if 0 failed pages."""
    _verify_resource_ownership(user_id, current_user)
    try:
        orch = get_book_orchestrator()
        _verify_job_ownership(session_id, user_id, orch)
        summary = orch.handle_job_completion(user_id=user_id, session_id=session_id)
        return summary.__dict__ if hasattr(summary, "__dict__") else {}
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Error handling completion for %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/book/export-drive")
async def export_to_drive_endpoint(
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Stream translated PDF directly from GCS to Google Drive using client GIS OAuth token."""
    user_id = payload.get("user_id", "").strip()
    session_id = payload.get("session_id", "").strip()
    access_token = payload.get("access_token", "").strip()
    filename = payload.get("filename")

    if not user_id or not session_id or not access_token:
        raise HTTPException(status_code=400, detail="user_id, session_id, and access_token are required")

    _verify_resource_ownership(user_id, current_user)

    try:
        orch = get_book_orchestrator()
        _verify_job_ownership(session_id, user_id, orch)
        result = orch.export_to_google_drive(
            user_id=user_id,
            session_id=session_id,
            access_token=access_token,
            filename=filename,
        )
        return {
            "file_id": result.file_id,
            "file_name": result.file_name,
            "web_view_link": result.web_view_link,
            "web_content_link": result.web_content_link,
            "created_time": result.created_time,
        }
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Drive export failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get("/book/download/{session_id}")
async def download_translated_book_endpoint(
    session_id: str,
    user_id: str = Query(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> Response:
    """Stream translated PDF directly from user's GCS bucket for direct browser download."""
    _verify_resource_ownership(user_id, current_user)
    try:
        orch = get_book_orchestrator()
        _verify_job_ownership(session_id, user_id, orch)
        if hasattr(orch, "download_translated_book"):
            res = orch.download_translated_book(user_id=user_id, session_id=session_id)
            if isinstance(res, tuple):
                stream_or_bytes, filename = res
            else:
                stream_or_bytes, filename = res, f"{session_id}_translated.pdf"
            if isinstance(stream_or_bytes, (bytes, bytearray)):
                return Response(
                    content=bytes(stream_or_bytes),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )
            return StreamingResponse(
                stream_or_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        state = orch.recovery_manager.resume_active_job(session_id, user_id=user_id)
        gcs_output_uri = f"{state.gcs_output_uri.rstrip('/')}/{state.book_id}_translated.pdf"
        stream = orch.batch_service.stream_translated_book(user_id, gcs_output_uri)
        return StreamingResponse(
            stream,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{state.book_id}_translated.pdf"'},
        )
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Download failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/book/fallback-translate")
async def fallback_translate_endpoint(
    user_id: str = Form(...),
    session_id: str = Form(...),
    failed_page_indices: str | None = Form(None),
    source_lang: str = Form("de"),
    target_lang: str = Form("en"),
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Trigger plaintext fallback extraction, translation, and splicing for failed layout pages."""
    _verify_resource_ownership(user_id, current_user)
    try:
        contents = await file.read()
        indices: list[int] | None = None
        if failed_page_indices:
            indices = [int(p.strip()) for p in failed_page_indices.split(",") if p.strip().isdigit()]

        orch = get_book_orchestrator()
        _verify_job_ownership(session_id, user_id, orch)
        res = orch.trigger_fallback_page_translation(
            user_id=user_id,
            session_id=session_id,
            source_pdf=contents,
            failed_page_indices=indices,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        return {
            "session_id": res.session_id,
            "failed_pages_count": res.failed_pages_count,
            "spliced_output_gcs_uri": res.spliced_output_gcs_uri,
            "success": res.success,
        }
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Fallback translation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.post("/book/dual-pane/{session_id}")
async def dual_pane_endpoint(
    session_id: str,
    user_id: str = Query(...),
    page_number: int = Query(1),
    render_images: bool = Query(True),
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user_dependency),
) -> dict[str, Any]:
    """Fetch synchronized German and English page pair for side-by-side reading mode."""
    _verify_resource_ownership(user_id, current_user)
    try:
        contents = await file.read()
        orch = get_book_orchestrator()
        _verify_job_ownership(session_id, user_id, orch)
        pair = orch.get_bilingual_view(
            user_id=user_id,
            session_id=session_id,
            german_source=contents,
            page_number=page_number,
            render_images=render_images,
        )
        return {
            "page_number": pair.page_number,
            "total_pages_german": pair.total_pages_german,
            "total_pages_english": pair.total_pages_english,
            "german_text": pair.german_text,
            "english_text": pair.english_text,
            "german_page_image_base64": getattr(pair, "german_page_image_base64", None),
            "english_page_image_base64": getattr(pair, "english_page_image_base64", None),
            "has_images": getattr(pair, "has_images", False),
        }
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Dual-pane view error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
