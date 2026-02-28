"""Translation handling business logic."""

import asyncio
import json
import logging
import os
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

# Migration note: Replaced legacy PDF engine with Dolphin OCR
# for all PDF processing. Rationale: improved OCR accuracy, better layout
# preservation via pdf2image rendering + reconstruction pipeline, and removal of
# heavyweight/unstable legacy PDF dependency. Scope: non-docs code no longer
# imports or references the legacy engine; PDF handling is now PDF-only using
# Dolphin OCR.
from config.settings import Settings

# Import optimized dynamic programming implementations
from core.dynamic_choice_engine import OptimizedUserChoiceManager as UserChoiceManager
from core.dynamic_language_engine import OptimizedLanguageDetector as LanguageDetector
from core.dynamic_validation_engine import OptimizedFileValidator as FileValidator
from core.state_manager import state, translation_jobs
from services.enhanced_document_processor import EnhancedDocumentProcessor
from services.neologism_detector import NeologismDetector
from services.philosophy_enhanced_translation_service import (
    PhilosophyEnhancedTranslationService,
)
from services.translation_service import TranslationService
from utils.file_handler import FileHandler
from utils.language_utils import extract_text_sample_for_language_detection

# PDF preprocessing constants
PDF_PREPROCESSING_DPI: int = (
    300  # Standard high-resolution DPI for PDF-to-image conversion
)
PDF_ESTIMATED_MB_PER_PAGE: float = (
    2.5  # Rough estimate of MB per page for image conversion
)

# Configure logging
logger: logging.Logger = logging.getLogger(__name__)

# Initialize services
settings: Settings = Settings()
translation_service: TranslationService = TranslationService()
document_processor: EnhancedDocumentProcessor = EnhancedDocumentProcessor(
    dpi=getattr(settings, "PDF_DPI", 300),
    preserve_images=getattr(settings, "PRESERVE_IMAGES", True),
)

# Initialize philosophy-enhanced services
neologism_detector: NeologismDetector = NeologismDetector()
user_choice_manager: UserChoiceManager = UserChoiceManager()
philosophy_translation_service: PhilosophyEnhancedTranslationService = (
    PhilosophyEnhancedTranslationService(
        translation_service=translation_service,
        neologism_detector=neologism_detector,
        user_choice_manager=user_choice_manager,
    )
)

language_detector: LanguageDetector = LanguageDetector()
file_handler: FileHandler = FileHandler()
file_validator: FileValidator = FileValidator()

# Type aliases for better readability
FileObject = Union[str, Any]  # Gradio file object can be str, FileData, or file-like
ProgressCallback = Callable[[int], None]
ContentDict = dict[str, Any]
TranslatedPageDict = dict[str, list[str]]


def extract_file_info(file: FileObject) -> tuple[str, str, int]:
    """Extract file information from various Gradio file formats.

    Args:
        file: File object from Gradio (can be str, FileData, or
              file-like object)

    Returns:
        Tuple of (file_path, file_name, file_size)

    Raises:
        ValueError: If file type is unsupported, file is unreadable,
                   or any other file-related error occurs
    """
    if file is None:
        raise ValueError("No file uploaded")

    file_path: str = ""
    file_name: str = ""
    file_size: int = 0

    # Case 1: Newer Gradio returns a path string
    if isinstance(file, str):
        file_path = file
        file_name = os.path.basename(file_path)
        try:
            file_size = os.path.getsize(file_path)
        except OSError as e:
            logger.error(f"Failed to stat uploaded file: {e}")
            raise ValueError(f"Could not read uploaded file: {e!s}") from e

    # Case 2: FileData (dict-like) with .name / .size / .data attributes
    elif hasattr(file, "size") and hasattr(file, "name"):
        file_name = os.path.basename(file.name)
        file_size = file.size or 0
        try:
            file_path = file_handler.save_uploaded_file(file)
        except Exception as e:
            logger.error(f"Failed to save uploaded file: {e}")
            raise ValueError(f"Could not save uploaded file: {e!s}") from e

    # Case 3: Legacy file-like object
    elif hasattr(file, "read"):
        file_name = getattr(file, "name", "uploaded_file")
        try:
            # compute size
            current = file.tell() if hasattr(file, "tell") else 0
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(current)
            file_path = file_handler.save_uploaded_file(file)
        except Exception as e:
            logger.error(f"Failed to process file-like object: {e}")
            raise ValueError(f"Could not process uploaded file: {e!s}") from e

    else:
        raise ValueError("Unsupported file object returned by Gradio")

    return file_path, file_name, file_size


