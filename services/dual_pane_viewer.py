"""Synchronized Side-by-Side Dual-Pane Reading Mode Controller (TASK-3.4).

Provides bilingual page-by-page alignment, serving the original German source
document alongside the translated English layout PDF. Supports text extraction,
optional base64 image rasterization with graceful fallback, and cross-pane term
searching with word-level bounding box coordinates for neologism highlighting (FR-15).

Traceability: FR-15, NFR-05, NFR-09
"""

from __future__ import annotations

import base64
import contextlib
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import pypdf

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextBoundingBox:
    """Bounding box coordinates for a highlighted term on a page."""

    text: str
    x: float
    y: float
    width: float
    height: float
    page_number: int


@dataclass(frozen=True)
class HighlightCoordinates:
    """Synchronized coordinate mapping for cross-pane neologism highlighting."""

    page_number: int
    german_term: str
    english_term: str
    german_matches: list[TextBoundingBox]
    english_matches: list[TextBoundingBox]


@dataclass(frozen=True)
class BilingualPagePair:
    """Synchronized bilingual page data for side-by-side display."""

    page_number: int
    total_pages_german: int
    total_pages_english: int
    german_text: str
    english_text: str
    german_page_image_base64: str | None = None
    english_page_image_base64: str | None = None
    has_images: bool = False


# ---------------------------------------------------------------------------
# DualPaneViewerController
# ---------------------------------------------------------------------------


