"""Tests for validate_dolphin_layout and _get_pdf_page_count in enhanced_document_processor."""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.enhanced_document_processor import (
    _get_pdf_page_count,
    validate_dolphin_layout,
)


# ---------------------------------------------------------------------------
# validate_dolphin_layout
# ---------------------------------------------------------------------------


class TestValidateDolphinLayout:
    """Tests for the standalone validate_dolphin_layout function."""

    def test_valid_layout_matching_page_count(self) -> None:
        layout = {"pages": [{"text_blocks": []}]}
        assert validate_dolphin_layout(layout, expected_page_count=1) is True

    def test_valid_layout_multiple_pages(self) -> None:
        layout = {"pages": [{}, {}, {}]}
        assert validate_dolphin_layout(layout, expected_page_count=3) is True

    def test_page_count_mismatch_returns_false(self) -> None:
        """This is the scenario the tautological check never caught."""
        layout = {"pages": [{"text_blocks": []}]}
        assert validate_dolphin_layout(layout, expected_page_count=5) is False

    def test_missing_pages_key(self) -> None:
        assert validate_dolphin_layout({}, expected_page_count=0) is False

    def test_pages_not_list(self) -> None:
        assert validate_dolphin_layout({"pages": "bad"}, expected_page_count=0) is False

    def test_not_a_dict(self) -> None:
        assert validate_dolphin_layout("bad", expected_page_count=0) is False  # type: ignore[arg-type]

    def test_page_not_dict(self) -> None:
        assert validate_dolphin_layout({"pages": ["string"]}, expected_page_count=1) is False


# ---------------------------------------------------------------------------
# _get_pdf_page_count
# ---------------------------------------------------------------------------


class TestGetPdfPageCount:
    """Tests for the _get_pdf_page_count helper."""

    def test_returns_page_count_for_valid_pdf(self, tmp_path) -> None:
        """Create a minimal valid PDF via pypdf and verify the count."""
        try:
            import pypdf
        except ImportError:
            pytest.skip("pypdf not installed")

        # Use pypdf's PdfWriter to create a 2-page PDF
        from pypdf import PdfWriter

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
# _extract_pdf_content integration: wiring verification
# ---------------------------------------------------------------------------


class TestExtractPdfContentValidation:
    """Verify _extract_pdf_content passes the real PDF page count."""

    @pytest.mark.asyncio
    async def test_uses_real_page_count_not_text_by_page_length(self) -> None:
        """The core regression test: validation should use _get_pdf_page_count
        output, not len(text_by_page)."""
        from services.enhanced_document_processor import EnhancedDocumentProcessor

        processor = EnhancedDocumentProcessor()

        # Dolphin returns a 3-page layout
        fake_layout = {
            "pages": [
                {"text_blocks": [{"text": "a"}]},
                {"text_blocks": [{"text": "b"}]},
                {"text_blocks": [{"text": "c"}]},
            ]
        }

        with (
            patch(
                "services.dolphin_client.get_layout",
                new_callable=AsyncMock,
                return_value=fake_layout,
            ) as mock_get_layout,
            # Real PDF has 5 pages — mismatch should trigger invalidation
            patch(
                "services.enhanced_document_processor._get_pdf_page_count",
                return_value=5,
            ),
            patch("os.path.getsize", return_value=1024),
        ):
            result = await processor._extract_pdf_content("/fake/doc.pdf")

        # Because 5 != 3, validate_dolphin_layout should have returned False
        # and dolphin_layout should be set to None
        assert result["dolphin_layout"] is None
        mock_get_layout.assert_called_once()

    @pytest.mark.asyncio
    async def test_matching_page_count_keeps_layout(self) -> None:
        """When real PDF page count matches layout, dolphin_layout is kept."""
        from services.enhanced_document_processor import EnhancedDocumentProcessor

        processor = EnhancedDocumentProcessor()

        fake_layout = {
            "pages": [
                {"text_blocks": [{"text": "a"}]},
                {"text_blocks": [{"text": "b"}]},
            ]
        }

        with (
            patch(
                "services.dolphin_client.get_layout",
                new_callable=AsyncMock,
                return_value=fake_layout,
            ) as mock_get_layout,
            patch(
                "services.enhanced_document_processor._get_pdf_page_count",
                return_value=2,
            ),
            patch("os.path.getsize", return_value=1024),
        ):
            result = await processor._extract_pdf_content("/fake/doc.pdf")

        assert result["dolphin_layout"] is not None
        mock_get_layout.assert_called_once()
        assert len(result["dolphin_layout"]["pages"]) == 2

    @pytest.mark.asyncio
    async def test_unknown_page_count_skips_validation(self) -> None:
        """When _get_pdf_page_count returns None, validation is skipped
        and dolphin_layout is preserved as-is."""
        from services.enhanced_document_processor import EnhancedDocumentProcessor

        processor = EnhancedDocumentProcessor()

        fake_layout = {
            "pages": [{"text_blocks": [{"text": "x"}]}]
        }

        with (
            patch(
                "services.dolphin_client.get_layout",
                new_callable=AsyncMock,
                return_value=fake_layout,
            ) as mock_get_layout,
            patch(
                "services.enhanced_document_processor._get_pdf_page_count",
                return_value=None,
            ),
            patch("os.path.getsize", return_value=1024),
        ):
            result = await processor._extract_pdf_content("/fake/doc.pdf")

        # Layout should be preserved since we can't validate
        assert result["dolphin_layout"] is not None
        mock_get_layout.assert_called_once()