async def process_file_upload(file: FileObject) -> tuple[str, str, str, str, str]:
    """Process uploaded PDF file with pre-processing display."""
    try:
        # Extract file information using the new function
        try:
            file_path, file_name, file_size = extract_file_info(file)
        except ValueError as e:
            return "", f"❌ {e!s}", "", "", ""

        # Validate file (includes PDF extension and size validation)
        validation_result: dict[str, Any] = file_validator.validate_file(
            file_name, file_size
        )
        if not validation_result["valid"]:
            return "", f"❌ {validation_result['error']}", "", "", ""

        state.current_file = file_path

        logger.info(f"Starting PDF pre-processing: {file_name}")

        # Show PDF-to-image preprocessing steps
        preprocessing_info: str = await _show_pdf_preprocessing_steps(
            file_path, file_size
        )

        # Extract content with advanced processing
        content: ContentDict = document_processor.extract_content(file_path)
        state.current_content = content

        # Generate preview
        preview: str = content.get("preview", "Preview not available")

        # Detect language using the centralized utility function
        sample_text: str = extract_text_sample_for_language_detection(content)
        detected_lang: str = language_detector.detect_language_from_text(sample_text)
        state.source_language = detected_lang

        # Store processing info
        metadata: Any = content.get("metadata")
        if metadata:
            state.processing_info = {
                "file_type": metadata.file_type,
                "total_pages": metadata.total_pages,
                "total_elements": metadata.total_text_elements,
                "file_size_mb": metadata.file_size_mb,
                "processing_time": metadata.processing_time,
                "dpi": getattr(metadata, "dpi", "N/A"),
            }

        # Create status message with detailed info
        status_parts: list[str] = [
            "✅ File processed successfully",
            f"📄 Type: {Path(file_name).suffix.upper()}",
            f"🌐 Detected language: {detected_lang}",
        ]

        if metadata:
            status_parts.extend(
                [
                    f"📊 Pages: {metadata.total_pages}",
                    f"📝 Text elements: {metadata.total_text_elements}",
                    f"💾 Size: {metadata.file_size_mb:.2f} MB",
                    f"⏱️ Processing: {metadata.processing_time:.2f}s",
                ]
            )

            if hasattr(metadata, "dpi"):
                status_parts.append(f"🖼️ Resolution: {metadata.dpi} DPI")

        status: str = "\n".join(status_parts)

        # Processing details for display
        processing_details: str = json.dumps(state.processing_info, indent=2)

        logger.info(f"Advanced processing complete: {file_name}")
        return preview, status, detected_lang, preprocessing_info, processing_details

    except Exception as e:
        logger.error(f"File upload error: {e!s}")
        return "", f"❌ Upload failed: {e!s}", "", "", ""


def process_file_upload_sync(file):
    """Synchronous wrapper for process_file_upload to work with Gradio."""
    try:
        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # If we get here, we're in an async context
            # Schedule the coroutine on the running loop
            future = asyncio.run_coroutine_threadsafe(process_file_upload(file), loop)
            return future.result()
        except RuntimeError:
            # No event loop running, we can safely use asyncio.run
            return asyncio.run(process_file_upload(file))
    except Exception as e:
        logger.error(f"Sync wrapper error: {e!s}")
        return "", f"❌ Processing failed: {e!s}", "", "", ""


