"""Configuration settings for the PDF translator."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GCPSettings:
    """Immutable GCP configuration constants for the batch translation pipeline.

    All monetary values are in USD. All defaults match the Google Cloud pricing
    schedule described in .kiro/specs/gcp-migration/design.md §3.1.
    No secrets or credentials are stored here — those live in BYOKCredentialsManager.
    """

    # Regional endpoint for Cloud Translation v3 and Glossary provisioning
    gcp_location: str = "us-central1"

    # --- Pricing constants ---
    # Document Translation API rate (USD per page)
    doc_translation_price_per_page: float = 0.080
    # GCS Standard Regional Storage (USD per GB per month)
    gcs_standard_storage_per_gb_mo: float = 0.020
    # GCS Archive Storage for long-term retention (USD per GB per month)
    gcs_archive_storage_per_gb_mo: float = 0.0012
    # GCP Always Free tier: 5 GB-months of Standard Storage in US regions
    gcs_always_free_storage_gb: float = 5.0

    # --- Lifecycle policy ---
    # Staged input objects (gs://<bucket>/inputs/...) auto-delete after 7 days
    gcs_staging_expiration_days: int = 7
    gcs_staging_prefix: str = "inputs/"

    # --- LRO polling ---
    # Seconds between LRO status polls during a batch translation job
    batch_poll_interval_sec: int = 10

    # --- Preview / sampling ---
    # Maximum pages permitted in synchronous single-page preview mode
    max_inline_preview_pages: int = 3
    # OCR confidence below this triggers a "please test sample pages" recommendation
    fraktur_confidence_threshold: float = 0.85

    # --- Modal Labs volume ---
    # Persistent volume mount path for user metadata and session recovery data
    modal_volume_path: str = "/data"

    # --- Cost estimator tolerance ---
    # Maximum acceptable deviation between estimate and actual GCP bill (USD)
    cost_estimate_tolerance_usd: float = 5.00

    # --- GCP Glossary quota ---
    # Hard regional limit for Cloud Translation glossaries per project
    gcp_glossary_quota_limit: int = 1000
    # Soft warning threshold (alert when approaching quota)
    gcp_glossary_warning_threshold: int = 900

    @classmethod
    def from_env(cls) -> "GCPSettings":
        """Build a GCPSettings instance overriding defaults from environment variables.

        All GCP constants can be overridden via env vars with the GCP_ prefix.
        No secrets are read here — credentials are exclusively in BYOKCredentialsManager.
        """
        return cls(
            gcp_location=os.getenv("GCP_LOCATION", "us-central1"),
            doc_translation_price_per_page=float(
                os.getenv("GCP_DOC_TRANSLATION_PRICE_PER_PAGE", "0.080")
            ),
            gcs_standard_storage_per_gb_mo=float(
                os.getenv("GCS_STANDARD_STORAGE_PER_GB_MO", "0.020")
            ),
            gcs_archive_storage_per_gb_mo=float(
                os.getenv("GCS_ARCHIVE_STORAGE_PER_GB_MO", "0.0012")
            ),
            gcs_always_free_storage_gb=float(
                os.getenv("GCS_ALWAYS_FREE_STORAGE_GB", "5.0")
            ),
            gcs_staging_expiration_days=int(
                os.getenv("GCS_STAGING_EXPIRATION_DAYS", "7")
            ),
            gcs_staging_prefix=os.getenv("GCS_STAGING_PREFIX", "inputs/"),
            batch_poll_interval_sec=int(os.getenv("BATCH_POLL_INTERVAL_SEC", "10")),
            max_inline_preview_pages=int(os.getenv("MAX_INLINE_PREVIEW_PAGES", "3")),
            fraktur_confidence_threshold=float(
                os.getenv("FRAKTUR_CONFIDENCE_THRESHOLD", "0.85")
            ),
            modal_volume_path=os.getenv("MODAL_VOLUME_PATH", "/data"),
            cost_estimate_tolerance_usd=float(
                os.getenv("COST_ESTIMATE_TOLERANCE_USD", "5.00")
            ),
        )


# Module-level singleton — import this rather than Settings() for GCP constants
gcp_settings: GCPSettings = GCPSettings.from_env()



# Valid ISO 639-1 language codes
VALID_LANGUAGE_CODES: set[str] = {
    "AA",
    "AB",
    "AE",
    "AF",
    "AK",
    "AM",
    "AN",
    "AR",
    "AS",
    "AV",
    "AY",
    "AZ",
    "BA",
    "BE",
    "BG",
    "BH",
    "BI",
    "BM",
    "BN",
    "BO",
    "BR",
    "BS",
    "CA",
    "CE",
    "CH",
    "CO",
    "CR",
    "CS",
    "CU",
    "CV",
    "CY",
    "DA",
    "DE",
    "DV",
    "DZ",
    "EE",
    "EL",
    "EN",
    "EO",
    "ES",
    "ET",
    "EU",
    "FA",
    "FF",
    "FI",
    "FJ",
    "FO",
    "FR",
    "FY",
    "GA",
    "GD",
    "GL",
    "GN",
    "GU",
    "GV",
    "HA",
    "HE",
    "HI",
    "HO",
    "HR",
    "HT",
    "HU",
    "HY",
    "HZ",
    "IA",
    "ID",
    "IE",
    "IG",
    "II",
    "IK",
    "IO",
    "IS",
    "IT",
    "IU",
    "JA",
    "JV",
    "KA",
    "KG",
    "KI",
    "KJ",
    "KK",
    "KL",
    "KM",
    "KN",
    "KO",
    "KR",
    "KS",
    "KU",
    "KV",
    "KW",
    "KY",
    "LA",
    "LB",
    "LG",
    "LI",
    "LN",
    "LO",
    "LT",
    "LU",
    "LV",
    "MG",
    "MH",
    "MI",
    "MK",
    "ML",
    "MN",
    "MR",
    "MS",
    "MT",
    "MY",
    "NA",
    "NB",
    "ND",
    "NE",
    "NG",
    "NL",
    "NN",
    "NO",
    "NR",
    "NV",
    "NY",
    "OC",
    "OJ",
    "OM",
    "OR",
    "OS",
    "PA",
    "PI",
    "PL",
    "PS",
    "PT",
    "QU",
    "RM",
    "RN",
    "RO",
    "RU",
    "RW",
    "SA",
    "SC",
    "SD",
    "SE",
    "SG",
    "SI",
    "SK",
    "SL",
    "SM",
    "SN",
    "SO",
    "SQ",
    "SR",
    "SS",
    "ST",
    "SU",
    "SV",
    "SW",
    "TA",
    "TE",
    "TG",
    "TH",
    "TI",
    "TK",
    "TL",
    "TN",
    "TO",
    "TR",
    "TS",
    "TT",
    "TW",
    "TY",
    "UG",
    "UK",
    "UR",
    "UZ",
    "VE",
    "VI",
    "VO",
    "WA",
    "WO",
    "XH",
    "YI",
    "YO",
    "ZA",
    "ZH",
    "ZU",
}


def _parse_bool_env(env_var: str, default: str = "false") -> bool:
    """Parse boolean environment variable with error handling."""
    try:
        value: str = os.getenv(env_var, default).lower().strip()
        if value in ("true", "1", "yes", "on"):
            return True
        elif value in ("false", "0", "no", "off"):
            return False
        else:
            logger.error(
                "Invalid boolean value '%s' for %s. Valid values: true/false, 1/0, yes/no, on/off",
                value,
                env_var,
            )
            raise ValueError(f"Invalid boolean value for {env_var}: {value}")
    except AttributeError as e:
        logger.exception("Error parsing boolean environment variable %s", env_var)
        raise ValueError(f"Error parsing {env_var}: {e}") from e


def _parse_int_env(
    env_var: str,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Parse integer environment variable with error handling and value clamping.

    Args:
        env_var: Environment variable name to parse
        default: Default value to return on error
        min_value: Minimum allowed value (optional)
        max_value: Maximum allowed value (optional)

    Returns:
        int: Parsed and validated integer value
    """
    try:
        value_str: str = os.getenv(env_var, str(default))
        result: int = int(value_str)

        # Apply clamping if specified
        if min_value is not None and result < min_value:
            logger.warning(
                "Environment variable %s value %d is below minimum %d, clamping to %d",
                env_var,
                result,
                min_value,
                min_value,
            )
            return min_value

        if max_value is not None and result > max_value:
            logger.warning(
                "Environment variable %s value %d is above maximum %d, clamping to %d",
                env_var,
                result,
                max_value,
                max_value,
            )
            return max_value

        return result

    except (ValueError, TypeError) as e:
        logger.error(
            "Invalid integer value '%s' for %s, using default %d: %s",
            os.getenv(env_var, str(default)),
            env_var,
            default,
            str(e),
        )
        return default