class DualPaneViewerController:
    """Controller for bilingual side-by-side reading mode and term highlighting."""

    def __init__(self, default_dpi: int = 150) -> None:
        """Initialise viewer controller with default rasterization DPI."""
        self._default_dpi = default_dpi

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_bilingual_page_pair(
        self,
        german_source: Path | str | bytes | BinaryIO,
        english_source: Path | str | bytes | BinaryIO,
        page_number: int,  # 1-indexed
        render_images: bool = True,
        dpi: int | None = None,
    ) -> BilingualPagePair:
        """Retrieve synchronized page text and optional rendered images.

        Args:
            german_source: German original PDF (Path, bytes, or stream).
            english_source: English translated PDF (Path, bytes, or stream).
            page_number: 1-indexed page number to display.
            render_images: Whether to rasterize page images as base64 strings.
            dpi: Image rasterization resolution (default 150).

        Returns:
            BilingualPagePair containing text, total counts, and images.

        Raises:
            ValueError: If page_number is out of range or PDF parsing fails.
        """
        if page_number < 1:
            raise ValueError(
                f"Page number {page_number} is out of bounds (must be >= 1)"
            )

        from utils.pdf_stream import open_pdf_stream

        try:
            with (
                open_pdf_stream(german_source, "German") as (de_stream, _),
                open_pdf_stream(english_source, "English") as (en_stream, _),
            ):
                try:
                    reader_de = pypdf.PdfReader(de_stream)
                    total_de = len(reader_de.pages)
                except Exception as exc:
                    raise ValueError(f"Failed to parse German PDF: {exc}") from exc

                try:
                    reader_en = pypdf.PdfReader(en_stream)
                    total_en = len(reader_en.pages)
                except Exception as exc:
                    raise ValueError(f"Failed to parse English PDF: {exc}") from exc

                if page_number > total_de:
                    raise ValueError(
                        f"Page number {page_number} exceeds total pages in German PDF ({total_de})"
                    )
                if page_number > total_en:
                    raise ValueError(
                        f"Page number {page_number} exceeds total pages in English PDF ({total_en})"
                    )

                page_idx = page_number - 1
                german_text = reader_de.pages[page_idx].extract_text() or ""
                english_text = reader_en.pages[page_idx].extract_text() or ""

                de_img_b64: str | None = None
                en_img_b64: str | None = None
                has_images = False

                if render_images:
                    resolution = dpi or self._default_dpi
                    de_img_b64 = self._render_page_image(
                        de_stream, page_number, resolution
                    )
                    en_img_b64 = self._render_page_image(
                        en_stream, page_number, resolution
                    )
                    has_images = de_img_b64 is not None and en_img_b64 is not None

                return BilingualPagePair(
                    page_number=page_number,
                    total_pages_german=total_de,
                    total_pages_english=total_en,
                    german_text=german_text.strip(),
                    english_text=english_text.strip(),
                    german_page_image_base64=de_img_b64,
                    english_page_image_base64=en_img_b64,
                    has_images=has_images,
                )
        except FileNotFoundError as exc:
            raise ValueError(str(exc)) from exc

    def search_term_across_panes(
        self,
        german_source: Path | str | bytes | BinaryIO,
        english_source: Path | str | bytes | BinaryIO,
        german_term: str,
        english_term: str,
        page_number: int,  # 1-indexed
        case_sensitive: bool = False,
    ) -> HighlightCoordinates:
        """Search and extract neologism bounding boxes on a synchronized page.

        Args:
            german_source: German PDF document.
            english_source: English PDF document.
            german_term: German neologism or phrase to locate.
            english_term: Corresponding English translation to locate.
            page_number: 1-indexed page number to search.
            case_sensitive: Whether match should be case-sensitive.

        Returns:
            HighlightCoordinates with match bounding boxes for both panes.
        """
        de_matches = self._find_term_boxes_on_page(
            source=german_source,
            term=german_term,
            page_number=page_number,
            case_sensitive=case_sensitive,
            doc_label="German",
        )
        en_matches = self._find_term_boxes_on_page(
            source=english_source,
            term=english_term,
            page_number=page_number,
            case_sensitive=case_sensitive,
            doc_label="English",
        )

        return HighlightCoordinates(
            page_number=page_number,
            german_term=german_term,
            english_term=english_term,
            german_matches=de_matches,
            english_matches=en_matches,
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _find_term_boxes_on_page(
        self,
        source: Path | str | bytes | BinaryIO,
        term: str,
        page_number: int,
        case_sensitive: bool,
        doc_label: str,
    ) -> list[TextBoundingBox]:
        """Scan a specific page in a PDF and compute bounding boxes for matches."""
        matches: list[TextBoundingBox] = []
        if not term.strip():
            return matches

        from utils.pdf_stream import open_pdf_stream

        try:
            with open_pdf_stream(source, doc_label) as (stream, _):
                reader = pypdf.PdfReader(stream)
                total_pages = len(reader.pages)
                if not (1 <= page_number <= total_pages):
                    return matches

                page = reader.pages[page_number - 1]
                page_height = float(page.mediabox.height)

                extracted_fragments: list[dict[str, Any]] = []

                def visitor_body(
                    text: str, _cm: Any, tm: Any, _font_dict: Any, font_size: float
                ) -> None:
                    if text and text.strip():
                        x = float(tm[4]) if tm is not None and len(tm) > 4 else 50.0
                        y = float(tm[5]) if tm is not None and len(tm) > 5 else 700.0
                        extracted_fragments.append(
                            {
                                "text": text,
                                "x": x,
                                "y": y,
                                "font_size": float(font_size) if font_size else 12.0,
                            }
                        )

                with contextlib.suppress(Exception):
                    page.extract_text(visitor_text=visitor_body)

                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(re.escape(term), flags)

                # Check fragments first
                for frag in extracted_fragments:
                    if pattern.search(frag["text"]):
                        char_width = frag["font_size"] * 0.5
                        width = len(term) * char_width
                        matches.append(
                            TextBoundingBox(
                                text=term,
                                x=frag["x"],
                                y=frag["y"],
                                width=width,
                                height=frag["font_size"] * 1.2,
                                page_number=page_number,
                            )
                        )

                # If fragment visitor yielded no matches, search whole page text as fallback
                if not matches:
                    full_text = page.extract_text() or ""
                    for _match in pattern.finditer(full_text):
                        # Default estimated coordinate centered on page
                        matches.append(
                            TextBoundingBox(
                                text=term,
                                x=50.0,
                                y=page_height * 0.5,
                                width=100.0,
                                height=14.0,
                                page_number=page_number,
                            )
                        )

                return matches

        except Exception as exc:
            logger.warning(
                "Error searching term on %s page %d: %s", doc_label, page_number, exc
            )
            return matches

    def _render_page_image(
        self,
        source: Path | str | bytes | BinaryIO,
        page_number: int,
        dpi: int,
    ) -> str | None:
        """Rasterize a single page to base64 PNG, degrading gracefully if poppler missing."""
        try:
            import pdf2image

            from utils.pdf_stream import open_pdf_stream

            with open_pdf_stream(source, "Raster") as (stream, _):
                if hasattr(stream, "seek"):
                    with contextlib.suppress(Exception):
                        stream.seek(0)
                data_bytes = stream.read() if hasattr(stream, "read") else b""
                if not data_bytes and hasattr(stream, "getvalue"):
                    data_bytes = stream.getvalue()  # type: ignore
                if hasattr(stream, "seek"):
                    with contextlib.suppress(Exception):
                        stream.seek(0)

            images = pdf2image.convert_from_bytes(
                data_bytes,
                first_page=page_number,
                last_page=page_number,
                dpi=dpi,
                fmt="png",
            )
            if not images:
                return None

            img_byte_arr = io.BytesIO()
            images[0].save(img_byte_arr, format="PNG")
            img_byte_arr.seek(0)
            b64_str = base64.b64encode(img_byte_arr.read()).decode("utf-8")
            return f"data:image/png;base64,{b64_str}"

        except Exception as exc:
            logger.debug(
                "Image rendering for page %d skipped (poppler or renderer unavailable): %s",
                page_number,
                exc,
            )
            return None

    @staticmethod
    def _open_source(
        source: Path | str | bytes | BinaryIO,
        label: str = "PDF",
    ) -> tuple[BinaryIO, bool]:
        """Normalize input into an open binary stream with closure flag.

        Deprecated backward-compatibility shim. Callers should migrate to
        :func:`utils.pdf_stream.open_pdf_stream` context manager.
        """
        if isinstance(source, (str, Path)):
            p = Path(source)
            if not p.exists():
                raise ValueError(f"{label} file not found: {source}")
            return open(p, "rb"), True
        elif isinstance(source, bytes):
            return io.BytesIO(source), True
        elif hasattr(source, "read") and hasattr(source, "seek"):
            with contextlib.suppress(Exception):
                source.seek(0)
            return source, False
        else:
            raise TypeError(f"Unsupported source type: {type(source)}")
