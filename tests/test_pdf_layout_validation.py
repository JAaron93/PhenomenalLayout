"""Tests for validate_pdf_layout and _get_pdf_page_count in enhanced_document_processor."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.enhanced_document_processor import (
    _get_pdf_page_count,
    validate_pdf_layout,
)


# ---------------------------------------------------------------------------
# validate_pdf_layout
# ---------------------------------------------------------------------------


class TestValidatePdfLayout:
    """Tests for the standalone validate_pdf_layout function."""

    def test_valid_layout_matching_page_count(self) -> None:
        layout = {"pages": [{"text_blocks": []}]}
        assert validate_pdf_layout(layout, expected_page_count=1) is True

    def test_valid_layout_multiple_pages(self) -> None:
        layout = {"pages": [{}, {}, {}]}
        assert validate_pdf_layout(layout, expected_page_count=3) is True

    def test_page_count_mismatch_returns_false(self) -> None:
        """This is the scenario the tautological check never caught."""
        layout = {"pages": [{"text_blocks": []}]}
        assert validate_pdf_layout(layout, expected_page_count=5) is False

    def test_missing_pages_key(self) -> None:
        assert validate_pdf_layout({}, expected_page_count=0) is False

    def test_pages_not_list(self) -> None:
        assert validate_pdf_layout({"pages": "bad"}, expected_page_count=0) is False

    def test_not_a_dict(self) -> None:
        assert validate_pdf_layout("bad", expected_page_count=0) is False  # type: ignore[arg-type]

    def test_page_not_dict(self) -> None:
        assert validate_pdf_layout({"pages": ["string"]}, expected_page_count=1) is False


# ---------------------------------------------------------------------------
# _get_pdf_page_count
# ---------------------------------------------------------------------------


class TestGetPdfPageCount:
    """Tests for the _get_pdf_page_count helper."""

    def test_returns_page_count_for_valid_pdf(self, tmp_path) -> None:
        """Create a minimal valid PDF via pypdf and verify the count."""
        try:
            from pypdf import PdfWriter
        except ImportError:
            pytest.skip("pypdf not installed")

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        pdf_file = tmp_path / "two_pages.pdf"
        with open(pdf_file, "wb") as f:
            writer.write(f)

        assert _get_pdf_page_count(str(pdf_file)) == 2

    def test_returns_none_for_missing_file(self) -> None:
        assert _get_pdf_page_count("/nonexistent/path.pdf") is None

    def test_returns_none_for_corrupt_file(self, tmp_path) -> None:
        corrupt = tmp_path / "corrupt.pdf"
        corrupt.write_bytes(b"not a pdf")
        assert _get_pdf_page_count(str(corrupt)) is None

    def test_returns_none_when_pypdf_unavailable(self) -> None:
        """Ensure graceful fallback when pypdf cannot be imported."""
        with patch.dict("sys.modules", {"pypdf": None}):
            assert _get_pdf_page_count("any_path.pdf") is None


# ---------------------------------------------------------------------------
# _extract_pdf_content integration: post-retirement layout handling
# ---------------------------------------------------------------------------


class TestExtractPdfContentLayout:
    """Verify _extract_pdf_content layout handling after OCR retirement (ADR 0001)."""

    @pytest.mark.asyncio
    async def test_known_page_count_discards_unsourced_layout(self) -> None:
        """With a known real page count, the empty placeholder layout cannot
        match and is discarded."""
        from services.enhanced_document_processor import EnhancedDocumentProcessor

        processor = EnhancedDocumentProcessor()

        with (
            patch(
                "services.enhanced_document_processor._get_pdf_page_count",
                return_value=5,
            ),
            patch("os.path.getsize", return_value=1024),
        ):
            result = await processor._extract_pdf_content("/fake/doc.pdf")

        assert result["layout"] is None
        assert result["text_by_page"] == {}

    @pytest.mark.asyncio
    async def test_unknown_page_count_preserves_empty_layout(self) -> None:
        """When the page count cannot be determined, validation is skipped
        and the empty layout is preserved as-is."""
        from services.enhanced_document_processor import EnhancedDocumentProcessor

        processor = EnhancedDocumentProcessor()

        with (
            patch(
                "services.enhanced_document_processor._get_pdf_page_count",
                return_value=None,
            ),
            patch("os.path.getsize", return_value=1024),
        ):
            result = await processor._extract_pdf_content("/fake/doc.pdf")

        assert result["layout"] == {"pages": []}
        assert result["text_by_page"] == {}

    @pytest.mark.asyncio
    async def test_metadata_computed_from_empty_layout(self) -> None:
        """Metadata stays well-formed when no layout source exists."""
        from services.enhanced_document_processor import EnhancedDocumentProcessor

        processor = EnhancedDocumentProcessor()

        with (
            patch(
                "services.enhanced_document_processor._get_pdf_page_count",
                return_value=None,
            ),
            patch("os.path.getsize", return_value=1024),
        ):
            result = await processor._extract_pdf_content("/fake/doc.pdf")

        metadata = result["metadata"]
        assert metadata.file_type == "PDF"
        assert metadata.total_pages == 0
        assert metadata.total_text_elements == 0
        assert metadata.file_size_mb == 1024 / (1024 * 1024)
