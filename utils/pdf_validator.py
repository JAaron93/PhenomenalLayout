# pyright: reportMissingImports=false
"""Basic PDF validation utilities.

Provides lightweight checks for:
- File extension and header validation
- Encryption detection using pypdf
- Obvious structure corruption via header/xref/EOF heuristics

Returns structured results with standardized document error codes
(``DOC_INVALID_FORMAT``, ``DOC_ENCRYPTED_PDF``).
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

from utils.document_errors import (
    DOC_ENCRYPTED_PDF,
    DOC_INVALID_FORMAT,
    get_error_message,
)

# Error codes from utils.document_errors
ERR_INVALID_FORMAT = DOC_INVALID_FORMAT
ERR_ENCRYPTED_PDF = DOC_ENCRYPTED_PDF

# Indirect module name to prevent static import warnings
_PYPDF_MOD = "pypdf"


def _get_pdf_reader():
    """Return (PdfReader class, error message) via dynamic import."""
    try:
        spec = importlib.util.find_spec(_PYPDF_MOD)
        if spec is None:
            return None, "pypdf not installed"
        mod = importlib.import_module(_PYPDF_MOD)
        reader = getattr(mod, "PdfReader", None)
        if reader is None:
            return None, "pypdf.PdfReader not available"
        return reader, None
    except (ImportError, AttributeError) as exc:
        return None, str(exc)


@dataclass(frozen=True)
class ValidationIssue:
    """Represents a single validation issue with a standardized code."""

    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Aggregate result returned by PDF validation helpers."""

    ok: bool
    is_pdf: bool
    is_encrypted: bool
    issues: list[ValidationIssue] = field(default_factory=list)


