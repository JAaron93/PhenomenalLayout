"""Central configuration management for Dolphin OCR.

Implements environment-backed configuration objects and a manager with
validation and a summarized environment view, aligned with the design
document.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


def env_int(name: str, default: int) -> int:
    """Read integer env var with clear error messages.

    Returns default when unset; raises ValueError with the env name and
    raw value when parsing fails.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"Invalid integer for {name}={raw!r}") from e


def env_float(name: str, default: float) -> float:
    """Read float env var with clear error messages.

    Returns default when unset; raises ValueError with the env name and
    raw value when parsing fails.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"Invalid float for {name}={raw!r}") from e


@dataclass
class DolphinConfig:
    """Dolphin OCR service configuration.

    Provides environment defaults. Validation of credentials and URL format is
    intentionally deferred and performed by the higher-level
    :class:`ConfigurationManager` (see ``ConfigurationManager.validate_all`` in
    ``dolphin_ocr.config``). This allows instances to be created in tests and
    dependency-injection contexts without requiring real credentials at
    construction time. Callers must ensure validation is invoked before any
    Hugging Face or network-dependent operations.
    """

    hf_token: str = field(
        default_factory=lambda: os.getenv("HF_TOKEN", ""),
        repr=False,
    )
    modal_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "DOLPHIN_MODAL_ENDPOINT",
            (
                "https://modal-labs--dolphin-ocr-service-"
                "dolphin-ocr-endpoint.modal.run"
            ),
        )
    )
    timeout_seconds: int = field(
        default_factory=lambda: env_int("DOLPHIN_TIMEOUT_SECONDS", 300)
    )
    max_retries: int = field(default_factory=lambda: env_int("DOLPHIN_MAX_RETRIES", 3))
    batch_size: int = field(default_factory=lambda: env_int("DOLPHIN_BATCH_SIZE", 5))

    # NOTE: Validation is deferred to ConfigurationManager; see class docstring.
    def __post_init__(self) -> None:
        """Construct without enforcing credentials.

        Lifecycle: objects may be instantiated freely; prior to use in
        production paths, ``ConfigurationManager.validate_all()`` (or
        ``require_credentials()``) will enforce required fields and raise
        descriptive ``ValueError`` on misconfiguration.
        """
        return None

    def validate(self) -> None:
        """Validate Dolphin configuration values."""
        if not self.hf_token:
            raise ValueError("HF_TOKEN is required for Dolphin OCR authentication")
        if not self.modal_endpoint:
            raise ValueError("DOLPHIN_MODAL_ENDPOINT is required")
        # Normalize and validate endpoint using robust URL parsing
        endpoint = (self.modal_endpoint or "").strip()
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("DOLPHIN_MODAL_ENDPOINT must be a valid HTTP/HTTPS URL")
        # Persist normalized value
        self.modal_endpoint = endpoint
        if self.timeout_seconds <= 0 or self.timeout_seconds > 3600:
            raise ValueError(
                "DOLPHIN_TIMEOUT_SECONDS must be between 1 and 3600 seconds"
            )
        if self.max_retries < 0 or self.max_retries > 10:
            raise ValueError("DOLPHIN_MAX_RETRIES must be between 0 and 10")
        if self.batch_size <= 0 or self.batch_size > 50:
            raise ValueError("DOLPHIN_BATCH_SIZE must be between 1 and 50")


@dataclass
class PerformanceConfig:
    """Performance and monitoring configuration with environment defaults."""

    max_concurrent_requests: int = field(
        default_factory=lambda: env_int("MAX_CONCURRENT_REQUESTS", 10)
    )
    processing_timeout: int = field(
        default_factory=lambda: env_int("PROCESSING_TIMEOUT", 300)
    )
    dpi: int = field(default_factory=lambda: env_int("PDF_DPI", 300))
    memory_limit_mb: int = field(
        default_factory=lambda: env_int("MEMORY_LIMIT_MB", 2048)
    )

    def __post_init__(self) -> None:
        """Validate performance configuration on creation."""
        self.validate()

    def validate(self) -> None:
        """Validate performance constraints and ranges.

        Ensures concurrency, timeout, DPI and memory limits are sane.
        """
        if self.max_concurrent_requests <= 0 or self.max_concurrent_requests > 100:
            raise ValueError("MAX_CONCURRENT_REQUESTS must be between 1 and 100")
        if self.processing_timeout <= 0 or self.processing_timeout > 1800:
            raise ValueError("PROCESSING_TIMEOUT must be between 1 and 1800 seconds")
        if self.dpi < 150 or self.dpi > 600:
            raise ValueError(
                "PDF_DPI must be between 150 and 600 for optimal OCR quality"
            )
        if self.memory_limit_mb < 512 or self.memory_limit_mb > 8192:
            raise ValueError("MEMORY_LIMIT_MB must be between 512 and 8192 MB")


@dataclass
class AlertThresholds:
    """Alert threshold configuration with environment defaults.

    Includes validation constraints to keep alerting sensible.
    """

    error_rate_threshold: float = field(
        default_factory=lambda: env_float("ALERT_ERROR_RATE_THRESHOLD", 0.05)
    )
    error_rate_window: int = field(
        default_factory=lambda: env_int("ALERT_ERROR_RATE_WINDOW", 300)
    )
    critical_error_threshold: int = field(
        default_factory=lambda: env_int("ALERT_CRITICAL_ERROR_THRESHOLD", 3)
    )
    latency_threshold_multiplier: float = field(
        default_factory=lambda: env_float("ALERT_LATENCY_MULTIPLIER", 1.5)
    )
    quota_warning_threshold: float = field(
        default_factory=lambda: env_float("ALERT_QUOTA_WARNING_THRESHOLD", 0.8)
    )

    def __post_init__(self) -> None:
        """Validate alert thresholds on creation."""
        self.validate()

    def validate(self) -> None:
        """Validate alert threshold ranges."""
        if not 0.01 <= self.error_rate_threshold <= 0.5:
            raise ValueError("ALERT_ERROR_RATE_THRESHOLD must be between 0.01 and 0.5")
        if self.error_rate_window < 60 or self.error_rate_window > 3600:
            raise ValueError(
                "ALERT_ERROR_RATE_WINDOW must be between 60 and 3600 seconds"
            )
        if self.critical_error_threshold < 1 or self.critical_error_threshold > 20:
            raise ValueError("ALERT_CRITICAL_ERROR_THRESHOLD must be between 1 and 20")
        if not 1.1 <= self.latency_threshold_multiplier <= 3.0:
            raise ValueError("ALERT_LATENCY_MULTIPLIER must be between 1.1 and 3.0")
        if not 0.5 <= self.quota_warning_threshold <= 0.95:
            raise ValueError(
                "ALERT_QUOTA_WARNING_THRESHOLD must be between 0.5 and 0.95"
            )


@dataclass
class QualityThresholds:
    """Quality threshold configuration with environment defaults."""

    min_ocr_confidence: float = field(
        default_factory=lambda: env_float("MIN_OCR_CONFIDENCE", 0.8)
    )
    min_translation_confidence: float = field(
        default_factory=lambda: env_float("MIN_TRANSLATION_CONFIDENCE", 0.7)
    )
    min_layout_preservation_score: float = field(
        default_factory=lambda: env_float("MIN_LAYOUT_PRESERVATION_SCORE", 0.7)
    )
    min_overall_quality_score: float = field(
        default_factory=lambda: env_float("MIN_OVERALL_QUALITY_SCORE", 0.8)
    )

    def __post_init__(self) -> None:
        """Validate quality thresholds on creation."""
        self.validate()

    def validate(self) -> None:
        """Validate quality thresholds are within 0.1..1.0."""
        thresholds = {
            "MIN_OCR_CONFIDENCE": self.min_ocr_confidence,
            "MIN_TRANSLATION_CONFIDENCE": self.min_translation_confidence,
            "MIN_LAYOUT_PRESERVATION_SCORE": (self.min_layout_preservation_score),
            "MIN_OVERALL_QUALITY_SCORE": self.min_overall_quality_score,
        }
        for name, value in thresholds.items():
            if not 0.1 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.1 and 1.0")


class ConfigurationManager:
    """Centralized configuration with validation and environment loading."""

    def __init__(self) -> None:
        """Create a configuration manager and load sections."""
        self.dolphin = DolphinConfig()
        self.performance = PerformanceConfig()
        self.alert_thresholds = AlertThresholds()
        self.quality_thresholds = QualityThresholds()

    def require_credentials(self) -> None:
        """Ensure required credentials are present before HF actions.

        HF-dependent operations must have an `HF_TOKEN` configured.
        """
        if not self.dolphin.hf_token:
            raise ValueError("HF_TOKEN is required for Dolphin OCR authentication")

    def validate_all(self) -> None:
        """Enforce credentials and validate all configuration sections."""
        self.require_credentials()
        self.dolphin.validate()
        self.performance.validate()
        self.alert_thresholds.validate()
        self.quality_thresholds.validate()

    def get_environment_summary(self) -> dict[str, Any]:
        """Return a summarized view of effective configuration."""
        return {
            "dolphin_endpoint": self.dolphin.modal_endpoint,
            "timeout_seconds": self.dolphin.timeout_seconds,
            "max_concurrent_requests": (self.performance.max_concurrent_requests),
            "dpi": self.performance.dpi,
            "error_rate_threshold": (self.alert_thresholds.error_rate_threshold),
            "min_quality_score": (self.quality_thresholds.min_overall_quality_score),
            "hf_token_configured": bool(self.dolphin.hf_token),
            "max_retries": self.dolphin.max_retries,
            "batch_size": self.dolphin.batch_size,
            "processing_timeout": self.performance.processing_timeout,
        }