class Settings:
    """Application settings with environment variable configuration."""

    # Translation API settings - Only Lingo.dev
    LINGO_API_KEY: str | None = os.getenv("LINGO_API_KEY")

    # Server configuration
    PORT: int = _parse_int_env("PORT", default=7860, min_value=1, max_value=65535)
    DEBUG: bool = _parse_bool_env("DEBUG", "false")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # File handling
    MAX_FILE_SIZE_MB: int = _parse_int_env("MAX_FILE_SIZE_MB", default=10, min_value=1)
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", "downloads")
    TEMP_DIR: str = os.getenv("TEMP_DIR", "temp")
    IMAGE_CACHE_DIR: str = os.getenv("IMAGE_CACHE_DIR", "temp/images")

    # PDF processing
    PDF_DPI: int = _parse_int_env("PDF_DPI", default=300, min_value=72, max_value=600)
    PRESERVE_IMAGES: bool = _parse_bool_env("PRESERVE_IMAGES", "true")
    MEMORY_THRESHOLD: int = _parse_int_env(
        "MEMORY_THRESHOLD", default=500, min_value=100
    )  # MB

    # Translation settings
    SOURCE_LANGUAGE: str = "DE"
    TARGET_LANGUAGE: str = "EN"
    TRANSLATION_DELAY: float = float(os.getenv("TRANSLATION_DELAY", "0.1"))
    # Maximum number of concurrent translation tasks.
    # Environment variable: TRANSLATION_CONCURRENCY_LIMIT
    # Default: 8 (must be >= 1)
    TRANSLATION_CONCURRENCY_LIMIT: int = _parse_int_env(
        "TRANSLATION_CONCURRENCY_LIMIT", default=8, min_value=1
    )

    # Dolphin OCR service configuration
    # Choose between 'modal' (Modal Labs cloud) or 'local' (self-hosted) endpoint
    # Environment variable: DOLPHIN_ENDPOINT_TYPE
    DOLPHIN_ENDPOINT_TYPE: str = os.getenv("DOLPHIN_ENDPOINT_TYPE", "modal")
    # Custom local endpoint URL (used when DOLPHIN_ENDPOINT_TYPE is 'local')
    # Environment variable: DOLPHIN_LOCAL_ENDPOINT
    DOLPHIN_LOCAL_ENDPOINT: str = os.getenv(
        "DOLPHIN_LOCAL_ENDPOINT", "http://localhost:8501/layout"
    )
    # Timeout for Dolphin service requests in seconds
    # Environment variable: DOLPHIN_TIMEOUT_SECONDS
    DOLPHIN_TIMEOUT_SECONDS: int = _parse_int_env(
        "DOLPHIN_TIMEOUT_SECONDS", default=300, min_value=1
    )

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "app.log")


    def __init__(self) -> None:
        """Initialize settings and create required directories."""
        # Create required directories with proper error handling
        directories_to_create: list[str] = [
            self.UPLOAD_DIR,
            self.DOWNLOAD_DIR,
            self.TEMP_DIR,
            self.IMAGE_CACHE_DIR,
        ]
        for directory in directories_to_create:
            # Normalize path to absolute path
            normalized_path: str = os.path.abspath(directory)

            try:
                os.makedirs(normalized_path, exist_ok=True)
                logger.debug(
                    "Successfully created/verified directory: %s", normalized_path
                )
            except PermissionError as e:
                logger.error(
                    "Permission denied when creating directory '%s': %s. "
                    "Check file system permissions for the application.",
                    normalized_path,
                    e,
                )
                raise
            except OSError as e:
                logger.error(
                    "OS error when creating directory '%s': %s. "
                    "Check path validity and available disk space.",
                    normalized_path,
                    e,
                )
                raise

        # Post-initialization setup
        self.__post_init__()

    def __post_init__(self) -> None:
        """Post-initialization to handle auto-generated settings."""
        # Auto-generate SECRET_KEY for DEBUG mode if not provided
        if self.DEBUG and not self.SECRET_KEY:
            self.SECRET_KEY = secrets.token_urlsafe(32)
            logger.info("Auto-generated SECRET_KEY for DEBUG mode")
