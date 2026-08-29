"""Enhanced PDF document processor (PDF-only)."""

from __future__ import annotations

import logging
import os
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

warnings.warn(
    "services.enhanced_document_processor is deprecated and retired under ADR 0001 / Track 4. "
    "Use services.gcp_batch_translation_service.GCPBatchTranslationService instead.",
    DeprecationWarning,
    stacklevel=2,
)

# PDFToImageConverter, DolphinOCRService, and PDFDocumentReconstructor removed under ADR 0001
# Layout preservation is handled natively by Google Cloud Document Translation.

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


def _get_pdf_page_count(pdf_path: str) -> int | None:
    """Return the number of pages in *pdf_path* using pypdf.

    Returns ``None`` when the page count cannot be determined (e.g.
    pypdf is not installed, the file is missing, or the PDF is
    corrupted).  The caller should treat ``None`` as "unknown" and
    skip any page-count-based validation.
    """
    try:
        import pypdf  # type: ignore[import-untyped]

        reader = pypdf.PdfReader(pdf_path)
        return len(reader.pages)
    except Exception as exc:
        logger.warning("Could not determine PDF page count for %s: %s", pdf_path, exc)
        return None


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
        # PDFDocumentReconstructor retired and deleted under ADR 0001
        self.reconstructor = None

    async def extract_content(self, file_path: str) -> dict[str, Any]:
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
            return await self._extract_pdf_content(file_path)
        elif file_ext in {".docx", ".txt"}:
            raise ValueError("Only PDF files are supported in this project")
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")

    async def _extract_pdf_content(self, pdf_path: str) -> dict[str, Any]:
        """Extract content from PDF with advanced layout preservation."""
        start_time = time.time()

        # Call Dolphin OCR directly with the PDF path
        try:
            from services.dolphin_client import get_layout

            dolphin_layout = await get_layout(pdf_path)
        except (ImportError, Exception) as e:
            logger.error("OCR processing failed for %s: %s", pdf_path, e, exc_info=True)
            # Graceful degradation: continue with empty layout
            dolphin_layout = {"pages": []}

        # Validate dolphin_layout structure against the real PDF page count
        pdf_page_count = _get_pdf_page_count(pdf_path)
        if pdf_page_count is not None:
            if dolphin_layout and not validate_dolphin_layout(
                dolphin_layout,
                pdf_page_count,
            ):
                logger.warning("Invalid Dolphin layout structure, discarding")
                dolphin_layout = {"pages": []}  # Reset to empty rather than None
        else:
            logger.info(
                "Skipping Dolphin layout page-count validation "
                "(could not determine real PDF page count)"
            )

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

        # Validate dolphin_layout structure against the real PDF page count
        # so we catch actual OCR/layout mismatches instead of comparing the
        # layout against a value derived from itself (tautological check).
        pdf_page_count = _get_pdf_page_count(pdf_path)
        if pdf_page_count is not None:
            if dolphin_layout and not validate_dolphin_layout(
                dolphin_layout,
                pdf_page_count,
            ):
                logger.warning("Invalid Dolphin layout structure, discarding")
                dolphin_layout = None
        else:
            logger.info(
                "Skipping Dolphin layout page-count validation "
                "(could not determine real PDF page count)"
            )
        return {
            "type": "pdf_advanced",
            "layouts": [],
            "text_by_page": text_by_page,
            "metadata": metadata,
            "file_path": pdf_path,
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
        del translated_texts
        del output_filename
        content_type = original_content["type"]

        if content_type == "pdf_advanced":
            raise NotImplementedError(
                "Legacy PDF document reconstruction has been retired and deleted under "
                "ADR 0001 / Track 4. Use Google Cloud Document Translation."
            )
        elif content_type in {"docx", "txt"}:
            raise ValueError("Only PDF content is supported in this project")
        else:
            raise ValueError(f"Unsupported content type: {content_type}")

    async def reconstruct_document(
        self,
        original_content: dict[str, Any],
        translated_texts: dict[int, list[str]],
        output_path: str | None = None,
    ) -> str:
        """Reconstruct translated document (deprecated).

        Raises:
            NotImplementedError: Legacy ReportLab canvas reconstruction has been
                retired and deleted under ADR 0001 in favor of Google Cloud
                Document Translation.
        """
        raise NotImplementedError(
            "Legacy PDF document reconstruction has been retired and deleted under "
            "ADR 0001 / Track 4. Use Google Cloud Document Translation."
        )


