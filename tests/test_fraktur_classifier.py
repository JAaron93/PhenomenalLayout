"""Unit tests for FrakturClassifier (TASK-3.1).

Traceability: FR-11, NFR-01, NFR-09
- Historical German OCR & Fraktur / Blackletter classification
- OCR Script Confidence Rating (0.0 to 1.0)
- BDD Scenario FR-11.1 adherence (score ~0.88, preview recommendation)
- Deterministic file descriptor cleanup and streaming support
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.fraktur_classifier import (
    FrakturClassifier,
    OCRConfidence,
    ScriptAnalysisResult,
    ScriptType,
)


def _create_minimal_pdf(pages_count: int = 1) -> bytes:
    """Generate minimal valid PDF bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for _ in range(pages_count):
        c.setFont("Helvetica", 12)
        c.drawString(100, 700, "placeholder")
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def classifier() -> FrakturClassifier:
    return FrakturClassifier()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    return _create_minimal_pdf(pages_count=2)


class TestFrakturClassifierScriptAnalysis:
    """Tests for classify_script across different typographic styles."""

    def test_classify_antiqua_document(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes
    ) -> None:
        modern_text = (
            "Dies ist ein modernes philosophisches Werk über Erkenntnistheorie. "
            "The cognitive architecture discusses concepts of perception and reality. "
            "Standard typography without historical ligatures or long-s characters."
        )
        with patch("pypdf.PageObject.extract_text", return_value=modern_text):
            result = classifier.classify_script(sample_pdf_bytes)

        assert isinstance(result, ScriptAnalysisResult)
        assert result.script_type == ScriptType.ANTIQUA
        assert result.ocr_confidence_score >= 0.95
        assert result.fraktur_ratio < 0.05
        assert "Direct batch translation" in result.recommended_action
        assert result.total_pages_analyzed == 2

    def test_classify_fraktur_document_bdd_fr_11_1(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes
    ) -> None:
        """Adheres to BDD Scenario FR-11.1: 1929 edition with long-s (ſ) ligatures."""
        fraktur_text = (
            "Die Weſenslehre des Geiſtes von Ludwig Klages (1929). "
            "Erſte Abtheilung: Das Bewußtſein und die Schauung der Wirklichkeit. "
            "Hier ſteht der Text mit mancherley Schriften und Zeichen: ſch, tz, ck, ſt, ft. "
            "Die Seele iſt das Weſen des Lebens, der Geiſt aber der Widerſacher."
        )
        with patch("pypdf.PageObject.extract_text", return_value=fraktur_text):
            result = classifier.classify_script(sample_pdf_bytes)

        assert isinstance(result, ScriptAnalysisResult)
        assert result.script_type == ScriptType.FRAKTUR
        assert 0.80 <= result.ocr_confidence_score <= 0.92
        assert result.fraktur_ratio > 0.25
        assert result.ligature_counts.get("long_s", 0) > 0
        assert "Preview 2 sample pages" in result.recommended_action

    def test_classify_hybrid_document(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes
    ) -> None:
        p1 = "Introduction to twentieth century metaphysics and historical German philosophy."
        p2 = "Klages ſchrieb: Die Seele iſt die Wirklichkeit des Lebens, der Geiſt der Widerſacher."

        with patch("pypdf.PageObject.extract_text", side_effect=[p1, p2]):
            result = classifier.classify_script(sample_pdf_bytes)

        assert isinstance(result, ScriptAnalysisResult)
        assert result.script_type == ScriptType.HYBRID
        assert result.fraktur_ratio > 0.03
        assert "Preview 2 sample pages" in result.recommended_action

    def test_classify_font_descriptor_detection(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes
    ) -> None:
        """Verify Fraktur font detection via font descriptor names."""
        with patch.object(
            FrakturClassifier, "_extract_page_fonts", lambda self, page, fonts: fonts.add("Walbaum-Fraktur")
        ):
            with patch("pypdf.PageObject.extract_text", return_value="Einleitung"):
                result = classifier.classify_script(sample_pdf_bytes)

        assert result.script_type == ScriptType.FRAKTUR
        assert "Walbaum-Fraktur" in result.font_descriptors
        assert result.ocr_confidence_score < 0.90

    def test_classify_stream_and_path(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes, tmp_path: Path
    ) -> None:
        # Binary stream
        stream = io.BytesIO(sample_pdf_bytes)
        res_stream = classifier.classify_script(stream)
        assert res_stream.script_type == ScriptType.ANTIQUA

        # Path
        file_path = tmp_path / "doc.pdf"
        file_path.write_bytes(sample_pdf_bytes)
        res_path = classifier.classify_script(file_path)
        assert res_path.script_type == ScriptType.ANTIQUA

    def test_classify_max_pages_limit(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes
    ) -> None:
        result = classifier.classify_script(sample_pdf_bytes, max_pages=1)
        assert result.total_pages_analyzed == 1


