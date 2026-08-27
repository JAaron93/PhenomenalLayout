"""Historical German OCR & Fraktur / Blackletter Classifier (TASK-3.1).

Analyzes PDF font descriptors, historical Unicode ligature patterns (e.g. long-s 'ſ',
'tz', 'ch', 'ck'), and typography distributions to emit an OCR Script Confidence Rating
(0.0 to 1.0) and recommendations for batch translation vs. sample preview pages.

Traceability: FR-11, NFR-01, NFR-09
BDD Scenario: FR-11.1
"""

from __future__ import annotations

import contextlib
import io
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

import pypdf

from config.settings import gcp_settings

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class ScriptType(StrEnum):
    """Classification of typographic script family."""

    ANTIQUA = "Antiqua"
    FRAKTUR = "Fraktur"
    HYBRID = "Hybrid"


@dataclass(frozen=True)
class ScriptAnalysisResult:
    """Detailed script analysis report for a document."""

    script_type: ScriptType
    ocr_confidence_score: float
    ligature_counts: dict[str, int]
    font_descriptors: list[str]
    recommended_action: str
    total_pages_analyzed: int
    fraktur_ratio: float


@dataclass(frozen=True)
class OCRConfidence:
    """High-level confidence rating and sample preview recommendation."""

    confidence_score: float
    script_type: str
    recommended_action: str
    preview_recommended: bool


# ---------------------------------------------------------------------------
# Heuristic Patterns
# ---------------------------------------------------------------------------

_FRAKTUR_FONT_KEYWORDS: tuple[str, ...] = (
    "fraktur",
    "schwabacher",
    "gotisch",
    "gothic",
    "blackletter",
    "walbaum-fraktur",
    "fette",
    "textur",
    "gebrochene",
)

_LONG_S_PATTERN = re.compile(r"ſ")
_FRAKTUR_LIGATURE_PATTERNS: dict[str, re.Pattern[str]] = {
    "long_s": _LONG_S_PATTERN,
    "long_s_ch": re.compile(r"ſch"),
    "long_s_t": re.compile(r"ſt|ﬅ"),
    "tz": re.compile(r"tz"),
    "ck": re.compile(r"ck"),
    "ch": re.compile(r"ch"),
    "st_ligature": re.compile(r"ﬆ"),
}


# ---------------------------------------------------------------------------
# FrakturClassifier
# ---------------------------------------------------------------------------


