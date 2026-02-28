from __future__ import annotations

import os
from pathlib import Path

import pytest

from dolphin_ocr.layout import BoundingBox, FontInfo
from services.pdf_document_reconstructor import (
    PDFDocumentReconstructor,
    TranslatedElement,
    TranslatedLayout,
    TranslatedPage,
)

reportlab = pytest.importorskip(
    "reportlab",
    reason="ReportLab required for PDF reconstruction tests",
)


def _write_minimal_pdf_header(tmp_path: Path, name: str = "orig.pdf") -> str:
    """Create a minimal file that satisfies header validation.

    The content is not a valid PDF beyond the header, but our validation only
    checks presence of the %PDF- magic number and existence.
    """
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.7\nminimal")
    return str(p)


def _reconstructor() -> PDFDocumentReconstructor:
    return PDFDocumentReconstructor()


def test_reconstruct_single_line_simple(tmp_path: Path):
    original_path = _write_minimal_pdf_header(tmp_path)
    output_path = str(tmp_path / "out_simple.pdf")

    elem = TranslatedElement(
        original_text="Hello",
        translated_text="Hello",
        adjusted_text=None,
        bbox=BoundingBox(x=72, y=720, width=200, height=40),
        font_info=FontInfo(family="Helvetica", size=12, weight="normal"),
    )
    layout = TranslatedLayout(
        pages=[
            TranslatedPage(
                page_number=1,
                translated_elements=[elem],
                width=612,
                height=792,
            )
        ]
    )

    recon = _reconstructor()
    result = recon.reconstruct_pdf_document(
        translated_layout=layout,
        original_file_path=original_path,
        output_path=output_path,
    )

    assert result.success is True
    assert Path(output_path).exists()
    assert os.path.getsize(output_path) > 0

    # If pypdf is available, verify text extraction and page count
    try:
        from importlib import import_module

        pypdf = import_module("pypdf")
        reader = pypdf.PdfReader(output_path)
        assert len(reader.pages) == 1
        extracted = reader.pages[0].extract_text() or ""
        assert "Hello" in extracted
    except ModuleNotFoundError:
        pass


def test_pypdf_parse_error_emits_warning_but_validation_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    original_path = _write_minimal_pdf_header(tmp_path)
    output_path = str(tmp_path / "out_warning.pdf")

    elem = TranslatedElement(
        original_text="Hi",
        translated_text="Hi",
        adjusted_text=None,
        bbox=BoundingBox(x=50, y=750, width=200, height=20),
        font_info=FontInfo(family="Helvetica", size=12),
    )
    layout = TranslatedLayout(
        pages=[
            TranslatedPage(
                page_number=1,
                translated_elements=[elem],
                width=300,
                height=800,
            )
        ]
    )

    # Create a stub pypdf module whose PdfReader raises a parse-like error
    class _StubErrors:
        class PdfReadError(Exception):
            pass

    class _StubPdfReader:
        def __init__(self, _fh):
            raise _StubErrors.PdfReadError("simulated parse error")

    class _StubPypdf:
        errors = _StubErrors
        PdfReader = _StubPdfReader

    import importlib as _il
    _orig_import_module = _il.import_module

    def _fake_import(name: str, *args, **kwargs):
        if name == "pypdf":
            return _StubPypdf
        return _orig_import_module(name, *args, **kwargs)

    # If pypdf isn't installed, this still works since we intercept import
    monkeypatch.setattr("importlib.import_module", _fake_import)

    recon = _reconstructor()
    from services.pdf_document_reconstructor import PDFEncryptionCheckWarning

    with pytest.warns(PDFEncryptionCheckWarning):
        # Should not raise despite the parse error; just warn and continue
        result = recon.reconstruct_pdf_document(
            translated_layout=layout,
            original_file_path=original_path,
            output_path=output_path,
        )
    assert result.success is True
    assert Path(output_path).exists()


def test_reconstruct_multiline_wrap_and_overflow(tmp_path: Path):
    original_path = _write_minimal_pdf_header(tmp_path)
    output_path = str(tmp_path / "out_wrap.pdf")

    long_text = (
        "This is a considerably longer line that needs wrapping to fit nicely "
        "within the given bounding box width"
    )
    elem = TranslatedElement(
        original_text="Short",
        translated_text=long_text,
        adjusted_text=None,  # force internal wrapping
        bbox=BoundingBox(
            x=72,
            y=500,
            width=120,
            height=36,
        ),  # small height to trigger overflow
        font_info=FontInfo(family="Times", size=12, weight="normal"),
    )
    layout = TranslatedLayout(
        pages=[
            TranslatedPage(
                page_number=1,
                translated_elements=[elem],
                width=400,
                height=600,
            )
        ]
    )

    recon = _reconstructor()
    result = recon.reconstruct_pdf_document(
        translated_layout=layout,
        original_file_path=original_path,
        output_path=output_path,
    )

    assert Path(output_path).exists()
    # Expect an overflow warning due to insufficient height
    assert any("Text overflow" in w for w in result.warnings)


def test_reconstruct_color_and_style_application(tmp_path: Path):
    original_path = _write_minimal_pdf_header(tmp_path)
    output_path = str(tmp_path / "out_style.pdf")

    # Bold-italic Courier with red color
    elem = TranslatedElement(
        original_text="Emphasis",
        translated_text="Emphasis",
        adjusted_text=None,
        bbox=BoundingBox(x=72, y=700, width=200, height=40),
        font_info=FontInfo(
            family="Courier",
            size=14,
            weight="bold",
            style="italic",
            color=(255, 0, 0),
        ),
    )
    layout = TranslatedLayout(
        pages=[TranslatedPage(page_number=1, translated_elements=[elem])]
    )

    recon = _reconstructor()
    result = recon.reconstruct_pdf_document(
        translated_layout=layout,
        original_file_path=original_path,
        output_path=output_path,
    )

    assert result.success is True
    assert Path(output_path).exists()


def test_reconstruct_page_size_inference_from_elements(tmp_path: Path):
    original_path = _write_minimal_pdf_header(tmp_path)
    output_path = str(tmp_path / "out_infer_size.pdf")

    # No explicit page size; element extends to x+width=560, y+height=780
    elem = TranslatedElement(
        original_text="SizeTest",
        translated_text="SizeTest",
        adjusted_text=None,
        bbox=BoundingBox(x=500, y=730, width=60, height=50),
        font_info=FontInfo(family="Helvetica", size=12),
    )
    layout = TranslatedLayout(
        pages=[TranslatedPage(page_number=1, translated_elements=[elem])]
    )

    recon = _reconstructor()
    recon.reconstruct_pdf_document(
        translated_layout=layout,
        original_file_path=original_path,
        output_path=output_path,
    )

    assert Path(output_path).exists()

    try:
        from importlib import import_module

        pypdf = import_module("pypdf")
        reader = pypdf.PdfReader(output_path)
        page = reader.pages[0]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        assert width >= 560 - 1
        assert height >= 780 - 1
    except ModuleNotFoundError:
        pass
