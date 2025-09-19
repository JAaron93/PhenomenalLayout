"""Philosophy-Enhanced Document Processor with integrated neologism detection and user choice management."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.dynamic_choice_engine import OptimizedUserChoiceManager as UserChoiceManager
from models.neologism_models import NeologismAnalysis

from .enhanced_document_processor import EnhancedDocumentProcessor
from .neologism_detector import NeologismDetector
from .philosophy_enhanced_translation_service import (
    PhilosophyEnhancedTranslationService,
    PhilosophyTranslationProgress,
)

logger = logging.getLogger(__name__)


@dataclass
class PhilosophyProcessingProgress:
    """Extended progress tracking for philosophy-enhanced document processing."""

    # Document processing progress
    extraction_progress: int = 0
    neologism_detection_progress: int = 0
    user_choice_progress: int = 0
    translation_progress: int = 0
    reconstruction_progress: int = 0

    # Detailed metrics
    total_pages: int = 0
    processed_pages: int = 0
    total_text_blocks: int = 0
    processed_text_blocks: int = 0

    # Neologism-specific metrics
    total_neologisms: int = 0
    processed_neologisms: int = 0
    choices_applied: int = 0

    # Time tracking
    start_time: float = 0.0
    current_stage: str = "initializing"

    @property
    def overall_progress(self) -> float:
        """Calculate overall progress percentage."""
        stage_weights = {
            "extraction": 0.15,
            "neologism_detection": 0.25,
            "user_choice": 0.15,
            "translation": 0.35,
            "reconstruction": 0.10,
        }

        total_progress = (
            self.extraction_progress * stage_weights["extraction"]
            + self.neologism_detection_progress * stage_weights["neologism_detection"]
            + self.user_choice_progress * stage_weights["user_choice"]
            + self.translation_progress * stage_weights["translation"]
            + self.reconstruction_progress * stage_weights["reconstruction"]
        )

        return total_progress

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since processing started."""
        return time.time() - self.start_time if self.start_time > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "extraction_progress": self.extraction_progress,
            "neologism_detection_progress": self.neologism_detection_progress,
            "user_choice_progress": self.user_choice_progress,
            "translation_progress": self.translation_progress,
            "reconstruction_progress": self.reconstruction_progress,
            "total_pages": self.total_pages,
            "processed_pages": self.processed_pages,
            "total_text_blocks": self.total_text_blocks,
            "processed_text_blocks": self.processed_text_blocks,
            "total_neologisms": self.total_neologisms,
            "processed_neologisms": self.processed_neologisms,
            "choices_applied": self.choices_applied,
            "overall_progress": self.overall_progress,
            "elapsed_time": self.elapsed_time,
            "current_stage": self.current_stage,
        }


@dataclass
class PhilosophyDocumentResult:
    """Result of philosophy-enhanced document processing."""

    # Document content
    translated_content: dict[str, Any]
    original_content: dict[str, Any]

    # Neologism analysis
    document_neologism_analysis: NeologismAnalysis
    page_neologism_analyses: list[NeologismAnalysis]

    # User choice information
    session_id: Optional[str]
    total_choices_applied: int

    # Processing metadata
    processing_metadata: dict[str, Any]

    # Performance metrics
    processing_time: float
    neologism_detection_time: float
    translation_time: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "translated_content": self.translated_content,
            "original_content": self.original_content,
            "document_neologism_analysis": self.document_neologism_analysis.to_dict(),
            "page_neologism_analyses": [
                analysis.to_dict() for analysis in self.page_neologism_analyses
            ],
            "session_id": self.session_id,
            "total_choices_applied": self.total_choices_applied,
            "processing_metadata": self.processing_metadata,
            "processing_time": self.processing_time,
            "neologism_detection_time": self.neologism_detection_time,
            "translation_time": self.translation_time,
        }


