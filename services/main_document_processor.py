from __future__ import annotations

"""Main document processing orchestrator.

Coordinates the PDF conversion, OCR, layout-aware translation, and
reconstruction steps into a single `DocumentProcessor` pipeline.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dolphin_ocr.layout import BoundingBox, FontInfo
from dolphin_ocr.monitoring import MonitoringService
from dolphin_ocr.pdf_to_image import PDFToImageConverter
from services.dolphin_ocr_service import DolphinOCRService
from services.ocr_utils import parse_ocr_result
from services.layout_aware_translation_service import (
    LayoutAwareTranslationService,
    LayoutContext,
    TextBlock,
)
from services.pdf_document_reconstructor import (
    PDFDocumentReconstructor,
    TranslatedElement,
    TranslatedLayout,
    TranslatedPage,
)

# ----------------------------- Request/Result -----------------------------


@dataclass(frozen=True)
class ProcessingOptions:
    """Options for controlling pipeline behavior."""

    dpi: int = 300
    output_path: str | None = None


@dataclass(frozen=True)
class DocumentProcessingRequest:
    """Input describing the document and language pair."""

    file_path: str
    source_language: str
    target_language: str
    options: ProcessingOptions = field(default_factory=ProcessingOptions)


@dataclass(frozen=True)
class ProcessingStats:
    """Timing and counters for the run (milliseconds for timing)."""

    pages_processed: int
    convert_ms: float
    ocr_ms: float
    translation_ms: float
    reconstruction_ms: float


@dataclass(frozen=True)
class ProcessingResult:
    """Aggregate result of processing."""

    success: bool
    output_path: str | None
    warnings: list[str]
    processing_stats: ProcessingStats
    progress: list[str]


class DocumentProcessor:
    """Coordinate conversion, OCR, translation, and reconstruction."""

    def __init__(
        self,
        *,
        converter: PDFToImageConverter,
        ocr_service: DolphinOCRService,
        translation_service: LayoutAwareTranslationService,
        reconstructor: PDFDocumentReconstructor,
        monitoring: MonitoringService | None = None,
        max_batch_size: int = 100,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the processor with collaborating services."""
        self._converter = converter
        self._ocr = ocr_service
        self._translator = translation_service
        self._reconstructor = reconstructor
        self._monitor = monitoring
        self._max_batch_size = max(1, int(max_batch_size))
        self._logger = logger or logging.getLogger("services.document_processor")

    # ----------------------------- Public API -----------------------------
    def process_document(
        self,
        request: DocumentProcessingRequest,
        *,
        on_progress: Callable[[str, dict], None] | None = None,
    ) -> ProcessingResult:
        """Execute the complete workflow end-to-end.

        Progress events emitted (in order):
        - validated
        - converted
        - ocr
        - translated
        - reconstructed
        - completed
        """
        progress: list[str] = []

        def _emit(stage: str, **payload: object) -> None:
            progress.append(stage)
            if on_progress is not None:
                try:
                    on_progress(stage, payload)
                except Exception as e:  # pragma: no cover - best-effort
                    self._logger.debug(
                        "Progress callback error: %s: %s",
                        type(e).__name__,
                        e,
                        exc_info=True,
                    )

        # Validate request (extension/header + file exists)
        start_validate = time.perf_counter()
        self._reconstructor.validate_pdf_format_or_raise(request.file_path)
        _emit("validated", path=request.file_path)
        if self._monitor is not None:
            self._monitor.record_operation(
                "validate",
                (time.perf_counter() - start_validate) * 1000.0,
                success=True,
            )

        # Convert PDF to images
        start_convert = time.perf_counter()
        images = self._converter.convert_pdf_to_images(request.file_path)
        # Optional light optimization per image (safe, pure-python)
        optimized: list[bytes] = [
            self._converter.optimize_image_for_ocr(img) for img in images
        ]
        convert_ms = (time.perf_counter() - start_convert) * 1000.0
        _emit("converted", pages=len(optimized))
        if self._monitor is not None:
            self._monitor.record_operation("convert", convert_ms, success=True)

        # OCR processing (batch)
        start_ocr = time.perf_counter()
        ocr_result = self._ocr.process_document_images(optimized)
        ocr_ms = (time.perf_counter() - start_ocr) * 1000.0
        _emit("ocr", pages=len(optimized))
        if self._monitor is not None:
            self._monitor.record_operation("ocr", ocr_ms, success=True)

        # Build TextBlocks from OCR result
        blocks_per_page = parse_ocr_result(ocr_result)

        # Translation in fixed-size batches to avoid memory/API limits
        start_tx = time.perf_counter()
        all_blocks: list[TextBlock] = []
        for blocks in blocks_per_page:
            all_blocks.extend(blocks)

        translations = []
        bs = self._max_batch_size
        for i in range(0, len(all_blocks), bs):
            batch = all_blocks[i : i + bs]
            batch_tx = self._translator.translate_document_batch(
                text_blocks=batch,
                source_lang=request.source_language,
                target_lang=request.target_language,
            )
            translations.extend(batch_tx)

        translation_ms = (time.perf_counter() - start_tx) * 1000.0
        _emit("translated", count=len(translations))
        if self._monitor is not None:
            self._monitor.record_operation("translate", translation_ms, success=True)

        # Map translations back to pages and build TranslatedLayout
        pages: list[TranslatedPage] = []
        idx = 0
        for page_blocks in blocks_per_page:
            elems: list[TranslatedElement] = []
            for _ in page_blocks:
                t = translations[idx]
                elems.append(
                    TranslatedElement(
                        original_text=t.source_text,
                        translated_text=t.raw_translation,
                        adjusted_text=t.adjusted_text,
                        bbox=BoundingBox(
                            t.adjusted_bbox.x,
                            t.adjusted_bbox.y,
                            t.adjusted_bbox.width,
                            t.adjusted_bbox.height,
                        ),
                        font_info=FontInfo(
                            family=t.adjusted_font.family,
                            size=t.adjusted_font.size,
                            weight=t.adjusted_font.weight,
                            style=t.adjusted_font.style,
                            color=t.adjusted_font.color,
                        ),
                        layout_strategy=t.strategy.type.value,
                        confidence=t.translation_confidence,
                    )
                )
                idx += 1
            pages.append(
                TranslatedPage(
                    page_number=len(pages) + 1,
                    translated_elements=elems,
                )
            )

        tlayout = TranslatedLayout(pages=pages)

        # Reconstruct
        start_rc = time.perf_counter()
        output_path = request.options.output_path or _default_output_path(
            request.file_path
        )
        recon = self._reconstructor.reconstruct_pdf_document(
            translated_layout=tlayout,
            original_file_path=request.file_path,
            output_path=output_path,
        )
        reconstruction_ms = (time.perf_counter() - start_rc) * 1000.0
        _emit("reconstructed", output_path=recon.output_path)
        if self._monitor is not None:
            self._monitor.record_operation(
                "reconstruct", reconstruction_ms, success=True
            )

        warnings = list(recon.warnings)
        stats = ProcessingStats(
            pages_processed=len(pages),
            convert_ms=convert_ms,
            ocr_ms=ocr_ms,
            translation_ms=translation_ms,
            reconstruction_ms=reconstruction_ms,
        )
        _emit("completed")
        return ProcessingResult(
            success=recon.success,
            output_path=recon.output_path,
            warnings=warnings,
            processing_stats=stats,
            progress=progress,
        )

    # ---------------------------- Internal ----------------------------
    # Deprecated: _parse_ocr_result has been moved to services.ocr_utils.parse_ocr_result


def _default_output_path(input_path: str) -> str:
    p = Path(input_path)
    return str(p.with_name(f"{p.stem}.translated.pdf"))