class TestOCRConfidenceRating:
    """Tests for get_ocr_confidence_rating helper."""

    def test_ocr_confidence_rating_antiqua(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes
    ) -> None:
        with patch("pypdf.PageObject.extract_text", return_value="Standard latin text"):
            conf = classifier.get_ocr_confidence_rating(sample_pdf_bytes)

        assert isinstance(conf, OCRConfidence)
        assert conf.confidence_score >= 0.90
        assert not conf.preview_recommended
        assert conf.script_type == "Antiqua"
        assert "Direct batch" in conf.recommended_action

    def test_ocr_confidence_rating_fraktur(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes
    ) -> None:
        with patch("pypdf.PageObject.extract_text", return_value="Weſen des Geiſtes mit ſch und tz"):
            conf = classifier.get_ocr_confidence_rating(sample_pdf_bytes)

        assert isinstance(conf, OCRConfidence)
        assert conf.confidence_score < 0.90
        assert conf.preview_recommended
        assert conf.script_type in ("Fraktur", "Hybrid")
        assert "Preview 2 sample pages" in conf.recommended_action

    def test_custom_confidence_threshold(self, sample_pdf_bytes: bytes) -> None:
        strict_classifier = FrakturClassifier(confidence_threshold=0.99)
        with patch("pypdf.PageObject.extract_text", return_value="Standard latin text"):
            conf = strict_classifier.get_ocr_confidence_rating(sample_pdf_bytes)
        # Even though Antiqua, score is ~0.98 which is below 0.99
        assert conf.preview_recommended


class TestEdgeCasesAndDescriptorSafety:
    """Edge cases, corrupted inputs, and file descriptor closing safety."""

    def test_empty_document_handling(self, classifier: FrakturClassifier) -> None:
        pdf_bytes = _create_minimal_pdf(pages_count=1)
        with patch("pypdf.PageObject.extract_text", return_value=""):
            result = classifier.classify_script(pdf_bytes)
        assert result.script_type == ScriptType.ANTIQUA
        assert result.total_pages_analyzed == 1

    def test_corrupted_pdf_raises_value_error(
        self, classifier: FrakturClassifier
    ) -> None:
        with pytest.raises(ValueError, match="Failed to parse PDF"):
            classifier.classify_script(b"not a valid pdf file")

    def test_nonexistent_file_raises_value_error(
        self, classifier: FrakturClassifier, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.pdf"
        with pytest.raises(ValueError, match="File not found"):
            classifier.classify_script(missing)

    def test_unsupported_type_raises_type_error(
        self, classifier: FrakturClassifier
    ) -> None:
        with pytest.raises(TypeError, match="Unsupported source type"):
            classifier.classify_script(12345)  # type: ignore

    def test_extract_page_fonts_malformed_resources(
        self, classifier: FrakturClassifier
    ) -> None:
        mock_page = MagicMock()
        mock_page.get.return_value = {"/Font": None}
        fonts: set[str] = set()
        FrakturClassifier._extract_page_fonts(mock_page, fonts)
        assert len(fonts) == 0

    def test_deterministic_stream_closing(
        self, classifier: FrakturClassifier, sample_pdf_bytes: bytes, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "desc_test.pdf"
        file_path.write_bytes(sample_pdf_bytes)

        # Passing file path should open and close without leaking file descriptors
        result = classifier.classify_script(file_path)
        assert result.total_pages_analyzed == 2
