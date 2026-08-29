"""Main document processing orchestrator.

Coordinates OCR, layout-aware translation, and reconstruction steps
into a single `DocumentProcessor` pipeline.
"""

from __future__ import annotations

import logging
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dolphin_ocr.layout import BoundingBox, FontInfo
from dolphin_ocr.monitoring import MonitoringService
from services.layout_aware_translation_service import (
    LayoutAwareTranslationService,
    TextBlock,
)
from services.ocr_utils import parse_ocr_result

warnings.warn(
    "services.main_document_processor is deprecated and retired under ADR 0001. "
    "Use services.gcp_batch_translation_service.GCPBatchTranslationService instead.",
    DeprecationWarning,
    stacklevel=2,
)


def get_layout_sync(*args: Any, **kwargs: Any) -> Any:
    """Stub for retired DolphinClient.get_layout_sync."""
    raise NotImplementedError("DolphinClient has been deleted under ADR 0001.")


@dataclass
class TranslatedElement:
    """Stub for retired TranslatedElement."""

    original_text: str = ""
    translated_text: str = ""
    adjusted_text: str | None = None
    bbox: Any = None
    font_info: Any = None


@dataclass
class TranslatedPage:
    """Stub for retired TranslatedPage."""

    page_number: int = 0
    translated_elements: list[Any] = field(default_factory=list)


@dataclass
class TranslatedLayout:
    """Stub for retired TranslatedLayout."""

    pages: list[Any] = field(default_factory=list)


class PDFDocumentReconstructor:
    """Stub for retired PDFDocumentReconstructor."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize reconstructor stub."""
        pass

    def reconstruct_pdf_document(self, *args: Any, **kwargs: Any) -> Any:
        """Reconstruct PDF document stub."""
        raise NotImplementedError("PDFDocumentReconstructor has been deleted under ADR 0001.")

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
    convert_ms: float  # Deprecated: remains at 0.0 for backward compatibility
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
        translation_service: LayoutAwareTranslationService,
        reconstructor: PDFDocumentReconstructor,
        monitoring: MonitoringService | None = None,
        max_batch_size: int = 100,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the processor with collaborating services."""
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

        # OCR processing (direct PDF submission)
        start_ocr = time.perf_counter()
        try:
            ocr_result = get_layout_sync(request.file_path)
        except Exception as e:
            ocr_ms = (time.perf_counter() - start_ocr) * 1000.0
            _emit("ocr", pages=0)
            if self._monitor is not None:
                self._monitor.record_operation("ocr", ocr_ms, success=False)
            self._logger.error("OCR processing failed for %s: %s", request.file_path, e)
            raise

        ocr_ms = (time.perf_counter() - start_ocr) * 1000.0
        _emit("ocr", pages=len(ocr_result.get("pages", [])))
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
            convert_ms=0.0,
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
    # Moved: _parse_ocr_result relocated to services.ocr_utils.parse_ocr_result


def _default_output_path(input_path: str) -> str:
    p = Path(input_path)
    return str(p.with_name(f"{p.stem}.translated.pdf"))