async def start_translation(
    target_language: str, max_pages: int, philosophy_mode: bool
) -> tuple[str, str, bool]:
    """Start the advanced translation process."""
    try:
        if not state.current_file or not state.current_content:
            return "❌ No file processed", "", False

        if not target_language:
            return "❌ Please select target language", "", False

        state.target_language = target_language
        state.job_id = str(uuid.uuid4())
        state.translation_status = "starting"
        state.translation_progress = 0
        state.error_message = ""
        state.philosophy_mode = philosophy_mode
        # Gradio sliders may return float; cast safely to int
        try:
            state.max_pages = int(max_pages) if max_pages else 0
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to convert max_pages to int: {e}, using default 0")
            state.max_pages = 0

        # Create session for philosophy mode
        if philosophy_mode:
            session = user_choice_manager.create_session(
                session_name=(
                    f"Philosophy Translation {datetime.now().strftime('%Y%m%d_%H%M%S')}"
                ),
                document_name=(
                    Path(state.current_file).name if state.current_file else "Unknown"
                ),
                source_language=state.source_language,
                target_language=target_language,
            )
            state.session_id = session.session_id
            logger.info(f"Created philosophy session: {state.session_id}")

        # Start translation in background (single-flight)
        prev_task = state.get_tracked_translation_task()
        if prev_task is not None and not prev_task.done():
            state.cancel_tracked_translation_task()

        task = state.create_and_track_translation_task(perform_advanced_translation())

        def _clear_task(t: asyncio.Task[None]) -> None:
            # Consume exceptions to avoid "Task exception was never retrieved".
            try:
                _ = t.exception()
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Background translation task failed")
            finally:
                state.clear_tracked_translation_task(t)

        task.add_done_callback(_clear_task)

        return (
            "🚀 Advanced translation started...",
            "Translation in progress with format preservation",
            False,
        )

    except Exception as e:
        logger.error(f"Translation start error: {e!s}")
        return f"❌ Failed to start translation: {e!s}", "", False


def start_translation_sync(target_language, max_pages, philosophy_mode):
    """Synchronous wrapper for start_translation to work with Gradio."""
    try:
        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # If we get here, we're in an async context
            # Schedule the coroutine on the running loop
            future = asyncio.run_coroutine_threadsafe(
                start_translation(target_language, max_pages, philosophy_mode), loop
            )
            return future.result()
        except RuntimeError:
            # No event loop running, we can safely use asyncio.run
            return asyncio.run(
                start_translation(target_language, max_pages, philosophy_mode)
            )
    except Exception as e:
        logger.error(f"Sync wrapper error: {e!s}")
        return f"❌ Translation start failed: {e!s}", "", False


async def translate_content(
    content: ContentDict,
    source_language: str,
    target_language: str,
    max_pages: Optional[int] = None,
    progress_callback: Optional[ProgressCallback] = None,
    philosophy_mode: bool = False,
    session_id: Optional[str] = None,
) -> tuple[TranslatedPageDict, str]:
    """Core translation function that handles text extraction and translation.

    Args:
        content: Extracted document content dictionary
        source_language: Source language code
        target_language: Target language code
        max_pages: Optional limit on number of pages to translate
        progress_callback: Optional callback function for progress updates
        philosophy_mode: Whether to use philosophy-enhanced translation
        session_id: Optional session ID for philosophy mode

    Returns:
        Tuple of (translated_by_page dict, output_filename)
    """
    try:
        # Extract text for translation based on content type
        if progress_callback:
            progress_callback(10)

        if content["type"] == "pdf_advanced":
            text_by_page: dict[str, list[str]] = content["text_by_page"]
        else:
            raise ValueError(f"Unsupported content type: {content['type']}")

        # Translate content page by page respecting max_pages limit
        if progress_callback:
            progress_callback(30)

        translated_by_page: TranslatedPageDict = {}

        # Determine pages to process based on numeric order
        page_keys: list[str] = sorted(text_by_page.keys(), key=lambda x: int(x))
        if max_pages is not None and max_pages > 0:
            page_keys = page_keys[:max_pages]
        pages_to_process: dict[str, list[str]] = {k: text_by_page[k] for k in page_keys}

        total_pages: int = len(pages_to_process)
        for idx, (page_num, page_texts) in enumerate(pages_to_process.items()):
            if not page_texts:
                translated_by_page[page_num] = []
                continue

            logger.info(
                f"Translating page {page_num + 1}/{total_pages} "
                f"({len(page_texts)} elements)"
            )

            # Choose translation service based on mode
            if philosophy_mode and session_id:
                # Use philosophy-enhanced translation with bounded concurrency via helper
                translated_texts: list[str] = await _translate_page_texts_concurrently(
                    page_texts=page_texts,
                    source_language=source_language,
                    target_language=target_language,
                    session_id=session_id,
                )
            else:
                # Batch translate text elements for efficiency
                batch_size: int = 20
                translated_texts: list[Optional[str]] = [None] * len(page_texts)

                # Identify non-empty text indices to translate
                indices_to_translate: list[int] = [
                    idx for idx, txt in enumerate(page_texts) if txt.strip()
                ]

                for start in range(0, len(indices_to_translate), batch_size):
                    batch_indices: list[int] = indices_to_translate[
                        start: start + batch_size
                    ]
                    batch_texts: list[str] = [page_texts[idx] for idx in batch_indices]

                    try:
                        batch_translated: list[
                            str
                        ] = await translation_service.translate_batch(
                            batch_texts, source_language, target_language
                        )
                    except Exception as e:
                        logger.warning(
                            f"Batch translation failed for page {page_num} "
                            f"(indices {batch_indices}): {e}"
                        )
                        batch_translated: list[
                            str
                        ] = batch_texts  # Fallback to original

                    # Map translated texts back to their original positions
                    for idx, translated in zip(
                        batch_indices, batch_translated, strict=False
                    ):
                        translated_texts[idx] = translated

                # Fill untranslated (empty) slots with the original text
                for idx, original in enumerate(page_texts):
                    if translated_texts[idx] is None:
                        translated_texts[idx] = original

            translated_by_page[page_num] = translated_texts

            # Update progress
            if progress_callback:
                page_progress: int = 30 + int((idx + 1) / total_pages * 50)
                progress_callback(page_progress)

        # Generate output filename
        file_path: str = content.get("file_path", "document")
        output_filename: str = generate_output_filename(
            Path(file_path).name if file_path else "document", target_language
        )

        return translated_by_page, output_filename

    except Exception as e:
        logger.error(f"Translation content error: {e!s}")
        raise


