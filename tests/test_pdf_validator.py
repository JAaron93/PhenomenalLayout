from pathlib import Path

import pytest

from tests.helpers import write_minimal_pdf
from utils.pdf_validator import (
    detect_pdf_encryption,
    validate_pdf,
    validate_pdf_extension_and_header,
    validate_pdf_structure,
)


def _write_encrypted_pdf(path: Path) -> None:
    import importlib
    import importlib.util

    spec = importlib.util.find_spec("pypdf")
    if spec is None:  # pragma: no cover - dependency missing
        pytest.skip("pypdf not available")
    mod = importlib.import_module("pypdf")
    writer = mod.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("pwd")
    with path.open("wb") as fh:
        writer.write(fh)


def test_extension_and_header_valid_tmp(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    write_minimal_pdf(pdf)
    res = validate_pdf_extension_and_header(str(pdf))
    assert res.ok is True
    assert res.is_pdf is True
    assert res.issues == []


def test_extension_and_header_invalid_nonpdf(tmp_path: Path) -> None:
    txt = tmp_path / "doc.txt"
    txt.write_text("hello")
    res = validate_pdf_extension_and_header(str(txt))
    assert res.ok is False
    assert any(issue.code == "DOC_INVALID_FORMAT" for issue in res.issues)


def test_detect_encryption_for_encrypted_pdf(tmp_path: Path) -> None:
    enc = tmp_path / "enc.pdf"
    _write_encrypted_pdf(enc)
    res = detect_pdf_encryption(str(enc))
    assert res.is_pdf is True
    assert res.is_encrypted is True
    assert any(issue.code == "DOC_ENCRYPTED_PDF" for issue in res.issues)


def test_validate_pdf_structure_minimal(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    write_minimal_pdf(pdf)
    res = validate_pdf_structure(str(pdf))
    assert res.ok is True
    assert res.is_pdf is True


def test_validate_pdf_end_to_end(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    write_minimal_pdf(pdf)
    res = validate_pdf(str(pdf))
    assert res.ok is True
    assert res.is_pdf is True
    assert res.is_encrypted is False


def test_validate_pdf_nonpdf_file(tmp_path: Path) -> None:
    f = tmp_path / "not.pdf"
    f.write_text("not a pdf")
    res = validate_pdf(str(f))
    assert res.ok is False
    assert any(issue.code == "DOC_INVALID_FORMAT" for issue in res.issues)
