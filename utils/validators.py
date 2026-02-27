"""Input validation utilities."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from utils.language_utils import DEFAULT_SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)


class FileValidator:
    """Validates file uploads and inputs."""

    def __init__(self) -> None:
        """Initialize validator with file size limits and allowed formats.

        Attributes:
            max_file_size: Maximum allowed file size in bytes, derived from
                         Settings.MAX_FILE_SIZE_MB converted to bytes.
            allowed_extensions: Set of permitted file extensions, currently
                              restricted to PDF files only.
            allowed_mimetypes: Set of permitted MIME types for file
                             validation, currently supporting only PDF files.
        """
        from config.settings import Settings

        settings = Settings()
        self.max_file_size: int = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        # Only PDF files are supported
        self.allowed_extensions: set[str] = {".pdf"}
        self.allowed_mimetypes: set[str] = {
            "application/pdf",
        }

    def validate_file(self, filename: str, file_size: int) -> dict[str, Any]:
        """Validate file upload against size and extension constraints.

        Args:
            filename: Name of the file to validate, including extension.
            file_size: Size of the file in bytes to check against limits.

        Returns:
            Dictionary containing validation results with keys:
            - "valid" (bool): True if file passes all validation checks,
                            False otherwise.
            - "error" (str | None): Error message describing validation
                                  failure, or None if validation succeeds.
        """
        try:
            # Check filename
            if not filename:
                return {"valid": False, "error": "No filename provided"}

            # Check file extension
            file_ext = Path(filename).suffix.lower()
            if file_ext not in self.allowed_extensions:
                return {
                    "valid": False,
                    "error": f"Unsupported file type. Allowed: {', '.join(self.allowed_extensions)}",
                }

            # Check file size
            if file_size > self.max_file_size:
                max_size_mb = self.max_file_size / (1024 * 1024)
                return {
                    "valid": False,
                    "error": f"File too large. Maximum size: {max_size_mb}MB",
                }

            if file_size == 0:
                return {"valid": False, "error": "File is empty"}

            return {"valid": True}

        except Exception as e:
            logger.error(f"File validation error: {e}")
            return {"valid": False, "error": f"Validation error: {e!s}"}

    def validate_upload_file(self, upload_file: UploadFile) -> dict[str, Any]:
        """Validate FastAPI UploadFile against content type and size limits.

        FastAPI's UploadFile wraps SpooledTemporaryFile, providing file-like
        operations. This function determines file size using seek/tell
        operations and preserves the original file pointer position after
        validation.

        Args:
            upload_file: FastAPI UploadFile instance wrapping uploaded
                       file data.

        Returns:
            Dictionary containing validation results with keys:
            - "valid" (bool): True if file passes all validation checks,
                            False otherwise.
            - "error" (str | None): Error message describing validation
                                  failure, or None if validation succeeds.

        Note:
            File pointer position is preserved during validation. The
            function uses seek(0, 2) to determine file size, then restores
            the original position with seek(current_pos) to avoid affecting
            subsequent reads.
        """
        try:
            # Check content type
            if upload_file.content_type not in self.allowed_mimetypes:
                return {
                    "valid": False,
                    "error": f"Unsupported content type: {upload_file.content_type}",
                }

            # Get file size with safety check
            current_pos = upload_file.file.tell()
            upload_file.file.seek(0, 2)
            file_size = upload_file.file.tell()

            # Safety check before seeking back
            if file_size > self.max_file_size:
                return {
                    "valid": False,
                    "error": f"File too large. Maximum size: {self.max_file_size / (1024 * 1024)}MB",
                }

            upload_file.file.seek(current_pos)  # Reset to original position

            # Validate using standard method
            return self.validate_file(upload_file.filename, file_size)

        except Exception as e:
            logger.error(f"Upload file validation error: {e}")
            return {"valid": False, "error": f"Validation error: {e!s}"}

    def _load_language_config(self) -> dict[str, Any]:
        """Load language configuration from external JSON file.

        Falls back to hard-coded defaults if the JSON file cannot be read,
        ensuring graceful degradation when configuration is unavailable.
        """
        try:
            config_path = Path(__file__).parent.parent / "config" / "languages.json"
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load language config: {e}")
            # Fallback to default values if config loading fails
            return {
                "supported_languages": DEFAULT_SUPPORTED_LANGUAGES,
                "supported_formats": ["PDF"],
            }

    def validate_language(self, language: str) -> dict[str, Any]:
        """Validate language selection with case-insensitive matching.

        Args:
            language: Language name to validate (case-insensitive).

        Returns:
            Dictionary containing validation results with keys:
            - "valid" (bool): True if language is supported, False otherwise.
            - "error" (str | None): Error message if validation fails,
                                  None if validation succeeds.

        Note:
            Language matching is case-insensitive. Input is normalized to
            title case before comparison (e.g., "english" -> "English").
        """
        config = self._load_language_config()
        supported_languages = config.get("supported_languages", [])

        if not language:
            return {"valid": False, "error": "No language selected"}

        # Normalize input to title case for case-insensitive comparison
        normalized_language = language.strip().title()

        if normalized_language not in supported_languages:
            return {
                "valid": False,
                "error": f"Unsupported language. Supported: {', '.join(supported_languages)}",
            }

        return {"valid": True}

    def validate_output_format(self, format_type: str) -> dict[str, Any]:
        """Validate output format selection with case-insensitive matching.

        Args:
            format_type: Output format to validate (case-insensitive).
                       Callers can pass the format string in any casing
                       (e.g., "pdf", "PDF", "Pdf").

        Returns:
            Dictionary containing validation results with keys:
            - "valid" (bool): True if format is supported, False otherwise.
            - "error" (str | None): Error message if validation fails,
                                  None if validation succeeds.

        Note:
            Format matching is case-insensitive. Input is converted to
            uppercase internally for comparison against supported formats.
        """
        config = self._load_language_config()
        supported_formats = config.get("supported_formats", ["PDF"])

        if not format_type:
            return {"valid": False, "error": "No output format selected"}

        if format_type.upper() not in supported_formats:
            return {
                "valid": False,
                "error": f"Unsupported format. Supported: {', '.join(supported_formats)}",
            }

        return {"valid": True}
