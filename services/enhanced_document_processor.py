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

# Layout preservation is handled natively by Google Cloud Document Translation.

logger = logging.getLogger(__name__)


def validate_pdf_layout(layout: dict[str, Any], expected_page_count: int) -> bool:
    """Validate the structure of PDF layout data.

    Args:
        layout: The layout data to validate
        expected_page_count: Expected number of pages in the layout

    Returns:
        bool: True if layout is valid, False otherwise
    """
    if not isinstance(layout, dict):
        logger.warning("PDF layout must be a dictionary")
        return False

    if "pages" not in layout:
        logger.warning("PDF layout missing 'pages' key")
        return False

    if not isinstance(layout["pages"], list):
        logger.warning("PDF layout 'pages' must be a list")
        return False

    if len(layout["pages"]) != expected_page_count:
        logger.warning(
            "PDF layout page count mismatch. Expected %s, got %s",
            expected_page_count,
            len(layout["pages"]),
        )
        return False

    # Validate each page structure
    for i, page in enumerate(layout["pages"]):
        if not isinstance(page, dict):
            logger.warning("Page %s is not a dictionary", i)
            return False

        # Add more specific validations here based on the expected schema

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

    PDF-only; layout preservation is handled by Google Cloud Document
    Translation (ADR 0001).
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
        """Extract content from PDF with layout metadata."""
        start_time = time.time()

        # OCR layout extraction is retired under ADR 0001; layout preservation
        # is handled natively by Google Cloud Document Translation.
        layout: dict[str, Any] = {"pages": []}

        # Validate the placeholder structure against the real PDF page count so
        # consumers never see a layout claiming pages the PDF does not have.
        pdf_page_count = _get_pdf_page_count(pdf_path)
        if pdf_page_count is not None:
            if not validate_pdf_layout(layout, pdf_page_count):
                logger.warning("Invalid PDF layout structure, discarding")
                layout = None
        else:
            logger.info(
                "Skipping PDF layout page-count validation "
                "(could not determine real PDF page count)"
            )

        text_by_page: dict[int, list[str]] = {}
        for i, page in enumerate(layout["pages"] if layout else []):
            blocks = page.get("text_blocks", [])
            text_by_page[i] = [
                b.get("text", "") for b in blocks if isinstance(b, dict)
            ]

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

        return {
            "type": "pdf_advanced",
            "layouts": [],
            "text_by_page": text_by_page,
            "metadata": metadata,
            "file_path": pdf_path,
            "backup_path": "",
            "preview": "",
            "layout": layout,
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


