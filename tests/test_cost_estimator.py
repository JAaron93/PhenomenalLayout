"""Unit and BDD scenario tests for GCPCostEstimator (TASK-1.5).

Traceability: FR-07, NFR-06
- Zero-auth offline cost calculation
- Base Document Translation ($0.080/page)
- GCS Always Free 5 GB Tier eligibility check
- 7-day staging and monthly retention calculation
- Tolerance range within ±$5.00
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pypdf

from services.cost_estimator import CostQuote, GCPCostEstimator


def _create_mock_pdf_bytes(page_count: int) -> bytes:
    """Generate a valid in-memory PDF with the specified number of pages."""
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


@pytest.fixture
def estimator() -> GCPCostEstimator:
    return GCPCostEstimator()


class TestCostEstimatorZeroAuthBDD:
    """BDD Scenario FR-07.1: Estimate costs for a 350-page PDF."""

    def test_estimate_350_page_book_under_free_tier(self, estimator: GCPCostEstimator) -> None:
        """350-page PDF (e.g. 15MB): base cost is $28.00, storage is $0.00 (under 5GB)."""
        pdf_bytes = _create_mock_pdf_bytes(page_count=350)
        quote = estimator.estimate_book_cost(pdf_bytes)

        assert isinstance(quote, CostQuote)
        assert quote.total_pages == 350
        assert quote.base_cost == pytest.approx(28.00, abs=0.01)
        assert quote.free_tier_covered is True
        assert quote.staging_overhead_cost == pytest.approx(0.00, abs=1e-5)
        assert quote.storage_cost_1mo == pytest.approx(0.00, abs=1e-5)
        assert quote.storage_cost_12mo == pytest.approx(0.00, abs=1e-5)
        assert quote.total_estimate == pytest.approx(28.00, abs=0.01)
        # Tolerance range ±$5.00
        min_est, max_est = quote.tolerance_range
        assert min_est == pytest.approx(23.00, abs=0.01)
        assert max_est == pytest.approx(33.00, abs=0.01)
        assert quote.estimation_time_sec < 1.0

    def test_estimate_large_book_exceeding_free_tier(self, estimator: GCPCostEstimator) -> None:
        """Mock a 10,000 MB file (combined 20,000 MB > 5,120 MB free tier)."""
        pdf_bytes = _create_mock_pdf_bytes(page_count=100)

        with patch.object(estimator, "_open_source") as mock_open:
            # 10,000 MB file -> 20 GB combined
            mock_open.return_value = (io.BytesIO(pdf_bytes), 10000.0, False)
            quote = estimator.estimate_book_cost(pdf_bytes)

            assert quote.total_pages == 100
            assert quote.base_cost == pytest.approx(8.00, abs=0.01)
            assert quote.free_tier_covered is False
            assert quote.staging_overhead_cost > 0.0
            assert quote.storage_cost_1mo > 0.0
            assert quote.storage_cost_12mo > 0.0
            assert quote.total_estimate > 8.00


class TestCalculateStorageRetention:
    """Test calculate_storage_retention method."""

    def test_retention_small_file_free_tier(self, estimator: GCPCostEstimator) -> None:
        breakdown = estimator.calculate_storage_retention(file_size_mb=25.0)
        assert breakdown["free_tier_covered"] == 1.0
        assert breakdown["staging_7day"] == 0.0
        assert breakdown["retention_1mo"] == 0.0
        assert breakdown["archival_12mo"] == 0.0

    def test_retention_huge_file_paid(self, estimator: GCPCostEstimator) -> None:
        breakdown = estimator.calculate_storage_retention(file_size_mb=5000.0)
        assert breakdown["free_tier_covered"] == 0.0
        assert breakdown["staging_7day"] > 0.0
        assert breakdown["retention_1mo"] > 0.0
        assert breakdown["archival_12mo"] > 0.0


class TestCostEstimatorEdgeCases:
    """Test error handling and edge cases."""

    def test_estimate_with_path(self, estimator: GCPCostEstimator, tmp_path: Path) -> None:
        pdf_bytes = _create_mock_pdf_bytes(page_count=5)
        test_file = tmp_path / "sample.pdf"
        test_file.write_bytes(pdf_bytes)

        quote = estimator.estimate_book_cost(test_file)
        assert quote.total_pages == 5
        assert quote.base_cost == pytest.approx(0.40, abs=0.01)

    def test_estimate_with_non_seekable_stream(self, estimator: GCPCostEstimator) -> None:
        pdf_bytes = _create_mock_pdf_bytes(page_count=3)

        class NonSeekableStream(io.BytesIO):
            def seek(self, offset: int, whence: int = 0) -> int:
                raise OSError("Stream not seekable")

        stream = NonSeekableStream(pdf_bytes)
        quote = estimator.estimate_book_cost(stream)
        assert quote.total_pages == 3
        assert quote.base_cost == pytest.approx(0.24, abs=0.01)

    def test_zero_pages_raises_value_error(self, estimator: GCPCostEstimator) -> None:
        with patch("pypdf.PdfReader") as mock_reader_cls:
            mock_reader = MagicMock()
            mock_reader.pages = []
            mock_reader_cls.return_value = mock_reader

            with pytest.raises(ValueError, match="0 pages"):
                estimator.estimate_book_cost(b"%PDF-mock")

    def test_corrupt_pdf_bytes_raises_value_error(self, estimator: GCPCostEstimator) -> None:
        with pytest.raises(ValueError, match="Failed to read PDF"):
            estimator.estimate_book_cost(b"Not a real PDF file header")
