"""FastAPI route handlers for document translation API."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

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

# Import dolphin client for configuration exposure
from services.dolphin_client import DEFAULT_LOCAL_ENDPOINT, DEFAULT_MODAL_ENDPOINT

# Import services for configuration endpoints
from services.philosophical_context_analyzer import PhilosophicalContextAnalyzer
from services.neologism_detector import NeologismDetector
from services.philosophy_enhanced_translation_service import (
    PhilosophyEnhancedTranslationService,
    translate_with_philosophy_awareness,
)
from services.neologism_detector import NeologismDetector, merge_neologism_analyses
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
            "pattern_types": list(scorer.patterns.keys()),
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
            if isinstance(threshold, (int, float)) and 0 <= threshold <= 1:
                scorer.adjust_confidence_threshold(threshold)
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
        factors = scorer.calculate_confidence_factors(term)
        
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
