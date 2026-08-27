"""Unit tests for DualPaneViewerController (TASK-3.4).

Traceability: FR-15, NFR-05, NFR-09
- Synchronized bilingual page pair generation (German original + English layout PDF)
- Text and optional base64 rasterized image serving with graceful fallback
- Search term highlighting across panes with bounding box extraction
- Bounds checking, stream safety, and deterministic descriptor cleanup
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.dual_pane_viewer import (
    BilingualPagePair,
    DualPaneViewerController,
    HighlightCoordinates,
    TextBoundingBox,
)


def _create_sample_pdf(pages_text: list[str]) -> bytes:
    """Helper to generate an in-memory PDF with specified text per page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for text in pages_text:
        c.setFont("Helvetica", 12)
        text_obj = c.beginText(50, 700)
        for line in text.split("\n"):
            text_obj.textLine(line)
        c.drawText(text_obj)
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def viewer() -> DualPaneViewerController:
    return DualPaneViewerController()


@pytest.fixture
def german_pdf_bytes() -> bytes:
    p1 = (
        "Kapitel 1: Die Grundbegriffe der philosophischen Psychologie.\n"
        "Der Begriff Schauung bezeichnet die unmittelbare Wahrnehmung des Wesens.\n"
        "Hier wird die Lebensphilosophie vertieft."
    )
    p2 = "Kapitel 2: Der Geist als Widersacher der Seele."
    return _create_sample_pdf([p1, p2])


@pytest.fixture
def english_pdf_bytes() -> bytes:
    p1 = (
        "Chapter 1: The foundational concepts of philosophical psychology.\n"
        "The term Intuitive Vision designates the immediate perception of essence.\n"
        "Here the philosophy of life is deepened."
    )
    p2 = "Chapter 2: The Spirit as Adversary of the Soul."
    return _create_sample_pdf([p1, p2])


