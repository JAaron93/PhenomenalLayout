"""Unit and BDD tests for FallbackPageTranslator (TASK-3.3).

Traceability: FR-13, NFR-02, NFR-09
BDD Scenario: FR-13.1
- Extract unformatted raw text from failed/skipped pages
- Translate extracted text via Cloud Translation Text v3 with session glossary
- Exponential backoff retry on transient 429/503
- Splice translated plaintext pages back into layout-preserved PDF (100% complete)
- Deterministic file descriptor cleanup and stream safety
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pypdf
import pytest
from google.api_core import exceptions as api_exceptions
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.byok_credentials_manager import BYOKCredentialsManager
from services.fallback_translator import (
    FallbackPageTranslator,
    PageText,
    TranslatedPage,
)


def _create_multi_page_pdf(pages_text: list[str]) -> bytes:
    """Helper to generate a multi-page PDF with distinct text per page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for text in pages_text:
        c.setFont("Helvetica", 12)
        c.drawString(100, 700, text)
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def mock_credentials_manager() -> MagicMock:
    mgr = MagicMock(spec=BYOKCredentialsManager)
    mgr.get_project_id.return_value = "test-project-123"
    mgr.get_translation_client.return_value = MagicMock()
    return mgr


@pytest.fixture
def fallback_translator(mock_credentials_manager: MagicMock) -> FallbackPageTranslator:
    return FallbackPageTranslator(
        credentials_manager=mock_credentials_manager,
        location="us-central1",
    )


@pytest.fixture
def sample_source_pdf() -> bytes:
    pages = [
        "Seite 1: Einleitung in die philosophische Psychologie.",
        "Seite 2: Komplexe Tafel der Seelenlehre mit Diagrammen.",  # Failed page
        "Seite 3: Schlussfolgerungen des ersten Kapitels.",
    ]
    return _create_multi_page_pdf(pages)


class TestExtractFailedPagesText:
    """Verify raw text extraction from skipped / failed page indices."""

    def test_extract_single_failed_page(
        self, fallback_translator: FallbackPageTranslator, sample_source_pdf: bytes
    ) -> None:
        # Extract page index 1 (Page 2)
        results = fallback_translator.extract_failed_pages_text(
            sample_source_pdf, failed_page_indices=[1]
        )
        assert len(results) == 1
        page_text = results[0]
        assert isinstance(page_text, PageText)
        assert page_text.page_index == 1
        assert page_text.page_number == 2
        assert "Komplexe Tafel" in page_text.raw_text
        assert page_text.extracted_successfully is True

    def test_extract_multiple_failed_pages(
        self, fallback_translator: FallbackPageTranslator, sample_source_pdf: bytes
    ) -> None:
        results = fallback_translator.extract_failed_pages_text(
            sample_source_pdf, failed_page_indices=[0, 2]
        )
        assert len(results) == 2
        assert results[0].page_index == 0
        assert results[1].page_index == 2
        assert "Seite 1" in results[0].raw_text
        assert "Seite 3" in results[1].raw_text

    def test_extract_invalid_or_out_of_range_index(
        self, fallback_translator: FallbackPageTranslator, sample_source_pdf: bytes
    ) -> None:
        results = fallback_translator.extract_failed_pages_text(
            sample_source_pdf, failed_page_indices=[99]
        )
        assert len(results) == 1
        assert results[0].extracted_successfully is False
        assert results[0].raw_text == ""