class FrakturClassifier:
    """Evaluates PDF documents for historical Fraktur (Blackletter) typography."""

    def __init__(self, confidence_threshold: float | None = None) -> None:
        """Initialise classifier with optional threshold override.

        Args:
            confidence_threshold: Cutoff below which preview is recommended.
                Defaults to ``gcp_settings.fraktur_confidence_threshold`` (0.85).
        """
        self._confidence_threshold: float = (
            confidence_threshold
            if confidence_threshold is not None
            else gcp_settings.fraktur_confidence_threshold
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_script(
        self,
        source: Path | str | bytes | BinaryIO,
        max_pages: int | None = None,
    ) -> ScriptAnalysisResult:
        """Analyze PDF typography and classify script family and OCR confidence.

        Args:
            source: PDF file path, raw bytes, or binary stream.
            max_pages: Optional maximum page count to sample (default all).

        Returns:
            ScriptAnalysisResult detailing script type, confidence, and action.

        Raises:
            ValueError: If the PDF stream cannot be parsed.
        """
        stream, should_close = self._open_source(source)
        try:
            reader = pypdf.PdfReader(stream)
            total_pages = len(reader.pages)
            if total_pages == 0:
                raise ValueError("Failed to parse PDF: empty document with 0 pages")

            pages_to_scan = (
                total_pages
                if max_pages is None
                else min(total_pages, max(1, max_pages))
            )

            total_chars = 0
            total_s_count = 0
            ligature_counts: dict[str, int] = dict.fromkeys(
                _FRAKTUR_LIGATURE_PATTERNS, 0
            )
            font_descriptors: set[str] = set()

            fraktur_pages_count = 0
            antiqua_pages_count = 0

            for page_idx in range(pages_to_scan):
                page = reader.pages[page_idx]

                # Extract fonts
                page_fonts: set[str] = set()
                self._extract_page_fonts(page, page_fonts)
                font_descriptors.update(page_fonts)

                page_has_fraktur_font = any(
                    any(kw in font.lower() for kw in _FRAKTUR_FONT_KEYWORDS)
                    for font in page_fonts
                )

                # Extract and analyze text
                text = page.extract_text() or ""
                page_chars = len(text)
                total_chars += page_chars
                s_count = text.lower().count("s") + text.count("ſ")
                total_s_count += s_count

                page_ligatures: dict[str, int] = {}
                for name, pattern in _FRAKTUR_LIGATURE_PATTERNS.items():
                    cnt = len(pattern.findall(text))
                    ligature_counts[name] += cnt
                    page_ligatures[name] = cnt

                page_long_s = page_ligatures.get("long_s", 0)
                page_long_s_ratio = page_long_s / s_count if s_count > 0 else 0.0

                if (
                    page_has_fraktur_font
                    or page_long_s_ratio >= 0.15
                    or page_long_s >= 2
                ):
                    fraktur_pages_count += 1
                elif page_chars > 0:
                    antiqua_pages_count += 1

            long_s_count = ligature_counts.get("long_s", 0)
            fraktur_font_detected = any(
                any(kw in font.lower() for kw in _FRAKTUR_FONT_KEYWORDS)
                for font in font_descriptors
            )

            # Fraktur ratio based on historical ligature prevalence and long-s proportion
            long_s_ratio = long_s_count / total_s_count if total_s_count > 0 else 0.0

            fraktur_features_count = (
                long_s_count
                + ligature_counts.get("long_s_ch", 0)
                + ligature_counts.get("long_s_t", 0)
            )

            if total_chars > 0:
                char_feature_ratio = (fraktur_features_count * 10) / total_chars
            else:
                char_feature_ratio = 0.0

            combined_fraktur_ratio = max(long_s_ratio, min(1.0, char_feature_ratio))
            if fraktur_font_detected:
                combined_fraktur_ratio = max(combined_fraktur_ratio, 0.40)

            # Script family classification
            if fraktur_pages_count > 0 and antiqua_pages_count > 0:
                script_type = ScriptType.HYBRID
                ocr_confidence_score = round(
                    max(0.75, min(0.89, 0.85 - combined_fraktur_ratio * 0.1)), 2
                )
                recommended_action = "Preview 2 sample pages before full batch"
            elif (
                fraktur_pages_count > 0
                or combined_fraktur_ratio >= 0.25
                or fraktur_font_detected
            ):
                script_type = ScriptType.FRAKTUR
                # BDD FR-11.1 calibration: Historical Fraktur scan confidence ~0.88
                ocr_confidence_score = round(
                    max(0.70, min(0.92, 0.88 - (combined_fraktur_ratio - 0.3) * 0.1)), 2
                )
                recommended_action = "Preview 2 sample pages before full batch"
            else:
                script_type = ScriptType.ANTIQUA
                ocr_confidence_score = 0.98 if total_chars > 0 else 0.95
                recommended_action = "Direct batch translation"

            return ScriptAnalysisResult(
                script_type=script_type,
                ocr_confidence_score=ocr_confidence_score,
                ligature_counts=ligature_counts,
                font_descriptors=sorted(font_descriptors),
                recommended_action=recommended_action,
                total_pages_analyzed=pages_to_scan,
                fraktur_ratio=round(combined_fraktur_ratio, 4),
            )

        except Exception as exc:
            if isinstance(exc, ValueError) and "Failed to parse PDF" in str(exc):
                raise
            raise ValueError(f"Failed to parse PDF: {exc}") from exc
        finally:
            if should_close:
                with contextlib.suppress(Exception):
                    stream.close()

    def get_ocr_confidence_rating(
        self,
        source: Path | str | bytes | BinaryIO,
    ) -> OCRConfidence:
        """Convenience method returning high-level OCRConfidence structure.

        Args:
            source: PDF input source.

        Returns:
            OCRConfidence object.
        """
        analysis = self.classify_script(source)
        preview_recommended = (
            analysis.ocr_confidence_score < self._confidence_threshold
            or analysis.script_type in (ScriptType.FRAKTUR, ScriptType.HYBRID)
        )
        return OCRConfidence(
            confidence_score=analysis.ocr_confidence_score,
            script_type=analysis.script_type.value,
            recommended_action=analysis.recommended_action,
            preview_recommended=preview_recommended,
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _open_source(
        source: Path | str | bytes | BinaryIO,
    ) -> tuple[BinaryIO, bool]:
        """Normalize input into an open binary stream with closure flag."""
        if isinstance(source, (str, Path)):
            p = Path(source)
            if not p.exists():
                raise ValueError(f"File not found: {source}")
            return open(p, "rb"), True
        elif isinstance(source, bytes):
            return io.BytesIO(source), True
        elif hasattr(source, "read") and hasattr(source, "seek"):
            return source, False
        else:
            raise TypeError(f"Unsupported source type: {type(source)}")

    @staticmethod
    def _extract_page_fonts(page: pypdf.PageObject, font_descriptors: set[str]) -> None:
        """Extract font base names from page resources if present."""
        with contextlib.suppress(Exception):
            resources = page.get("/Resources")
            if not resources or not hasattr(resources, "get"):
                return
            fonts = resources.get("/Font")
            if not fonts or not hasattr(fonts, "keys"):
                return
            for font_key in fonts:
                font_obj = fonts[font_key]
                if hasattr(font_obj, "get"):
                    base_font = font_obj.get("/BaseFont")
                    if base_font:
                        # Clean /FontName
                        name = str(base_font).lstrip("/")
                        font_descriptors.add(name)