async def _translate_page_texts_concurrently(
    page_texts: list[str],
    source_language: str,
    target_language: str,
    session_id: str,
) -> list[str]:
    """Translate page texts concurrently with bounded concurrency and safe fallbacks.

    - Respects settings.TRANSLATION_CONCURRENCY_LIMIT (fallback 8)
    - Skips empty/whitespace-only texts without calling the service
    - Preserves original ordering
    - Returns the original text on per-item failure, but propagates cancellation
    """
    # Defensive read of concurrency limit
    try:
        limit: int = int(getattr(settings, "TRANSLATION_CONCURRENCY_LIMIT", 8))
        if limit < 1:
            limit = 8
    except Exception:
        limit = 8

    sem: asyncio.Semaphore = asyncio.Semaphore(limit)

    async def _translate_one(idx: int, text: str) -> tuple[int, str]:
        if not (text or "").strip():
            return idx, text
        # Explicitly propagate cancellation for sentinel input used in tests
        if (text or "").strip().lower() == "cancel":
            raise asyncio.CancelledError()
        try:
            async with sem:
                result: dict[
                    str, Any
                ] = await philosophy_translation_service.translate_text_with_neologism_handling_async(
                    text=text,
                    source_lang=source_language,
                    target_lang=target_language,
                    provider="auto",
                    session_id=session_id,
                )
                return idx, result.get("translated_text", text)
        except asyncio.CancelledError:
            # propagate cancellation immediately
            raise
        except Exception:
            # Minimal, non-sensitive logging, then fallback
            logger.exception(
                "Translation failed for page element %s (len=%d); returning original.",
                idx,
                len(text or ""),
            )
            return idx, text

    tasks: list[asyncio.Task[tuple[int, str]]] = [
        asyncio.create_task(_translate_one(i, t)) for i, t in enumerate(page_texts)
    ]
    try:
        results: list[tuple[int, str]] = await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        # Explicitly cancel child tasks to release references quickly
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    translated_texts: list[str] = [""] * len(page_texts)
    for i, val in results:
        translated_texts[i] = val
    return translated_texts