class PhilosophyEnhancedDocumentProcessor:
    """Enhanced document processor with comprehensive neologism detection and user choice management.

    This processor extends the EnhancedDocumentProcessor with:
    - Integrated neologism detection during document processing
    - User choice application for handling detected neologisms
    - Enhanced progress tracking for large documents
    - Preservation of existing PDF processing capabilities
    - Session management for user choices
    """

    def __init__(
        self,
        base_processor: Optional[EnhancedDocumentProcessor] = None,
        philosophy_translation_service: Optional[
            PhilosophyEnhancedTranslationService
        ] = None,
        neologism_detector: Optional[NeologismDetector] = None,
        user_choice_manager: Optional[UserChoiceManager] = None,
        dpi: int = 300,
        preserve_images: bool = True,
        terminology_path: Optional[str] = None,
        enable_batch_processing: bool = True,
        max_concurrent_pages: int = 5,
    ):
        """Initialize the philosophy-enhanced document processor.

        Args:
            base_processor: Base document processor instance
            philosophy_translation_service: Philosophy-enhanced translation service
            neologism_detector: Neologism detection service
            user_choice_manager: User choice management service
            dpi: Resolution for PDF processing
            preserve_images: Whether to preserve images in PDFs
            terminology_path: Path to terminology file
            enable_batch_processing: Whether to enable batch processing
            max_concurrent_pages: Maximum concurrent page processing
        """
        # Initialize base processor
        self.base_processor = base_processor or EnhancedDocumentProcessor(
            dpi=dpi, preserve_images=preserve_images
        )

        # Initialize philosophy-enhanced translation service
        self.philosophy_translation_service = (
            philosophy_translation_service
            or PhilosophyEnhancedTranslationService(terminology_path=terminology_path)
        )

        # Initialize neologism detector
        self.neologism_detector = neologism_detector or NeologismDetector(
            terminology_path=terminology_path
        )

        # Initialize user choice manager
        self.user_choice_manager = user_choice_manager or UserChoiceManager()

        # Configuration
        self.enable_batch_processing = enable_batch_processing
        self.max_concurrent_pages = max_concurrent_pages

        # Statistics tracking
        self.stats = {
            "documents_processed": 0,
            "total_neologisms_detected": 0,
            "total_choices_applied": 0,
            "total_processing_time": 0.0,
            "average_neologisms_per_page": 0.0,
            "choice_application_rate": 0.0,
        }

        logger.info("PhilosophyEnhancedDocumentProcessor initialized")

    def extract_content(self, file_path: str) -> dict[str, Any]:
        """Extract content from document with enhanced philosophy-aware processing.

        Args:
            file_path: Path to the document file

        Returns:
            Dictionary containing extracted content and metadata
        """
        # Use base processor for content extraction
        content = self.base_processor.extract_content(file_path)

        # Add philosophy-enhanced metadata
        content["philosophy_enhanced"] = True
        content["neologism_detection_ready"] = True

        return content

    async def process_document_with_philosophy_awareness(
        self,
        file_path: str,
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        philosophy_mode: bool = True,
        progress_callback: Optional[
            Callable[[PhilosophyProcessingProgress], None]
        ] = None,
    ) -> PhilosophyDocumentResult:
        """Process document with comprehensive philosophy-aware translation.

        Args:
            file_path: Path to the document file
            source_lang: Source language code
            target_lang: Target language code
            provider: Translation provider to use
            user_id: User ID for session management
            session_id: Existing session ID or None to create new
            philosophy_mode: Enable philosophy-aware processing features
            progress_callback: Optional progress callback

        Returns:
            PhilosophyDocumentResult with comprehensive processing results
        """
        start_time = time.time()

        # Initialize progress tracking
        progress = PhilosophyProcessingProgress()
        progress.start_time = start_time
        progress.current_stage = "extraction"

        try:
            # Step 1: Extract document content
            logger.info(f"Extracting content from {file_path}")
            original_content = await self._extract_content_async(
                file_path, progress, progress_callback
            )

            # Step 2: Create or get user session
            if not session_id:
                session_id = await self._create_session_async(
                    file_path, user_id, source_lang, target_lang
                )

            # Step 3: Detect neologisms across the document
            logger.info("Detecting neologisms in document content")
            progress.current_stage = "neologism_detection"
            neologism_results = await self._detect_document_neologisms_async(
                original_content, progress, progress_callback
            )

            # Step 4: Apply user choices
            logger.info("Applying user choices to detected neologisms")
            progress.current_stage = "user_choice"
            choice_results = await self._apply_document_choices_async(
                neologism_results, session_id, progress, progress_callback
            )

            # Step 5: Translate with philosophy awareness
            logger.info("Translating document with philosophy awareness")
            progress.current_stage = "translation"
            translation_start_time = time.time()
            translated_content = await self._translate_document_async(
                original_content,
                source_lang,
                target_lang,
                provider,
                session_id,
                progress,
                progress_callback,
            )
            translation_time = time.time() - translation_start_time

            # Step 6: Reconstruct document
            logger.info("Reconstructing document with enhanced metadata")
            progress.current_stage = "reconstruction"
            final_content = await self._reconstruct_document_async(
                translated_content,
                neologism_results,
                choice_results,
                progress,
                progress_callback,
            )

            # Update statistics
            self.stats["documents_processed"] += 1
            self.stats["total_neologisms_detected"] += neologism_results[
                "total_neologisms"
            ]
            self.stats["total_choices_applied"] += choice_results[
                "total_choices_applied"
            ]

            processing_time = time.time() - start_time
            self.stats["total_processing_time"] += processing_time

            # Create result
            result = PhilosophyDocumentResult(
                translated_content=final_content,
                original_content=original_content,
                document_neologism_analysis=neologism_results["document_analysis"],
                page_neologism_analyses=neologism_results["page_analyses"],
                session_id=session_id,
                total_choices_applied=choice_results["total_choices_applied"],
                processing_metadata={
                    "file_path": file_path,
                    "source_language": source_lang,
                    "target_language": target_lang,
                    "provider_used": provider,
                    "user_id": user_id,
                    "total_pages": progress.total_pages,
                    "total_text_blocks": progress.total_text_blocks,
                    "total_neologisms": progress.total_neologisms,
                },
                processing_time=processing_time,
                neologism_detection_time=neologism_results["detection_time"],
                translation_time=translation_time,
            )

            # Final progress update
            progress.current_stage = "completed"
            progress.extraction_progress = 100
            progress.neologism_detection_progress = 100
            progress.user_choice_progress = 100
            progress.translation_progress = 100
            progress.reconstruction_progress = 100
            if progress_callback:
                progress_callback(progress)

            return result

        except Exception as e:
            logger.error(f"Error in philosophy-enhanced document processing: {e}")
            raise

    async def _extract_content_async(
        self,
        file_path: str,
        progress: PhilosophyProcessingProgress,
        progress_callback: Optional[
            Callable[[PhilosophyProcessingProgress], None]
        ] = None,
    ) -> dict[str, Any]:
        """Extract content asynchronously with progress tracking."""
        # Run extraction in thread to avoid blocking
        content = await asyncio.to_thread(
            self.base_processor.extract_content, file_path
        )

        # Update progress metrics
        if content.get("type") == "pdf_advanced" and "layouts" in content:
            progress.total_pages = len(content["layouts"])
            progress.total_text_blocks = sum(
                len(layout.text_elements) for layout in content["layouts"]
            )
        elif "pages" in content:
            progress.total_pages = len(content["pages"])
            progress.total_text_blocks = sum(
                len(page.get("text_blocks", [])) for page in content["pages"]
            )

        progress.extraction_progress = 100
        if progress_callback:
            progress_callback(progress)

        return content

    async def _create_session_async(
        self, file_path: str, user_id: Optional[str], source_lang: str, target_lang: str
    ) -> str:
        """Create a new user session for document processing."""
        document_name = Path(file_path).name

        session = await asyncio.to_thread(
            self.user_choice_manager.create_session,
            session_name=f"Processing: {document_name}",
            document_name=document_name,
            user_id=user_id,
            source_language=source_lang,
            target_language=target_lang,
        )

        return session.session_id

    async def _detect_document_neologisms_async(
        self,
        content: dict[str, Any],
        progress: PhilosophyProcessingProgress,
        progress_callback: Optional[
            Callable[[PhilosophyProcessingProgress], None]
        ] = None,
    ) -> dict[str, Any]:
        """Detect neologisms across the entire document."""
        detection_start_time = time.time()

        # Extract text from all pages
        all_text = self._extract_all_text_from_content(content)

        # Detect neologisms in full document
        document_analysis = await asyncio.to_thread(
            self.neologism_detector.analyze_text,
            all_text,
            text_id=f"document_{int(time.time())}",
        )

        # Detect neologisms per page for detailed analysis
        page_analyses = []
        if content.get("type") == "pdf_advanced" and "text_by_page" in content:
            for page_num, page_text in content["text_by_page"].items():
                if page_text.strip():
                    page_analysis = await asyncio.to_thread(
                        self.neologism_detector.analyze_text,
                        page_text,
                        text_id=f"page_{page_num}",
                    )
                    page_analyses.append(page_analysis)

                    # Update progress
                    progress.processed_pages += 1
                    progress.neologism_detection_progress = (
                        int((progress.processed_pages / progress.total_pages) * 100)
                        if progress.total_pages > 0
                        else 100
                    )

                    if progress_callback:
                        progress_callback(progress)

        # Update total neologisms count
        progress.total_neologisms = len(document_analysis.detected_neologisms)

        detection_time = time.time() - detection_start_time

        return {
            "document_analysis": document_analysis,
            "page_analyses": page_analyses,
            "total_neologisms": len(document_analysis.detected_neologisms),
            "detection_time": detection_time,
        }

    def _extract_all_text_from_content(self, content: dict[str, Any]) -> str:
        """Extract all text from document content."""
        all_text = ""

        if content.get("type") == "pdf_advanced":
            if "text_by_page" in content:
                for page_text in content["text_by_page"].values():
                    all_text += page_text + "\n\n"
        elif content.get("type") in {"docx", "txt"}:
            all_text = content.get("text_content", "")
        elif "pages" in content:
            for page in content["pages"]:
                if "text_blocks" in page:
                    for block in page["text_blocks"]:
                        all_text += block.get("text", "") + "\n"

        return all_text

    async def _apply_document_choices_async(
        self,
        neologism_results: dict[str, Any],
        session_id: str,
        progress: PhilosophyProcessingProgress,
        progress_callback: Optional[
            Callable[[PhilosophyProcessingProgress], None]
        ] = None,
    ) -> dict[str, Any]:
        """Apply user choices to detected neologisms."""
        document_analysis = neologism_results["document_analysis"]
        total_choices_applied = 0

        # Process each detected neologism
        for neologism in document_analysis.detected_neologisms:
            # Check for existing user choice
            existing_choice = await asyncio.to_thread(
                self.user_choice_manager.get_choice_for_neologism, neologism, session_id
            )

            if existing_choice:
                total_choices_applied += 1
                progress.choices_applied += 1

            # Update progress
            progress.processed_neologisms += 1
            progress.user_choice_progress = (
                int((progress.processed_neologisms / progress.total_neologisms) * 100)
                if progress.total_neologisms > 0
                else 100
            )

            if progress_callback:
                progress_callback(progress)

        return {
            "total_choices_applied": total_choices_applied,
            "processed_neologisms": progress.processed_neologisms,
        }

    async def _translate_document_async(
        self,
        content: dict[str, Any],
        source_lang: str,
        target_lang: str,
        provider: str,
        session_id: str,
        progress: PhilosophyProcessingProgress,
        progress_callback: Optional[
            Callable[[PhilosophyProcessingProgress], None]
        ] = None,
    ) -> dict[str, Any]:
        """Translate document with philosophy awareness."""

        # Create translation progress callback
        def translation_progress_callback(
            translation_progress: PhilosophyTranslationProgress,
        ):
            progress.translation_progress = int(translation_progress.overall_progress)
            if progress_callback:
                progress_callback(progress)

        # Use philosophy-enhanced translation service
        result = await self.philosophy_translation_service.translate_document_with_neologism_handling(
            content,
            source_lang,
            target_lang,
            provider,
            session_id,
            translation_progress_callback,
        )

        return result["translated_content"]

    async def _reconstruct_document_async(
        self,
        translated_content: dict[str, Any],
        neologism_results: dict[str, Any],
        choice_results: dict[str, Any],
        progress: PhilosophyProcessingProgress,
        progress_callback: Optional[
            Callable[[PhilosophyProcessingProgress], None]
        ] = None,
    ) -> dict[str, Any]:
        """Reconstruct document with enhanced metadata."""
        # Add neologism analysis metadata to the translated content
        translated_content["philosophy_enhanced_metadata"] = {
            "neologism_analysis": neologism_results["document_analysis"].to_dict(),
            "page_analyses": [
                analysis.to_dict() for analysis in neologism_results["page_analyses"]
            ],
            "total_neologisms_detected": neologism_results["total_neologisms"],
            "total_choices_applied": choice_results["total_choices_applied"],
            "processing_timestamp": datetime.now().isoformat(),
        }

        progress.reconstruction_progress = 100
        if progress_callback:
            progress_callback(progress)

        return translated_content

    async def create_translated_document_with_philosophy_awareness(
        self, processing_result: PhilosophyDocumentResult, output_filename: str
    ) -> str:
        """Create translated document with philosophy-aware enhancements."""
        # Extract necessary data
        translated_content = processing_result.translated_content
        original_content = processing_result.original_content

        # Create translated texts mapping for base processor
        translated_texts = {}

        if "pages" in translated_content:
            for page_num, page in enumerate(translated_content["pages"]):
                if "text_blocks" in page:
                    page_texts = []
                    for block in page["text_blocks"]:
                        page_texts.append(block.get("text", ""))
                    translated_texts[page_num] = page_texts

        # Use base processor to create the document
        output_path = await asyncio.to_thread(
            self.base_processor.create_translated_document,
            original_content,
            translated_texts,
            output_filename,
        )

        # Add philosophy-enhanced metadata as a separate JSON file
        metadata_path = (
            str(Path(output_path).with_suffix("")) + "_philosophy_metadata.json"
        )
        try:
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(processing_result.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Philosophy-enhanced metadata saved to: {metadata_path}")
        except Exception as e:
            logger.warning(f"Could not save philosophy metadata: {e}")

        return output_path

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive processor statistics."""
        base_stats = {
            "documents_processed": self.stats["documents_processed"],
            "total_neologisms_detected": self.stats["total_neologisms_detected"],
            "total_choices_applied": self.stats["total_choices_applied"],
            "total_processing_time": self.stats["total_processing_time"],
        }

        # Calculate derived statistics
        if self.stats["documents_processed"] > 0:
            base_stats["average_processing_time"] = (
                self.stats["total_processing_time"] / self.stats["documents_processed"]
            )
            base_stats["average_neologisms_per_document"] = (
                self.stats["total_neologisms_detected"]
                / self.stats["documents_processed"]
            )

        if self.stats["total_neologisms_detected"] > 0:
            base_stats["choice_application_rate"] = (
                self.stats["total_choices_applied"]
                / self.stats["total_neologisms_detected"]
            )

        return {
            "philosophy_enhanced_processor_stats": base_stats,
            "base_processor_stats": "Available via base_processor.get_statistics()",
            "translation_service_stats": self.philosophy_translation_service.get_statistics(),
            "neologism_detector_stats": self.neologism_detector.get_statistics(),
            "user_choice_manager_stats": self.user_choice_manager.get_statistics(),
            "configuration": {
                "enable_batch_processing": self.enable_batch_processing,
                "max_concurrent_pages": self.max_concurrent_pages,
            },
        }

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        return await asyncio.to_thread(
            self.user_choice_manager.cleanup_expired_sessions
        )


# Convenience functions


def create_philosophy_enhanced_document_processor(
    dpi: int = 300,
    preserve_images: bool = True,
    terminology_path: Optional[str] = None,
    db_path: str = "database/user_choices.db",
    **kwargs,
) -> PhilosophyEnhancedDocumentProcessor:
    """Create a philosophy-enhanced document processor with default components."""
    return PhilosophyEnhancedDocumentProcessor(
        dpi=dpi,
        preserve_images=preserve_images,
        terminology_path=terminology_path,
        user_choice_manager=UserChoiceManager(db_path=db_path),
        **kwargs,
    )


async def process_document_with_philosophy_awareness(
    file_path: str,
    source_lang: str,
    target_lang: str,
    provider: str = "auto",
    user_id: Optional[str] = None,
    terminology_path: Optional[str] = None,
    output_filename: Optional[str] = None,
) -> tuple[PhilosophyDocumentResult, str]:
    """Process a document with philosophy awareness and create translated output."""
    processor = create_philosophy_enhanced_document_processor(
        terminology_path=terminology_path
    )

    # Process the document
    result = await processor.process_document_with_philosophy_awareness(
        file_path, source_lang, target_lang, provider, user_id
    )

    # Create translated document
    if not output_filename:
        output_filename = f"translated_{Path(file_path).stem}.pdf"

    output_path = await processor.create_translated_document_with_philosophy_awareness(
        result, output_filename
    )

    return result, output_path
