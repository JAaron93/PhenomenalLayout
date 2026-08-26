"""GCP Cost Estimator (TASK-1.5).

Pre-authentication, zero-credential cost estimation for Google Cloud Document
Translation and GCS storage. Requires no GCP credentials — operates purely on
local PDF metadata and pricing constants from GCPSettings.

Traceability: FR-07, NFR-06
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostQuote:
    """Itemized GCP cost quote for a book translation job."""

    total_pages: int
    file_size_mb: float
    base_cost: float               # Document Translation cost (USD)
    staging_overhead_cost: float   # 7-day GCS staging lifecycle cost (USD)
    storage_cost_1mo: float        # 1-month GCS standard storage (USD)
    storage_cost_12mo: float       # 12-month GCS archive storage (USD)
    free_tier_covered: bool        # True when file under GCS Always Free 5 GB tier
    total_estimate: float          # base + staging + 1-month storage (USD)
    tolerance_range: tuple[float, float]  # (min, max) within ±$5.00
    estimation_time_sec: float     # Wall-clock seconds the estimation took


# ---------------------------------------------------------------------------
# Estimator
# ---------------------------------------------------------------------------


class GCPCostEstimator:
    """Estimates GCP translation and storage costs without requiring credentials.

    All pricing constants are read from the module-level `gcp_settings` singleton.
    No GCP API calls are ever made — this class is fully offline-capable.
    """

    def __init__(self) -> None:
        from config.settings import gcp_settings
        self._settings = gcp_settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_book_cost(
        self,
        source: Path | bytes | BinaryIO,
    ) -> CostQuote:
        """Compute an itemized GCP billing estimate for a PDF book.

        This method requires NO GCP credentials and performs NO network calls.
        It reads the local PDF to count pages and measure file size.

        Args:
            source: PDF data — a Path, raw bytes, or an open binary file stream.

        Returns:
            CostQuote dataclass with all pricing fields.

        Raises:
            ValueError: If the PDF has zero pages or cannot be read.
        """
        t_start = time.monotonic()

        stream, file_size_mb, should_close = self._open_source(source)
        try:
            import pypdf
            reader = pypdf.PdfReader(stream)
            total_pages = len(reader.pages)
        except Exception as exc:
            raise ValueError(f"Failed to read PDF: {exc}") from exc
        finally:
            if should_close:
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass

        if total_pages == 0:
            raise ValueError("PDF has 0 pages — cannot estimate cost.")

        # Apply pricing formulas from design.md §3.2
        s = self._settings
        # Both source and translated output are stored ⇒ multiply by 2
        combined_gb = (file_size_mb * 2) / 1024.0

        base_cost = total_pages * s.doc_translation_price_per_page

        # Check GCS Always Free 5 GB tier
        free_tier_covered = combined_gb <= s.gcs_always_free_storage_gb

        if free_tier_covered:
            staging_overhead_cost = 0.0
            storage_cost_1mo = 0.0
            storage_cost_12mo = 0.0
        else:
            paid_gb = max(0.0, combined_gb - s.gcs_always_free_storage_gb)
            staging_overhead_cost = (
                paid_gb * s.gcs_standard_storage_per_gb_mo
                * (s.gcs_staging_expiration_days / 30.0)
            )
            storage_cost_1mo = paid_gb * s.gcs_standard_storage_per_gb_mo
            storage_cost_12mo = paid_gb * s.gcs_archive_storage_per_gb_mo * 12.0

        total_estimate = base_cost + staging_overhead_cost + storage_cost_1mo
        tolerance = s.cost_estimate_tolerance_usd
        tolerance_range = (max(0.0, total_estimate - tolerance), total_estimate + tolerance)

        estimation_time_sec = time.monotonic() - t_start

        return CostQuote(
            total_pages=total_pages,
            file_size_mb=file_size_mb,
            base_cost=round(base_cost, 4),
            staging_overhead_cost=round(staging_overhead_cost, 6),
            storage_cost_1mo=round(storage_cost_1mo, 6),
            storage_cost_12mo=round(storage_cost_12mo, 6),
            free_tier_covered=free_tier_covered,
            total_estimate=round(total_estimate, 4),
            tolerance_range=(round(tolerance_range[0], 4), round(tolerance_range[1], 4)),
            estimation_time_sec=round(estimation_time_sec, 4),
        )

    def calculate_storage_retention(self, file_size_mb: float) -> dict[str, float]:
        """Return a storage retention cost breakdown for a given file size.

        Args:
            file_size_mb: Size of one PDF in megabytes.

        Returns:
            Dict with keys: staging_7day, retention_1mo, archival_12mo, free_tier_covered.
        """
        s = self._settings
        combined_gb = (file_size_mb * 2) / 1024.0
        free_tier = combined_gb <= s.gcs_always_free_storage_gb

        if free_tier:
            return {
                "staging_7day": 0.0,
                "retention_1mo": 0.0,
                "archival_12mo": 0.0,
                "free_tier_covered": 1.0,
            }

        paid_gb = max(0.0, combined_gb - s.gcs_always_free_storage_gb)
        return {
            "staging_7day": paid_gb * s.gcs_standard_storage_per_gb_mo * (7 / 30.0),
            "retention_1mo": paid_gb * s.gcs_standard_storage_per_gb_mo,
            "archival_12mo": paid_gb * s.gcs_archive_storage_per_gb_mo * 12.0,
            "free_tier_covered": 0.0,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _open_source(source: Path | bytes | BinaryIO) -> tuple[BinaryIO, float, bool]:
        """Open the PDF source and return (stream, file_size_mb, should_close).

        For paths: opens in binary mode and measures size via os.stat.
        For bytes: wraps in BytesIO and uses len(bytes).
        For BinaryIO: measures size via seek, then rewinds.
        """
        import os

        if isinstance(source, Path):
            file_size_mb = os.path.getsize(source) / (1024 * 1024)
            return open(source, "rb"), file_size_mb, True  # noqa: SIM115
        elif isinstance(source, bytes):
            file_size_mb = len(source) / (1024 * 1024)
            return io.BytesIO(source), file_size_mb, False
        else:
            # Try to measure via seek
            try:
                pos = source.tell()
                source.seek(0, 2)  # seek to end
                size_bytes = source.tell()
                source.seek(pos)   # rewind to original position
                file_size_mb = size_bytes / (1024 * 1024)
            except (AttributeError, OSError):
                # Non-seekable stream: buffer it to measure
                data = source.read()
                file_size_mb = len(data) / (1024 * 1024)
                return io.BytesIO(data), file_size_mb, False
            return source, file_size_mb, False