class TestGetBilingualPagePair:
    """Verify synchronized page retrieval."""

    def test_get_page_pair_text_content(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        pair = viewer.get_bilingual_page_pair(
            german_source=german_pdf_bytes,
            english_source=english_pdf_bytes,
            page_number=1,
            render_images=False,
        )

        assert isinstance(pair, BilingualPagePair)
        assert pair.page_number == 1
        assert pair.total_pages_german == 2
        assert pair.total_pages_english == 2
        assert "Schauung" in pair.german_text
        assert "Intuitive Vision" in pair.english_text
        assert pair.german_page_image_base64 is None
        assert pair.english_page_image_base64 is None

    def test_page_number_out_of_range_raises_value_error(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        with pytest.raises(ValueError, match="Page number 0 is out of bounds"):
            viewer.get_bilingual_page_pair(german_pdf_bytes, english_pdf_bytes, page_number=0)

        with pytest.raises(ValueError, match="Page number 5 exceeds total pages"):
            viewer.get_bilingual_page_pair(german_pdf_bytes, english_pdf_bytes, page_number=5)

    def test_graceful_fallback_when_rendering_fails(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        """When pdf2image or poppler is unavailable, gracefully fall back to text-only."""
        with patch.object(DualPaneViewerController, "_render_page_image", return_value=None):
            pair = viewer.get_bilingual_page_pair(
                german_source=german_pdf_bytes,
                english_source=english_pdf_bytes,
                page_number=1,
                render_images=True,
            )

        assert pair.german_page_image_base64 is None
        assert pair.has_images is False
        assert "Schauung" in pair.german_text

    def test_render_images_success(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        fake_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        with patch.object(DualPaneViewerController, "_render_page_image", return_value=fake_b64):
            pair = viewer.get_bilingual_page_pair(
                german_source=german_pdf_bytes,
                english_source=english_pdf_bytes,
                page_number=1,
                render_images=True,
            )

        assert pair.has_images is True
        assert pair.german_page_image_base64 == fake_b64
        assert pair.english_page_image_base64 == fake_b64


class TestSearchTermAcrossPanes:
    """Verify neologism highlight coordinate extraction."""

    def test_search_term_found_in_both_panes(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        coords = viewer.search_term_across_panes(
            german_source=german_pdf_bytes,
            english_source=english_pdf_bytes,
            german_term="Schauung",
            english_term="Intuitive Vision",
            page_number=1,
        )

        assert isinstance(coords, HighlightCoordinates)
        assert coords.page_number == 1
        assert coords.german_term == "Schauung"
        assert coords.english_term == "Intuitive Vision"

        assert len(coords.german_matches) >= 1
        assert coords.german_matches[0].text == "Schauung"
        assert coords.german_matches[0].page_number == 1

        assert len(coords.english_matches) >= 1
        assert "Intuitive Vision" in coords.english_matches[0].text
        assert coords.english_matches[0].page_number == 1

    def test_search_term_not_found(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        coords = viewer.search_term_across_panes(
            german_source=german_pdf_bytes,
            english_source=english_pdf_bytes,
            german_term="UnbekanntesWort",
            english_term="UnknownWord",
            page_number=1,
        )

        assert len(coords.german_matches) == 0
        assert len(coords.english_matches) == 0

    def test_search_term_case_insensitivity(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        coords = viewer.search_term_across_panes(
            german_source=german_pdf_bytes,
            english_source=english_pdf_bytes,
            german_term="schauung",
            english_term="intuitive vision",
            page_number=1,
            case_sensitive=False,
        )
        assert len(coords.german_matches) >= 1
        assert len(coords.english_matches) >= 1


class TestStreamAndDescriptorSafety:
    """Verify Path, bytes, streams, and cleanup."""

    def test_path_and_stream_inputs(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
        tmp_path: Path,
    ) -> None:
        p_de = tmp_path / "de.pdf"
        p_en = tmp_path / "en.pdf"
        p_de.write_bytes(german_pdf_bytes)
        p_en.write_bytes(english_pdf_bytes)

        pair = viewer.get_bilingual_page_pair(
            german_source=p_de,
            english_source=io.BytesIO(english_pdf_bytes),
            page_number=1,
            render_images=False,
        )
        assert pair.page_number == 1

    def test_corrupted_pdf_raises_value_error(
        self, viewer: DualPaneViewerController, english_pdf_bytes: bytes
    ) -> None:
        with pytest.raises(ValueError, match="Failed to parse German PDF"):
            viewer.get_bilingual_page_pair(
                german_source=b"bad pdf",
                english_source=english_pdf_bytes,
                page_number=1,
            )

    def test_unsupported_source_type_raises_type_error(
        self, viewer: DualPaneViewerController
    ) -> None:
        with pytest.raises(TypeError, match="Unsupported source type"):
            viewer._open_source(12345)  # type: ignore


class TestDualPaneViewerCoverageBranches:
    """Comprehensive branch coverage for DualPaneViewerController."""

    def test_english_pdf_parsing_error(
        self, viewer: DualPaneViewerController, german_pdf_bytes: bytes
    ) -> None:
        with pytest.raises(ValueError, match="Failed to parse English PDF"):
            viewer.get_bilingual_page_pair(
                german_source=german_pdf_bytes,
                english_source=b"corrupted",
                page_number=1,
            )

    def test_page_exceeds_english_pdf_length(
        self, viewer: DualPaneViewerController
    ) -> None:
        p_de = _create_sample_pdf(["p1", "p2", "p3"])
        p_en = _create_sample_pdf(["p1", "p2"])

        with pytest.raises(ValueError, match="Page number 3 exceeds total pages in English PDF"):
            viewer.get_bilingual_page_pair(p_de, p_en, page_number=3)

    def test_search_empty_term_returns_empty_list(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        coords = viewer.search_term_across_panes(
            german_source=german_pdf_bytes,
            english_source=english_pdf_bytes,
            german_term="  ",
            english_term="",
            page_number=1,
        )
        assert len(coords.german_matches) == 0
        assert len(coords.english_matches) == 0

    def test_search_out_of_range_page(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        coords = viewer.search_term_across_panes(
            german_source=german_pdf_bytes,
            english_source=english_pdf_bytes,
            german_term="Schauung",
            english_term="Vision",
            page_number=99,
        )
        assert len(coords.german_matches) == 0
        assert len(coords.english_matches) == 0

    def test_search_fallback_when_fragment_visitor_fails(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
        english_pdf_bytes: bytes,
    ) -> None:
        """When visitor_text doesn't record fragments, whole-page search is used."""
        with patch("pypdf.PageObject.extract_text") as mock_extract:
            # First call is for visitor_text (does nothing), second call returns text
            def side_effect(visitor_text=None):
                if visitor_text:
                    return ""
                return "Dies ist eine Schauung der Welt."
            mock_extract.side_effect = side_effect

            coords = viewer.search_term_across_panes(
                german_source=german_pdf_bytes,
                english_source=english_pdf_bytes,
                german_term="Schauung",
                english_term="Intuitive Vision",
                page_number=1,
            )
            assert len(coords.german_matches) >= 1
            assert coords.german_matches[0].text == "Schauung"

    def test_render_page_image_internal_execution(
        self,
        viewer: DualPaneViewerController,
        german_pdf_bytes: bytes,
    ) -> None:
        """Exercise internal _render_page_image path by mocking convert_from_bytes."""
        mock_image = MagicMock()
        mock_image.save = lambda buf, format: buf.write(b"fake-png-bytes")

        with patch("pdf2image.convert_from_bytes", return_value=[mock_image]):
            b64 = viewer._render_page_image(german_pdf_bytes, page_number=1, dpi=150)
            assert b64 is not None
            assert b64.startswith("data:image/png;base64,")

        # Empty image list from convert_from_bytes
        with patch("pdf2image.convert_from_bytes", return_value=[]):
            b64_empty = viewer._render_page_image(german_pdf_bytes, page_number=1, dpi=150)
            assert b64_empty is None

        # Exception from convert_from_bytes
        with patch("pdf2image.convert_from_bytes", side_effect=RuntimeError("Poppler error")):
            b64_err = viewer._render_page_image(german_pdf_bytes, page_number=1, dpi=150)
            assert b64_err is None

    def test_missing_file_in_open_source(
        self, viewer: DualPaneViewerController, tmp_path: Path
    ) -> None:
        missing = tmp_path / "missing.pdf"
        with pytest.raises(ValueError, match="file not found"):
            viewer._open_source(missing)