class TestTranslateFailedPages:
    """Verify translation of extracted raw text via Cloud Translation Text v3."""

    def test_translate_pages_with_session_glossary(
        self,
        fallback_translator: FallbackPageTranslator,
        mock_credentials_manager: MagicMock,
    ) -> None:
        mock_client = mock_credentials_manager.get_translation_client.return_value
        mock_translation = MagicMock()
        mock_translation.translated_text = "Page 2: Complex table of psychology with diagrams."
        mock_response = MagicMock()
        mock_response.glossary_translations = [mock_translation]
        mock_response.translations = []
        mock_client.translate_text.return_value = mock_response

        pages_text = [
            PageText(
                page_index=1,
                page_number=2,
                raw_text="Seite 2: Komplexe Tafel der Seelenlehre mit Diagrammen.",
                extracted_successfully=True,
            )
        ]

        translated = fallback_translator.translate_failed_pages(
            user_id="u1",
            pages_text=pages_text,
            glossary_name="projects/test-project-123/locations/us-central1/glossaries/sess_123",
        )

        assert len(translated) == 1
        assert translated[0].page_index == 1
        assert translated[0].page_number == 2
        assert translated[0].success is True
        assert "Complex table" in translated[0].translated_text

        mock_client.translate_text.assert_called_once()
        call_kwargs = mock_client.translate_text.call_args.kwargs
        assert call_kwargs["glossary_config"].glossary == (
            "projects/test-project-123/locations/us-central1/glossaries/sess_123"
        )

    def test_translate_pages_retry_transient_error(
        self,
        fallback_translator: FallbackPageTranslator,
        mock_credentials_manager: MagicMock,
    ) -> None:
        """Verify exponential backoff retry on HTTP 429 (NFR-02)."""
        mock_client = mock_credentials_manager.get_translation_client.return_value

        mock_translation = MagicMock()
        mock_translation.translated_text = "Translated text"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]
        mock_response.glossary_translations = []

        mock_client.translate_text.side_effect = [
            api_exceptions.ResourceExhausted("Rate limit 429"),
            mock_response,
        ]

        pages_text = [PageText(page_index=0, page_number=1, raw_text="Quelle", extracted_successfully=True)]

        with patch("time.sleep"):  # Skip real backoff delay
            translated = fallback_translator.translate_failed_pages(
                user_id="u1", pages_text=pages_text
            )

        assert len(translated) == 1
        assert translated[0].success is True
        assert translated[0].translated_text == "Translated text"
        assert mock_client.translate_text.call_count == 2

    def test_translate_empty_pages_skips_api_call(
        self,
        fallback_translator: FallbackPageTranslator,
        mock_credentials_manager: MagicMock,
    ) -> None:
        mock_client = mock_credentials_manager.get_translation_client.return_value
        pages_text = [PageText(page_index=0, page_number=1, raw_text="", extracted_successfully=False)]

        translated = fallback_translator.translate_failed_pages(
            user_id="u1", pages_text=pages_text
        )
        assert len(translated) == 1
        assert translated[0].translated_text == ""
        mock_client.translate_text.assert_not_called()