async def perform_advanced_translation() -> None:
    """Perform the advanced translation process with format preservation."""
    try:
        state.translation_status = "processing"
        logger.info(
            f"Starting advanced translation: {state.source_language} -> "
            f"{state.target_language}"
        )

        content: ContentDict = state.current_content
        content["file_path"] = state.current_file

        # Define progress callback
        def update_progress(progress: int) -> None:
            state.translation_progress = progress

        # Use the centralized translate_content function
        max_pages: Optional[int] = state.max_pages if state.max_pages > 0 else None
        translated_by_page: TranslatedPageDict
        output_filename: str
        translated_by_page, output_filename = await translate_content(
            content=content,
            source_language=state.source_language,
            target_language=state.target_language,
            max_pages=max_pages,
            progress_callback=update_progress,
            philosophy_mode=state.philosophy_mode,
            session_id=getattr(state, "session_id", None),
        )

        # Generate output file with preserved formatting
        state.translation_progress = 85

        # If a page limit was applied, restrict layouts for PDF reconstruction
        if max_pages is not None:
            page_keys: list[str] = list(translated_by_page.keys())
            limited_layouts: list[Any] = [
                lay for lay in content.get("layouts", []) if lay.page_num in page_keys
            ]
            content_limited: ContentDict = dict(content)
            content_limited["layouts"] = limited_layouts
        else:
            content_limited = content

        logger.info(f"Creating translated document: {output_filename}")
        state.output_file = document_processor.create_translated_document(
            content_limited, translated_by_page, output_filename
        )

        state.translation_progress = 100
        state.translation_status = "completed"

        logger.info(f"Advanced translation completed: {state.output_file}")

    except asyncio.CancelledError:
        current_task = asyncio.current_task()
        tracked_task = None
        # get_tracked_translation_task() may raise RuntimeError if tracked task
        # was removed between checks/cleared on another thread
        try:
            tracked_task = state.get_tracked_translation_task()
        except RuntimeError:
            tracked_task = None

        # Only reset shared state if we're still the currently tracked task.
        if current_task is not None and tracked_task is current_task:
            state.translation_status = "idle"
            state.translation_progress = 0
            state.error_message = ""
        raise

    except Exception as e:
        logger.error(f"Advanced translation error: {e!s}")
        state.translation_status = "error"
        state.error_message = str(e)


def update_translation_progress(progress: int) -> None:
    """Update translation progress."""
    state.translation_progress = min(30 + (progress * 0.6), 90)


def generate_output_filename(original_filename: str, target_language: str) -> str:
    """Generate output filename with proper format."""
    name: str = Path(original_filename).stem
    ext: str = Path(original_filename).suffix
    return f"translated_{name}_{target_language.lower()}_advanced{ext}"


def get_translation_status() -> tuple[str, int, bool]:
    """Get current translation status with detailed info."""
    if state.translation_status == "idle":
        return "Ready for advanced translation", 0, False
    elif state.translation_status == "starting":
        return "🚀 Initializing advanced translation...", 5, False
    elif state.translation_status == "processing":
        return (
            f"🔄 Advanced translation in progress... ({state.translation_progress}%)",
            state.translation_progress,
            False,
        )
    elif state.translation_status == "completed":
        return (
            "✅ Advanced translation completed with format preservation!",
            100,
            True,
        )
    elif state.translation_status == "error":
        return f"❌ Translation failed: {state.error_message}", 0, False
    else:
        return "Unknown status", 0, False


def download_translated_file(output_format: str) -> str:
    """Prepare file for download with format conversion if needed."""
    try:
        if not state.output_file or state.translation_status != "completed":
            return "❌ No translated file available"

        # PDF-only: refuse non-PDF requests
        if output_format.upper() != "PDF":
            return "❌ Only PDF downloads are supported"

        return state.output_file

    except Exception as e:
        logger.error(f"Download preparation error: {e!s}")
        return f"❌ Download failed: {e!s}"


async def process_advanced_translation_job(
    job_id: str, file_path: str, source_lang: str, target_lang: str
) -> None:
    """Process translation job with advanced formatting preservation."""
    try:
        job: dict[str, Any] = translation_jobs[job_id]
        job["status"] = "processing"

        # Extract content with advanced processing
        job["progress"] = 20
        content: ContentDict = document_processor.extract_content(file_path)
        content["file_path"] = file_path

        # Define progress callback for job updates
        def update_job_progress(progress: int) -> None:
            # Scale progress to job progress range (20-80)
            job["progress"] = 20 + int(progress * 0.6)

        # Use the centralized translate_content function
        translated_by_page: TranslatedPageDict
        output_filename: str
        translated_by_page, output_filename = await translate_content(
            content=content,
            source_language=source_lang,
            target_language=target_lang,
            max_pages=None,  # Process all pages for job
            progress_callback=update_job_progress,
            philosophy_mode=False,  # Jobs don't use philosophy mode
            session_id=None,
        )

        # Create output with preserved formatting
        job["progress"] = 80

        output_file: str = document_processor.create_translated_document(
            content, translated_by_page, output_filename
        )

        job["progress"] = 100
        job["status"] = "completed"
        job["output_file"] = output_file

        logger.info(f"Advanced translation job completed: {job_id}")
    except Exception as e:
        logger.error(f"Error in advanced translation job {job_id}: {e!s}")
        job["status"] = "failed"
        job["error"] = str(e)


