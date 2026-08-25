"""Tests for GCPSettings dataclass (TASK-1.1, FR-03, NFR-03).

Verifies that the GCPSettings dataclass:
- Loads all defaults without requiring any environment variables or secrets
- Exposes the correct pricing constants per design.md §3.1
- Supports environment variable overrides via from_env()
- Is immutable (frozen=True)
"""

from __future__ import annotations

import dataclasses
import os

import pytest

from config.settings import GCPSettings, gcp_settings


class TestGCPSettingsDefaults:
    """Verify all default values match the spec (design.md §3.1 and §9)."""

    def test_gcp_location_default(self) -> None:
        s = GCPSettings()
        assert s.gcp_location == "us-central1"

    def test_doc_translation_price_per_page(self) -> None:
        s = GCPSettings()
        assert s.doc_translation_price_per_page == pytest.approx(0.080, abs=1e-6)

    def test_gcs_standard_storage_rate(self) -> None:
        s = GCPSettings()
        assert s.gcs_standard_storage_per_gb_mo == pytest.approx(0.020, abs=1e-6)

    def test_gcs_archive_storage_rate(self) -> None:
        s = GCPSettings()
        assert s.gcs_archive_storage_per_gb_mo == pytest.approx(0.0012, abs=1e-6)

    def test_gcs_always_free_storage_gb(self) -> None:
        s = GCPSettings()
        assert s.gcs_always_free_storage_gb == pytest.approx(5.0, abs=1e-6)

    def test_gcs_staging_expiration_days(self) -> None:
        s = GCPSettings()
        assert s.gcs_staging_expiration_days == 7

    def test_gcs_staging_prefix(self) -> None:
        s = GCPSettings()
        assert s.gcs_staging_prefix == "inputs/"

    def test_batch_poll_interval_sec(self) -> None:
        s = GCPSettings()
        assert s.batch_poll_interval_sec == 10

    def test_max_inline_preview_pages(self) -> None:
        s = GCPSettings()
        assert s.max_inline_preview_pages == 3

    def test_fraktur_confidence_threshold(self) -> None:
        s = GCPSettings()
        assert s.fraktur_confidence_threshold == pytest.approx(0.85, abs=1e-6)

    def test_modal_volume_path(self) -> None:
        s = GCPSettings()
        assert s.modal_volume_path == "/data"

    def test_cost_estimate_tolerance_usd(self) -> None:
        s = GCPSettings()
        assert s.cost_estimate_tolerance_usd == pytest.approx(5.00, abs=1e-6)

    def test_gcp_glossary_quota_limit(self) -> None:
        s = GCPSettings()
        assert s.gcp_glossary_quota_limit == 1000

    def test_gcp_glossary_warning_threshold(self) -> None:
        s = GCPSettings()
        assert s.gcp_glossary_warning_threshold == 900


class TestGCPSettingsNoSecretsRequired:
    """Verify that defaults load cleanly without any environment variables."""

    def test_defaults_load_without_env_vars(self) -> None:
        env_keys_to_strip = [
            "GCP_LOCATION", "GCP_DOC_TRANSLATION_PRICE_PER_PAGE",
            "GCS_STANDARD_STORAGE_PER_GB_MO", "GCS_ARCHIVE_STORAGE_PER_GB_MO",
            "GCS_ALWAYS_FREE_STORAGE_GB", "GCS_STAGING_EXPIRATION_DAYS",
            "GCS_STAGING_PREFIX", "BATCH_POLL_INTERVAL_SEC",
            "MAX_INLINE_PREVIEW_PAGES", "FRAKTUR_CONFIDENCE_THRESHOLD",
            "MODAL_VOLUME_PATH", "COST_ESTIMATE_TOLERANCE_USD",
        ]
        original = {k: os.environ.pop(k) for k in env_keys_to_strip if k in os.environ}
        try:
            settings = GCPSettings.from_env()
            assert settings.gcp_location == "us-central1"
            assert settings.doc_translation_price_per_page == pytest.approx(0.080, abs=1e-6)
        finally:
            os.environ.update(original)

    def test_no_credentials_stored_in_settings(self) -> None:
        s = GCPSettings()
        for f in dataclasses.fields(s):
            val = getattr(s, f.name)
            if isinstance(val, str) and len(val) > 40:
                pytest.fail(f"Suspiciously long string in '{f.name}' - possible credential?")


class TestGCPSettingsImmutability:
    """Verify that GCPSettings is frozen and cannot be mutated."""

    def test_frozen_raises_on_mutation(self) -> None:
        from dataclasses import FrozenInstanceError
        s = GCPSettings()
        with pytest.raises(FrozenInstanceError):
            s.gcp_location = "us-east1"  # type: ignore[misc]

    def test_price_per_page_frozen(self) -> None:
        from dataclasses import FrozenInstanceError
        s = GCPSettings()
        with pytest.raises(FrozenInstanceError):
            s.doc_translation_price_per_page = 0.10  # type: ignore[misc]


class TestGCPSettingsEnvOverride:
    """Verify that environment variables correctly override defaults."""

    def test_override_gcp_location(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GCP_LOCATION", "us-east1")
        s = GCPSettings.from_env()
        assert s.gcp_location == "us-east1"

    def test_override_price_per_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GCP_DOC_TRANSLATION_PRICE_PER_PAGE", "0.090")
        s = GCPSettings.from_env()
        assert s.doc_translation_price_per_page == pytest.approx(0.090, abs=1e-6)

    def test_override_poll_interval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BATCH_POLL_INTERVAL_SEC", "30")
        s = GCPSettings.from_env()
        assert s.batch_poll_interval_sec == 30

    def test_override_modal_volume_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MODAL_VOLUME_PATH", "/mnt/data")
        s = GCPSettings.from_env()
        assert s.modal_volume_path == "/mnt/data"


class TestGCPSettingsSingleton:
    """Verify the module-level gcp_settings singleton."""

    def test_singleton_is_gcpsettings_instance(self) -> None:
        assert isinstance(gcp_settings, GCPSettings)

    def test_singleton_has_correct_location(self) -> None:
        expected = os.getenv("GCP_LOCATION", "us-central1")
        assert gcp_settings.gcp_location == expected

    def test_singleton_price_is_positive(self) -> None:
        assert gcp_settings.doc_translation_price_per_page > 0.0


class TestGCPPricingMath:
    """Verify pricing constants produce correct values per design.md §3.2."""

    def test_350_page_book_base_cost(self) -> None:
        s = GCPSettings()
        cost = 350 * s.doc_translation_price_per_page
        assert cost == pytest.approx(28.00, abs=0.01)

    def test_staging_overhead_15mb_is_negligible(self) -> None:
        s = GCPSettings()
        file_size_mb = 15.0
        total_gb = (file_size_mb * 2) / 1024
        overhead = total_gb * s.gcs_standard_storage_per_gb_mo * (s.gcs_staging_expiration_days / 30)
        assert overhead < 0.001

    def test_free_tier_covers_small_books(self) -> None:
        s = GCPSettings()
        small_book_mb = 50.0
        total_gb = (small_book_mb * 2) / 1024
        assert total_gb < s.gcs_always_free_storage_gb
