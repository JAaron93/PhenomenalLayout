import pytest

from dolphin_ocr.config import (
    AlertThresholds,
    ConfigurationManager,
    DolphinConfig,
    PerformanceConfig,
    QualityThresholds,
)


def test_dolphin_config_validation(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "testtoken")
    monkeypatch.setenv("DOLPHIN_MODAL_ENDPOINT", "https://example.com/endpoint")
    cfg = DolphinConfig()
    assert cfg.hf_token == "testtoken"
    assert cfg.modal_endpoint.startswith("https://")
    # Test validation passes with valid config


@pytest.mark.parametrize("dpi", [150, 300, 600])
def test_performance_config_valid_dpi(monkeypatch, dpi):
    monkeypatch.setenv("PDF_DPI", str(dpi))
    perf = PerformanceConfig()
    assert perf.dpi == dpi


@pytest.mark.parametrize("invalid_dpi", [149, 601, 0, -100])
def test_performance_config_invalid_dpi(monkeypatch, invalid_dpi):
    monkeypatch.setenv("PDF_DPI", str(invalid_dpi))
    with pytest.raises(ValueError, match="PDF_DPI must be between 150 and 600"):
        PerformanceConfig()


def test_dolphin_config_validation_failures(monkeypatch):
    # Test missing HF_TOKEN
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("DOLPHIN_MODAL_ENDPOINT", raising=False)
    cfg = DolphinConfig()
    with pytest.raises(ValueError, match="HF_TOKEN is required"):
        cfg.validate()

    # Test invalid endpoint
    monkeypatch.setenv("HF_TOKEN", "token")
    monkeypatch.setenv("DOLPHIN_MODAL_ENDPOINT", "invalid-url")
    cfg = DolphinConfig()
    with pytest.raises(ValueError, match="must be a valid HTTP/HTTPS URL"):
        cfg.validate()


def test_alert_thresholds_ranges(monkeypatch):
    monkeypatch.setenv("ALERT_ERROR_RATE_THRESHOLD", "0.1")
    monkeypatch.setenv("ALERT_ERROR_RATE_WINDOW", "600")
    monkeypatch.setenv("ALERT_CRITICAL_ERROR_THRESHOLD", "5")


def test_configuration_manager_summary(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "abc")
    monkeypatch.setenv(
        "DOLPHIN_MODAL_ENDPOINT",
        "https://example.com/endpoint",
    )
    cm = ConfigurationManager()
    summary = cm.get_environment_summary()
    assert summary["hf_token_configured"] is True
    assert summary["dolphin_endpoint"].startswith("https://")
    # Verify all expected fields are present and valid
    expected_keys = {
        "dolphin_endpoint",
        "timeout_seconds",
        "max_concurrent_requests",
        "dpi",
        "error_rate_threshold",
        "min_quality_score",
        "hf_token_configured",
        "max_retries",
        "batch_size",
        "processing_timeout",
    }
    assert set(summary.keys()) == expected_keys
    assert isinstance(summary["timeout_seconds"], int)
    assert isinstance(summary["max_concurrent_requests"], int)
    assert isinstance(summary["dpi"], int)
    assert isinstance(summary["error_rate_threshold"], float)
    assert isinstance(summary["min_quality_score"], float)


def test_quality_thresholds_ranges(monkeypatch):
    monkeypatch.setenv("MIN_OCR_CONFIDENCE", "0.8")
    monkeypatch.setenv("MIN_TRANSLATION_CONFIDENCE", "0.7")
    monkeypatch.setenv("MIN_LAYOUT_PRESERVATION_SCORE", "0.75")
    monkeypatch.setenv("MIN_OVERALL_QUALITY_SCORE", "0.85")
    qual = QualityThresholds()
    assert 0.1 <= qual.min_ocr_confidence <= 1.0
    assert 0.1 <= qual.min_translation_confidence <= 1.0
    assert 0.1 <= qual.min_layout_preservation_score <= 1.0
    assert 0.1 <= qual.min_overall_quality_score <= 1.0


def test_configuration_manager_validation_failures(monkeypatch):
    # HF token missing -> credentials required
    monkeypatch.setenv("HF_TOKEN", "")
    monkeypatch.setenv("DOLPHIN_MODAL_ENDPOINT", "https://example.com/e")
    cm = ConfigurationManager()
    with pytest.raises(ValueError, match="HF_TOKEN is required"):
        cm.require_credentials()
    with pytest.raises(ValueError, match="HF_TOKEN is required"):
        cm.validate_all()


def test_performance_config_validation_failures(monkeypatch):
    # Out-of-range concurrency
    monkeypatch.setenv("MAX_CONCURRENT_REQUESTS", "0")
    with pytest.raises(
        ValueError, match="MAX_CONCURRENT_REQUESTS must be between 1 and 100"
    ):
        PerformanceConfig()
    # Out-of-range processing timeout
    monkeypatch.setenv("MAX_CONCURRENT_REQUESTS", "10")
    monkeypatch.setenv("PROCESSING_TIMEOUT", "2000")
    with pytest.raises(
        ValueError, match="PROCESSING_TIMEOUT must be between 1 and 1800 seconds"
    ):
        PerformanceConfig()


def test_alert_thresholds_validation_failures(monkeypatch):
    monkeypatch.setenv("ALERT_ERROR_RATE_THRESHOLD", "0.0")
    with pytest.raises(
        ValueError, match="ALERT_ERROR_RATE_THRESHOLD must be between 0.01 and 0.5"
    ):
        AlertThresholds()


def test_quality_thresholds_validation_failures(monkeypatch):
    monkeypatch.setenv("MIN_OCR_CONFIDENCE", "0.05")
    with pytest.raises(
        ValueError, match="MIN_OCR_CONFIDENCE must be between 0.1 and 1.0"
    ):
        QualityThresholds()