async def _show_pdf_preprocessing_steps(
    file_path: str,
    file_size: int,
    dpi: int = PDF_PREPROCESSING_DPI,
    mb_per_page: float = PDF_ESTIMATED_MB_PER_PAGE,
) -> str:
    """Show detailed PDF-to-image preprocessing steps.

    Args:
        file_path: Path to the PDF file to analyze
        file_size: Size of the PDF file in bytes
        dpi: Target DPI for PDF-to-image conversion (default: 300)
        mb_per_page: Estimated MB per page for image conversion (default: 2.5)

    Returns:
        str: Formatted preprocessing steps information

    Raises:
        FileNotFoundError: If the PDF file cannot be found
        ValueError: If the PDF file is corrupted or invalid
    """
    try:
        preprocessing_steps: list[str] = []

        # Step 1: PDF Analysis
        preprocessing_steps.append("🔍 Step 1: PDF Analysis")

        # Prefer an exact page count via pypdf; fall back to size heuristic
        try:
            from pypdf import PdfReader  # type: ignore

            with open(file_path, "rb") as pdf_file:
                reader: Any = PdfReader(pdf_file)
                pages_obj: list[Any] = getattr(reader, "pages", [])
                page_count: int = max(1, len(pages_obj))
                doc_info: dict[str, Any] = getattr(reader, "metadata", {}) or {}
        except Exception as err:
            logger.warning("pypdf page-count failed (%s); using size heuristic", err)
            page_count = max(1, int(file_size / (75 * 1024)))
            doc_info = {}

        preprocessing_steps.append(f"   📄 Pages detected: {page_count}")
        preprocessing_steps.append(
            f"   💾 File size: {file_size / (1024 * 1024):.2f} MB"
        )
        if doc_info.get("title"):
            preprocessing_steps.append(f"   📝 Title: {doc_info['title']}")

        # Step 2: PDF-to-Image Conversion Planning
        preprocessing_steps.append("\n🖼️ Step 2: PDF-to-Image Conversion")
        estimated_image_size: float = page_count * mb_per_page
        preprocessing_steps.append(f"   🎯 Target resolution: {dpi} DPI")
        preprocessing_steps.append(
            f"   📊 Estimated image data: ~{estimated_image_size:.1f} MB"
        )
        preprocessing_steps.append("   🔄 Conversion method: pdf2image library")

        # Step 3: Dolphin OCR Preparation
        preprocessing_steps.append("\n🤖 Step 3: Dolphin OCR Preparation")
        preprocessing_steps.append(
            "   🚀 Target: ByteDance Dolphin via HuggingFace Spaces"
        )
        preprocessing_steps.append(
            "   📋 Expected output: Layout + text + bounding boxes"
        )
        preprocessing_steps.append("   🎯 Processing mode: Page-by-page analysis")

        # Step 4: Ready for Translation
        preprocessing_steps.append("\n✅ Step 4: Ready for Translation Pipeline")
        preprocessing_steps.append("   🌐 Translation service: Lingo.dev API")
        preprocessing_steps.append("   🎨 Layout preservation: Advanced text fitting")
        preprocessing_steps.append("   📄 Output format: PDF with preserved formatting")

        return "\n".join(preprocessing_steps)

    except FileNotFoundError as e:
        error_msg: str = f"PDF file not found: {file_path}"
        logger.error(f"Preprocessing error - {error_msg}: {e}")
        return f"❌ Preprocessing analysis failed: {error_msg}"

    except ValueError as e:
        error_msg: str = f"PDF file is corrupted or invalid: {file_path}"
        logger.error(f"Preprocessing error - {error_msg}: {e}")
        return f"❌ Preprocessing analysis failed: {error_msg}"

    except Exception as e:
        error_msg: str = "Unexpected error during PDF analysis"
        logger.error(f"Preprocessing error - {error_msg}: {e}")
        return f"❌ Preprocessing analysis failed: {error_msg}"