def _has_pdf_extension(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def _has_pdf_header(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            head = fh.read(5)
        return head == b"%PDF-"
    except OSError:
        return False


def validate_pdf_extension_and_header(file_path: str) -> ValidationResult:
    """Validate extension and header."""
    p = Path(file_path)
    issues: list[ValidationIssue] = []

    is_pdf_ext = _has_pdf_extension(p)
    has_header = _has_pdf_header(p)
    looks_like_pdf = is_pdf_ext and has_header

    if not looks_like_pdf:
        issues.append(
            ValidationIssue(
                code=ERR_INVALID_FORMAT,
                message=get_error_message(ERR_INVALID_FORMAT),
            )
        )

    return ValidationResult(
        ok=looks_like_pdf,
        is_pdf=looks_like_pdf,
        is_encrypted=False,
        issues=issues,
    )


def detect_pdf_encryption(file_path: str) -> ValidationResult:
    """Detect whether a PDF is encrypted."""
    pdf_reader, err = _get_pdf_reader()
    if pdf_reader is None:
        return ValidationResult(
            ok=False,
            is_pdf=False,
            is_encrypted=False,
            issues=[
                ValidationIssue(
                    code=ERR_INVALID_FORMAT,
                    message=get_error_message(ERR_INVALID_FORMAT)
                    + (f" ({err})" if err else ""),
                )
            ],
        )

    p = Path(file_path)
    issues: list[ValidationIssue] = []

    try:
        reader = pdf_reader(str(p))
        encrypted = getattr(reader, "is_encrypted", False)
    except (OSError, ValueError, RuntimeError):
        # If we cannot open the file to check, treat as invalid format
        issues.append(
            ValidationIssue(
                code=ERR_INVALID_FORMAT,
                message=get_error_message(ERR_INVALID_FORMAT),
            )
        )
        return ValidationResult(
            ok=False, is_pdf=False, is_encrypted=False, issues=issues
        )

    if encrypted:
        issues.append(
            ValidationIssue(
                code=ERR_ENCRYPTED_PDF,
                message=get_error_message(ERR_ENCRYPTED_PDF),
            )
        )

    return ValidationResult(
        ok=not encrypted,
        is_pdf=True,
        is_encrypted=encrypted,
        issues=issues,
    )


def validate_pdf_structure(
    file_path: str, *, skip_header_check: bool = False
) -> ValidationResult:
    """Perform basic structure checks for obvious corruption.

    Streams the file to avoid loading large PDFs into memory.

    Parameters:
        skip_header_check: If True, do not re-read the first 5 bytes to check
            the %PDF- header (useful when the caller already validated it).
    """
    p = Path(file_path)
    issues: list[ValidationIssue] = []

    try:
        with p.open("rb") as fh:
            # Header check (optional)
            if not skip_header_check:
                head = fh.read(5)
                if head != b"%PDF-":
                    issues.append(
                        ValidationIssue(
                            code=ERR_INVALID_FORMAT,
                            message=get_error_message(ERR_INVALID_FORMAT),
                        )
                    )
            else:
                # If skipping header check, seek back to start for consistent
                # subsequent reads
                fh.seek(0)

            # Check for %%EOF marker (PDFs can have multiple EOF markers)
            try:
                fh.seek(0, 2)
                size = fh.tell()
                tail_len = 2048 if size > 2048 else size
                fh.seek(size - tail_len, 0)
                tail = fh.read(tail_len)
                # More lenient check - just ensure EOF exists somewhere
                if b"%%EOF" not in tail:
                    # For linearized PDFs, EOF might be elsewhere
                    fh.seek(0)
                    found_eof = False
                    while True:
                        chunk = fh.read(64 * 1024)
                        if not chunk:
                            break
                        if b"%%EOF" in chunk:
                            found_eof = True
                            break
                    if not found_eof:
                        issues.append(
                            ValidationIssue(
                                code=ERR_INVALID_FORMAT,
                                message=get_error_message(ERR_INVALID_FORMAT),
                            )
                        )
            except OSError:
                issues.append(
                    ValidationIssue(
                        code=ERR_INVALID_FORMAT,
                        message=get_error_message(ERR_INVALID_FORMAT),
                    )
                )

            # Scan for 'xref' in chunks
            fh.seek(0)
            chunk_size = 64 * 1024
            found_xref = False
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                if b"xref" in chunk:
                    found_xref = True
                    break
            if not found_xref:
                issues.append(
                    ValidationIssue(
                        code=ERR_INVALID_FORMAT,
                        message=get_error_message(ERR_INVALID_FORMAT),
                    )
                )
    except OSError:
        issues.append(
            ValidationIssue(
                code=ERR_INVALID_FORMAT,
                message=get_error_message(ERR_INVALID_FORMAT),
            )
        )
        return ValidationResult(
            ok=False, is_pdf=False, is_encrypted=False, issues=issues
        )

    # Try to parse with pypdf as a final sanity check (use file path)
    reader_cls, err2 = _get_pdf_reader()
    try:
        if reader_cls is None:  # pragma: no cover - treat as invalid
            raise ImportError(err2 or "pypdf not available")
        _ = reader_cls(str(p))
    except (ImportError, OSError, ValueError, RuntimeError):
        issues.append(
            ValidationIssue(
                code=ERR_INVALID_FORMAT,
                message=get_error_message(ERR_INVALID_FORMAT),
            )
        )

    ok = len(issues) == 0
    return ValidationResult(ok=ok, is_pdf=True, is_encrypted=False, issues=issues)


def validate_pdf(file_path: str) -> ValidationResult:
    """Run extension/header, encryption, and structure validation."""
    initial = validate_pdf_extension_and_header(file_path)
    issues: list[ValidationIssue] = list(initial.issues)
    is_pdf = initial.is_pdf
    is_encrypted = False

    if not initial.ok:
        return ValidationResult(
            ok=False, is_pdf=is_pdf, is_encrypted=False, issues=issues
        )

    enc = detect_pdf_encryption(file_path)
    issues.extend(enc.issues)
    is_encrypted = enc.is_encrypted
    if not enc.ok:
        return ValidationResult(
            ok=False, is_pdf=True, is_encrypted=is_encrypted, issues=issues
        )

    struct = validate_pdf_structure(file_path, skip_header_check=True)
    issues.extend(struct.issues)
    ok = enc.ok and struct.ok
    return ValidationResult(
        ok=ok, is_pdf=True, is_encrypted=is_encrypted, issues=issues
    )
