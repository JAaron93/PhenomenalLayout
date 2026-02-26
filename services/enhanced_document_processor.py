"""Enhanced PDF document processor (PDF-only)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dolphin_ocr.layout import BoundingBox, FontInfo
from dolphin_ocr.pdf_to_image import PDFToImageConverter
from services.dolphin_ocr_service import DolphinOCRService

# Migrated off legacy PDF engine; uses pdf2image + Dolphin OCR (PDF-only)
from .pdf_document_reconstructor import PDFDocumentReconstructor

logger = logging.getLogger(__name__)


def validate_dolphin_layout(layout: dict[str, Any], expected_page_count: int) -> bool:
    """Validate the structure of the Dolphin layout data.

    Args:
        layout: The Dolphin layout data to validate
        expected_page_count: Expected number of pages in the layout

    Returns:
        bool: True if layout is valid, False otherwise
    """
    if not isinstance(layout, dict):
        logger.warning("Dolphin layout must be a dictionary")
        return False

    if "pages" not in layout:
        logger.warning("Dolphin layout missing 'pages' key")
        return False

    if not isinstance(layout["pages"], list):
        logger.warning("Dolphin layout 'pages' must be a list")
        return False

    if len(layout["pages"]) != expected_page_count:
        logger.warning(
            "Dolphin layout page count mismatch. Expected %s, got %s",
            expected_page_count,
            len(layout["pages"]),
        )
        return False

    # Validate each page structure
    for i, page in enumerate(layout["pages"]):
        if not isinstance(page, dict):
            logger.warning("Page %s is not a dictionary", i)
            return False

        # Add more specific validations here based on Dolphin's schema
        # For example, check for required fields in each page

    return True


@dataclass
class DocumentMetadata:
    """Metadata for processed documents."""

    filename: str
    file_type: str
    total_pages: int
    total_text_elements: int
    file_size_mb: float
    processing_time: float
    dpi: int = 300


class EnhancedDocumentProcessor:
    """Enhanced document processor with comprehensive formatting preservation.

    PDF-only with advanced layout preservation using Dolphin OCR.
    """

    def __init__(self, dpi: int = 300, preserve_images: bool = True) -> None:
        """Initialize the enhanced document processor.

        Args:
            dpi: Resolution for PDF processing
            preserve_images: Whether to preserve images in PDFs
        """
        self.dpi = dpi
        self.preserve_images = preserve_images
        self.pdf_converter = PDFToImageConverter(dpi=dpi)
        self.ocr = DolphinOCRService()
        self.reconstructor = PDFDocumentReconstructor()

    def _generate_text_preview(self, text: str, max_chars: int = 1000) -> str:
        """Generate a text preview with ellipsis if needed.

        Args:
            text: The text to generate a preview for
            max_chars: Maximum number of characters in the preview
                (default: 1000)

        Returns:
            str: The text preview, truncated with ellipsis if longer than
            max_chars
        """
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    def extract_content(self, file_path: str) -> dict[str, Any]:
        """Extract content from document with format-specific processing.

        Args:
            file_path: Path to the document file

        Returns:
            Dictionary containing extracted content and metadata
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document not found: {file_path}")

        file_ext = Path(file_path).suffix.lower()
        logger.info(
            "Processing document: %s (%s)",
            file_path,
            file_ext,
        )

        if file_ext == ".pdf":
            return self._extract_pdf_content(file_path)
        elif file_ext in {".docx", ".txt"}:
            raise ValueError("Only PDF files are supported in this project")
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")

    def _extract_pdf_content(self, pdf_path: str) -> dict[str, Any]:
        """Extract content from PDF with advanced layout preservation."""
        import time

        start_time = time.time()

        # Convert PDF to images and call Dolphin OCR
        images = self.pdf_converter.convert_pdf_to_images(pdf_path)
        try:
            dolphin_layout = self.ocr.process_document_images(images)
        except (
            OSError,
            RuntimeError,
            ValueError,
        ) as e:  # Keep extraction resilient to OCR failures
            logger.error("OCR processing failed for %s: %s", pdf_path, e, exc_info=True)
            # Graceful degradation: continue with empty layout
            dolphin_layout = {"pages": []}

        # Validate Dolphin layout structure (best-effort)
        if not isinstance(dolphin_layout, dict):
            dolphin_layout = {"pages": []}
        # Build minimal text_by_page from Dolphin OCR
        text_by_page: dict[int, list[str]] = {}
        for i, page in enumerate(dolphin_layout.get("pages", [])):
            blocks = page.get("text_blocks", [])
            texts = [b.get("text", "") for b in blocks if isinstance(b, dict)]
            text_by_page[i] = texts

        # Calculate metadata
        total_text_elements = sum(len(v) for v in text_by_page.values())
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        processing_time = time.time() - start_time

        metadata = DocumentMetadata(
            filename=Path(pdf_path).name,
            file_type="PDF",
            total_pages=len(text_by_page),
            total_text_elements=total_text_elements,
            file_size_mb=file_size_mb,
            processing_time=processing_time,
            dpi=self.dpi,
        )

        # Validate dolphin_layout structure if present
        if dolphin_layout and not validate_dolphin_layout(
            dolphin_layout,
            len(text_by_page),
        ):
            logger.warning("Invalid Dolphin layout structure, discarding")
            dolphin_layout = None
        return {
            "type": "pdf_advanced",
            "layouts": [],
            "text_by_page": text_by_page,
            "metadata": metadata,
            "backup_path": "",
            "preview": "",
            "dolphin_layout": dolphin_layout,
        }

    # TXT helpers removed (PDF-only)

    def create_translated_document(
        self,
        original_content: dict[str, Any],
        translated_texts: dict[int, list[str]],
        output_filename: str,
    ) -> str:
        """Create translated document preserving original formatting."""
        output_path = os.path.join("downloads", output_filename)
        os.makedirs("downloads", exist_ok=True)

        content_type = original_content["type"]

        if content_type == "pdf_advanced":
            return self._create_translated_pdf(
                original_content, translated_texts, output_path
            )
        elif content_type in {"docx", "txt"}:
            raise ValueError("Only PDF content is supported in this project")
        else:
            raise ValueError(f"Unsupported content type: {content_type}")

    def _create_translated_pdf(
        self,
        original_content: dict[str, Any],
        translated_texts: dict[int, list[str]],
        output_path: str,
    ) -> str:
        """Create translated PDF with preserved formatting.

        Uses ``PDFDocumentReconstructor.reconstruct_pdf_document``.
        Raises NotImplementedError if reconstruction backend is
        unavailable in the environment.
        """
        # Build TranslatedLayout from the content we have
        try:
            from services.pdf_document_reconstructor import (
                DocumentReconstructionError,
                TranslatedElement,
                TranslatedLayout,
                TranslatedPage,
            )
        except ImportError as e:  # pragma: no cover
            raise NotImplementedError(
                "PDF reconstruction is not available: missing dependencies"
            ) from e

        # Translate the minimal dolphin-derived structure into
        # TranslatedLayout for the reconstructor.

        pages: list[TranslatedPage] = []
        dolphin_layout = original_content.get("dolphin_layout")
        for page_index, texts in sorted(
            original_content.get("text_by_page", {}).items()
        ):
            elements: list[TranslatedElement] = []
            for i, original in enumerate(texts):
                translated = translated_texts.get(page_index, [])
                translated_text = translated[i] if i < len(translated) else original

                # Defaults
                bbox = BoundingBox(x=0.0, y=0.0, width=612.0, height=12.0)
                font_info = FontInfo(family="Helvetica", size=12.0)

                # Try to use dolphin_layout data if available
                try:
                    if isinstance(dolphin_layout, dict) and page_index < len(
                        dolphin_layout.get("pages", [])
                    ):
                        page_data = dolphin_layout["pages"][page_index]
                        blocks = page_data.get("text_blocks", [])
                        if i < len(blocks):
                            block = blocks[i]
                            if isinstance(block, dict):
                                bbox_data = block.get("bbox")
                                if (
                                    isinstance(bbox_data, (list, tuple))
                                    and len(bbox_data) >= 4
                                ):
                                    bbox = BoundingBox(
                                        x=float(bbox_data[0]),
                                        y=float(bbox_data[1]),
                                        width=float(bbox_data[2]) - float(bbox_data[0]),
                                        height=float(bbox_data[3])
                                        - float(bbox_data[1]),
                                    )
                                font_data = block.get("font_info", {})
                                if isinstance(font_data, dict):
                                    font_info = FontInfo(
                                        name=str(font_data.get("family", "Helvetica")),
                                        size=float(font_data.get("size", 12.0)),
                                    )
                except Exception:
                    # Best-effort only; fall back to defaults silently
                    pass

                elements.append(
                    TranslatedElement(
                        original_text=original,
                        translated_text=translated_text,
                        adjusted_text=None,
                        bbox=bbox,
                        font_info=font_info,
                    )
                )
            pages.append(
                TranslatedPage(page_number=page_index, translated_elements=elements)
            )

        layout = TranslatedLayout(pages=pages)

        reconstructor = self.reconstructor
        try:
            result = reconstructor.reconstruct_pdf_document(
                translated_layout=layout,
                original_file_path=original_content.get("metadata").filename
                if original_content.get("metadata")
                else original_content.get("file_path", ""),
                output_path=output_path,
            )
        except (DocumentReconstructionError, OSError, ValueError) as e:
            raise NotImplementedError(
                f"PDF reconstruction failed or is unavailable: {e}"
            ) from e

        if not result.success:
            raise NotImplementedError(
                f"PDF reconstruction did not complete successfully. Warnings: {getattr(result, 'warnings', [])}"
            )

        return result.output_path

    # TXT output helpers removed (PDF-only)

    def convert_format(self, input_path: str, target_format: str) -> str:
        """Convert document format (PDF-only).

        - If ``target_format`` is not PDF, raise ``ValueError``.
        - If input is already a PDF and target is PDF, return the original path.
        - Non-PDF inputs are rejected.
        """
        input_ext = Path(input_path).suffix.lower()
        target_ext = f".{target_format.lower()}"

        if target_ext != ".pdf":
            raise ValueError("Only PDF output is supported in this project")

        if input_ext == ".pdf":
            return input_path

        raise ValueError("Only PDF inputs are supported in this project")

    # PDF->TXT conversion removed (PDF-only)

    # DOCX/TXT conversion helpers removed (PDF-only)

    def generate_preview(self, file_path: str, max_chars: int = 1000) -> str | None:
        """Generate a preview of the document content.

        Returns a short preview string when possible, None for expected
        recoverable errors (e.g., missing file), and lets unexpected
        exceptions bubble up after logging.
        """
        try:
            content = self.extract_content(file_path)

            if content.get("type") == "pdf_advanced":
                preview = content.get("preview")
                if preview:
                    return preview
                # Fall through to try other content fields

            preview_text = content.get(
                "preview",
                content.get("text_content", ""),
            )
            if isinstance(preview_text, str) and len(preview_text) > max_chars:
                return preview_text[:max_chars] + "..."
            return preview_text

        except FileNotFoundError as err:
            logger.error("Preview failed - file not found: %s", err)
            return None
        except ValueError as err:
            # Content extraction/validation errors
            logger.error("Preview failed - invalid input: %s", err)
            return None
        except (OSError, RuntimeError) as err:
            # I/O or library-level issues (e.g., parser problems)
            logger.error("Preview failed due to I/O or parser error: %s", err)
            return None
        except Exception:
            # Log unexpected exceptions with traceback and re-raise
            logger.exception("Unexpected error while generating preview")
            raise
