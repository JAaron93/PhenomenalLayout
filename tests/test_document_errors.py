"""Tests for standardized document-processing error codes."""

from utils.document_errors import (
    CODE_TO_MESSAGE,
    DOC_ENCRYPTED_PDF,
    DOC_INVALID_FORMAT,
    DOC_SERVICE_UNAVAILABLE,
    GCP_CREDENTIALS_REQUIRED,
    get_error_message,
)


def test_code_to_message_contains_exactly_the_registered_codes() -> None:
    assert set(CODE_TO_MESSAGE) == {
        DOC_INVALID_FORMAT,
        DOC_ENCRYPTED_PDF,
        DOC_SERVICE_UNAVAILABLE,
        GCP_CREDENTIALS_REQUIRED,
    }


def test_invalid_format_message() -> None:
    assert CODE_TO_MESSAGE[DOC_INVALID_FORMAT] == (
        "Invalid document format - Unsupported file type"
    )


def test_encrypted_pdf_message() -> None:
    assert CODE_TO_MESSAGE[DOC_ENCRYPTED_PDF] == (
        "Encrypted PDFs not supported - please provide unlocked PDF"
    )


def test_service_unavailable_message() -> None:
    assert CODE_TO_MESSAGE[DOC_SERVICE_UNAVAILABLE] == (
        "Service unavailable - document processing service down"
    )


def test_get_error_message_override_passthrough() -> None:
    assert get_error_message(DOC_INVALID_FORMAT, "custom message") == "custom message"


def test_get_error_message_known_code() -> None:
    assert get_error_message(DOC_ENCRYPTED_PDF) == CODE_TO_MESSAGE[DOC_ENCRYPTED_PDF]


def test_get_error_message_unknown_code_falls_back_to_code() -> None:
    assert get_error_message("DOC_999") == "DOC_999"


def test_gcp_credentials_required_message_guides_onboarding() -> None:
    """The 503 code maps to actionable BYOK onboarding guidance."""
    message = get_error_message(GCP_CREDENTIALS_REQUIRED)
    assert "Google Cloud" in message
    assert "Service Account" in message or "service account" in message
    assert "/api/v1/byok/credentials" in message