class TestSpliceFallbackPages:
    """Verify injecting translated plaintext pages into final PDF (BDD FR-13.1)."""

    def test_splice_fallback_page_bdd_fr_13_1(
        self, fallback_translator: FallbackPageTranslator, sample_source_pdf: bytes
    ) -> None:
        """Adheres to BDD Scenario FR-13.1: 1 failed page replaced by raw text translation."""
        translated_pages = [
            TranslatedPage(
                page_index=1,
                page_number=2,
                translated_text="Page 2: Complex table of psychology translated as plaintext.",
                source_text="Seite 2...",
                success=True,
            )
        ]

        # Layout PDF has 3 pages
        spliced_stream = fallback_translator.splice_fallback_pages(
            layout_pdf=sample_source_pdf,
            translated_pages=translated_pages,
        )

        assert isinstance(spliced_stream, io.BytesIO)
        reader = pypdf.PdfReader(spliced_stream)
        assert len(reader.pages) == 3

        # Page 1 (index 0) remains unchanged
        assert "Seite 1" in reader.pages[0].extract_text()
        # Page 2 (index 1) has been replaced by the translated text
        p2_text = reader.pages[1].extract_text()
        assert "Page 2: Complex table" in p2_text
        # Page 3 (index 2) remains unchanged
        assert "Seite 3" in reader.pages[2].extract_text()

    def test_splice_to_file_path(
        self,
        fallback_translator: FallbackPageTranslator,
        sample_source_pdf: bytes,
        tmp_path: Path,
    ) -> None:
        output_file = tmp_path / "final_complete.pdf"
        translated_pages = [
            TranslatedPage(
                page_index=0,
                page_number=1,
                translated_text="Replacement text",
                source_text="Quelle",
                success=True,
            )
        ]

        res = fallback_translator.splice_fallback_pages(
            layout_pdf=sample_source_pdf,
            translated_pages=translated_pages,
            output_destination=output_file,
        )
        assert Path(res) == output_file
        assert output_file.exists()
        reader = pypdf.PdfReader(output_file)
        assert len(reader.pages) == 3
        assert "Replacement text" in reader.pages[0].extract_text()

    def test_corrupted_layout_pdf_raises_value_error(
        self, fallback_translator: FallbackPageTranslator
    ) -> None:
        with pytest.raises(ValueError, match="Failed to parse layout PDF"):
            fallback_translator.splice_fallback_pages(
                layout_pdf=b"invalid pdf data",
                translated_pages=[],
            )

    def test_deterministic_stream_closing(
        self,
        fallback_translator: FallbackPageTranslator,
        sample_source_pdf: bytes,
        tmp_path: Path,
    ) -> None:
        pdf_path = tmp_path / "source.pdf"
        pdf_path.write_bytes(sample_source_pdf)

        results = fallback_translator.extract_failed_pages_text(
            pdf_path, failed_page_indices=[0]
        )
        assert len(results) == 1


class TestFallbackCoverageAndErrorBranches:
    """Ensure complete line and branch coverage."""

    def test_non_transient_api_error_reraised(
        self,
        fallback_translator: FallbackPageTranslator,
        mock_credentials_manager: MagicMock,
    ) -> None:
        mock_client = mock_credentials_manager.get_translation_client.return_value
        mock_client.translate_text.side_effect = api_exceptions.InvalidArgument("Bad arg")

        pages = [PageText(page_index=0, page_number=1, raw_text="text", extracted_successfully=True)]
        with pytest.raises(api_exceptions.InvalidArgument):
            fallback_translator.translate_failed_pages(user_id="u1", pages_text=pages)

    def test_retries_exhausted_raises_exception(
        self,
        fallback_translator: FallbackPageTranslator,
        mock_credentials_manager: MagicMock,
    ) -> None:
        mock_client = mock_credentials_manager.get_translation_client.return_value
        mock_client.translate_text.side_effect = api_exceptions.ResourceExhausted("Rate limit")

        pages = [PageText(page_index=0, page_number=1, raw_text="text", extracted_successfully=True)]
        with patch("time.sleep"):
            with pytest.raises(api_exceptions.ResourceExhausted):
                fallback_translator.translate_failed_pages(user_id="u1", pages_text=pages)

    def test_unsupported_source_type_raises_type_error(
        self, fallback_translator: FallbackPageTranslator
    ) -> None:
        with pytest.raises(TypeError, match="Unsupported source type"):
            fallback_translator.extract_failed_pages_text(12345, [0])  # type: ignore

    def test_missing_source_file_raises_value_error(
        self, fallback_translator: FallbackPageTranslator, tmp_path: Path
    ) -> None:
        missing = tmp_path / "missing.pdf"
        with pytest.raises(ValueError, match="File not found"):
            fallback_translator.extract_failed_pages_text(missing, [0])

    def test_splice_to_binary_stream_output(
        self, fallback_translator: FallbackPageTranslator, sample_source_pdf: bytes
    ) -> None:
        out_stream = io.BytesIO()
        res = fallback_translator.splice_fallback_pages(
            layout_pdf=sample_source_pdf,
            translated_pages=[],
            output_destination=out_stream,
        )
        assert res == out_stream
        assert len(out_stream.getvalue()) > 0
