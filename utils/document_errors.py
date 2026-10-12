"""Standardized document-processing error codes.

These codes are returned by the API validation endpoints and mapped to
friendly messages by the Gradio UI.
"""
from __future__ import annotations

DOC_INVALID_FORMAT = "DOC_INVALID_FORMAT"
DOC_ENCRYPTED_PDF = "DOC_ENCRYPTED_PDF"
DOC_SERVICE_UNAVAILABLE = "DOC_SERVICE_UNAVAILABLE"

# Canonical mapping of error codes to default messages.
CODE_TO_MESSAGE: dict[str, str] = {
    DOC_INVALID_FORMAT: "Invalid document format - Unsupported file type",
    DOC_ENCRYPTED_PDF: "Encrypted PDFs not supported - please provide unlocked PDF",
    DOC_SERVICE_UNAVAILABLE: "Service unavailable - document processing service down",
}


def get_error_message(code: str, override: str | None = None) -> str:
    """Return the message for an error code, allowing optional override."""
    if override is not None:
        return override
    return CODE_TO_MESSAGE.get(code, code)
