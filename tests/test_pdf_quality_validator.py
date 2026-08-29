from __future__ import annotations

import types
from pathlib import Path

import pytest

from services.pdf_quality_validator import PDFQualityValidator


def _make_module(**attrs):
    mod = types.SimpleNamespace()
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def test_extract_text_hybrid_pypdf_only(monkeypatch: pytest.MonkeyPatch):
    class _FakePage:
        def __init__(self, text: str) -> None:
            self._t = text

        def extract_text(self, _extraction_mode: str | None = None) -> str:
            return self._t

    class _FakeReader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePage("A"), _FakePage("B")]

    fake_pypdf = _make_module(PdfReader=_FakeReader)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    v = PDFQualityValidator()
    res = v.extract_text_hybrid("dummy.pdf")
    assert res.text_per_page == ["A", "B"]
    assert res.used_ocr_pages == []
    assert not any("pypdf open failed" in w for w in res.warnings)


def test_extract_text_hybrid_pdfminer_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakePage:
        def extract_text(self, _extraction_mode: str | None = None) -> str:
            return ""  # force missing -> use pdfminer

    class _FakeReader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePage(), _FakePage()]

    def _extract_text(_pdf_path: str, page_numbers=None) -> str:
        # Return one chunk per page separated by form feed
        return "X\x0cY"

    fake_pypdf = _make_module(PdfReader=_FakeReader)
    fake_pdfminer_high = _make_module(extract_text=_extract_text)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        if name == "pdfminer.high_level":
            return fake_pdfminer_high
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    v = PDFQualityValidator()
    res = v.extract_text_hybrid("dummy.pdf")
    assert res.text_per_page == ["X", "Y"]
    assert "pdfminer:2" in res.extractor_summary
    assert res.used_ocr_pages == []


def test_extract_text_hybrid_ocr_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    # pypdf returns no text
    class _FakePage:
        def extract_text(self, _extraction_mode: str | None = None) -> str:
            return ""

    class _FakeReader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePage(), _FakePage()]

    # pdfminer returns empty -> force OCR
    def _pdfminer_extract(_pdf_path: str, page_numbers=None) -> str:
        return ""

    class _Img:
        def __init__(self, idx: int) -> None:
            self.idx = idx

    def _convert_from_path(
        _pdf_path: str = "",
        _dpi: int = 72,
        first_page: int = 1,
        last_page: int = 1,
        _poppler_path=None,
        **_kwargs,
    ) -> list[_Img]:
        count = (last_page - first_page) + 1
        return [_Img(i) for i in range(count)]

    def _image_to_string(img: _Img, lang: str = "eng", timeout: float = 10.0, **_kwargs) -> str:
        return f"OCR{img.idx + 1}"

    fake_pypdf = _make_module(PdfReader=_FakeReader)
    fake_pdfminer_high = _make_module(extract_text=_pdfminer_extract)
    fake_pdf2image = _make_module(convert_from_path=_convert_from_path)
    fake_pytesseract = _make_module(image_to_string=_image_to_string)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        if name == "pdfminer.high_level":
            return fake_pdfminer_high
        if name == "pdf2image":
            return fake_pdf2image
        if name == "pytesseract":
            return fake_pytesseract
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    # Provide an existing file path to avoid open() failures
    pdf_path = tmp_path / "a.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    v = PDFQualityValidator()
    res = v.extract_text_hybrid(str(pdf_path))
    assert res.text_per_page == ["OCR1", "OCR2"]
    assert res.used_ocr_pages == [1, 2]


def test_compute_text_accuracy_basic():
    v = PDFQualityValidator()
    ok_case = v.compute_text_accuracy("abcd", "abcdefgh")
    assert ok_case["ok"] is True
    assert 1.9 <= ok_case["ratio"] <= 2.1

    bad_case = v.compute_text_accuracy("a", "aaa")
    assert bad_case["ok"] is False


def test_compare_layout_hashes_uses_length_similarity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    a = tmp_path / "orig.pdf"
    b = tmp_path / "recon.pdf"
    a.write_bytes(b"%PDF-1.4\n")
    b.write_bytes(b"%PDF-1.4\n")

    def _fake_direct(_self, pdf_path: str) -> str:
        # lengths 4 vs 2 -> score = 1 - (2/4) = 0.5
        return "XXXX" if pdf_path.endswith("orig.pdf") else "XX"

    monkeypatch.setattr(
        PDFQualityValidator,
        "_extract_text_direct_only",
        _fake_direct,
    )

    v = PDFQualityValidator()
    report = v.compare_layout_hashes(str(a), str(b))
    assert 0.49 <= float(report["score"]) <= 0.51
    assert report["a_len"] == 4 and report["b_len"] == 2


def test_graceful_when_no_engines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    # No pypdf and no pdfminer available
    def _import_module(_name: str):
        raise ModuleNotFoundError

    monkeypatch.setattr("importlib.import_module", _import_module)

    path = tmp_path / "x.pdf"
    path.write_bytes(b"%PDF-1.4\n")

    v = PDFQualityValidator()
    res = v.extract_text_hybrid(str(path))
    assert res.text_per_page == []
    assert res.extractor_summary == "none"
    assert len(res.warnings) >= 1


def test_direct_only_pdfminer_tuple_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    # Force pypdf to yield empty text so direct-only falls back to pdfminer
    class _Page:
        def extract_text(self, _extraction_mode: str | None = None) -> str:
            return ""

    class _Reader:
        def __init__(self, _path: str) -> None:
            self.pages = [_Page(), _Page()]

    fake_pypdf = _make_module(PdfReader=_Reader)

    from typing import ClassVar

    class _PDFMinerHigh:
        calls: ClassVar[dict[str, int]] = {"list": 0, "tuple": 0}

        @staticmethod
        def extract_text(_pdf_path: str, page_numbers=None):
            # First call with list should raise TypeError
            if isinstance(page_numbers, list):
                _PDFMinerHigh.calls["list"] += 1
                raise TypeError("page_numbers must be tuple")
            _PDFMinerHigh.calls["tuple"] += 1
            return "A\x0cB"

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        if name == "pdfminer.high_level":
            return _PDFMinerHigh
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    v = PDFQualityValidator()
    # Exercise via public method which calls direct-only internally
    report = v.compare_layout_hashes(str(p), str(p))
    score = float(report["score"])
    assert 0.0 <= score <= 1.0
    assert _PDFMinerHigh.calls["list"] >= 1
    assert _PDFMinerHigh.calls["tuple"] >= 1


def test_warning_counts_not_affected_by_truncation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    # Simulate two distinct pypdf per-page failures; then make truncation
    # collapse both to the same short string so counts must remain distinct.
    class _BadPage:
        def extract_text(self, _extraction_mode: str | None = None) -> str:
            # Raise on both attempts to trigger outer except per page
            raise RuntimeError("boom")

    class _Reader:
        def __init__(self, _path: str) -> None:
            self.pages = [_BadPage(), _BadPage()]

    fake_pypdf = _make_module(PdfReader=_Reader)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        # Make other imports fail so we do not add extra long warnings
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    # Truncate aggressively so different warnings collide visually
    def _short_truncate(_self, text: str, _limit: int = 200) -> str:
        return "pypdf" if text.startswith("pypdf") else text

    monkeypatch.setattr(PDFQualityValidator, "_truncate", _short_truncate)

    p = tmp_path / "v.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    v = PDFQualityValidator()
    res = v.extract_text_hybrid(str(p))

    # Truncated warnings all look the same
    assert res.warnings.count("pypdf") >= 2
    # But counts are computed from full messages before truncation
    keys = [k for k in res.warning_counts if k.startswith("pypdf extract page ")]
    assert len(keys) == 2
    for k in keys:
        assert res.warning_counts[k] == 1


def test_compare_layout_hashes_page_normalized_vs_raw(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    a = tmp_path / "orig.pdf"
    b = tmp_path / "recon.pdf"
    a.write_bytes(b"%PDF-1.4\n")
    b.write_bytes(b"%PDF-1.4\n")

    def _fake_direct(_self, pdf_path: str) -> str:
        return ("A" * 1000) if pdf_path.endswith("orig.pdf") else ("B" * 500)

    monkeypatch.setattr(
        PDFQualityValidator,
        "_extract_text_direct_only",
        _fake_direct,
    )

    v = PDFQualityValidator()
    raw = v.compare_layout_hashes(str(a), str(b))
    norm = v.compare_layout_hashes(
        str(a),
        str(b),
        page_normalize=True,
        pages_a=10,
        pages_b=5,
    )

    assert 0.0 <= float(raw["score"]) < 1.0
    assert float(norm["score"]) >= 0.99
    assert norm["used_normalization"] is True
    assert norm["pages_a"] == 10 and norm["pages_b"] == 5


def test_compare_layout_hashes_max_length_ratio_clamps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    a = tmp_path / "orig.pdf"
    b = tmp_path / "recon.pdf"
    a.write_bytes(b"%PDF-1.4\n")
    b.write_bytes(b"%PDF-1.4\n")

    def _fake_direct(_self, pdf_path: str) -> str:
        return ("A" * 10000) if pdf_path.endswith("orig.pdf") else ("B" * 100)

    monkeypatch.setattr(
        PDFQualityValidator,
        "_extract_text_direct_only",
        _fake_direct,
    )

    v = PDFQualityValidator()
    raw = v.compare_layout_hashes(str(a), str(b))
    clamped = v.compare_layout_hashes(str(a), str(b), max_length_ratio=10.0)

    assert float(clamped["score"]) >= float(raw["score"])
    assert clamped["used_normalization"] is False
    assert clamped["pages_a"] is None and clamped["pages_b"] is None
    assert float(clamped["max_length_ratio"]) == 10.0


def test_compare_layout_hashes_page_normalize_derives_pages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    a = tmp_path / "orig.pdf"
    b = tmp_path / "recon.pdf"
    a.write_bytes(b"%PDF-1.4\n")
    b.write_bytes(b"%PDF-1.4\n")

    def _fake_direct(_self, pdf_path: str) -> str:
        return ("A" * 1000) if pdf_path.endswith("orig.pdf") else ("B" * 500)

    class _FakePdfReader:
        def __init__(self, pdf_path: str) -> None:
            # 10 pages for orig, 5 for recon
            n = 10 if pdf_path.endswith("orig.pdf") else 5
            self.pages = [object()] * n

    fake_pypdf = _make_module(PdfReader=_FakePdfReader)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        PDFQualityValidator,
        "_extract_text_direct_only",
        _fake_direct,
    )
    monkeypatch.setattr("importlib.import_module", _import_module)

    v = PDFQualityValidator()
    report = v.compare_layout_hashes(str(a), str(b), page_normalize=True)
    assert report["used_normalization"] is True
    assert report["pages_a"] == 10 and report["pages_b"] == 5
    assert float(report["score"]) >= 0.99


def test_extract_text_clamps_max_pages_minimum(
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakePage:
        def __init__(self, t: str) -> None:
            self.t = t

        def extract_text(self, _extraction_mode: str | None = None) -> str:
            return self.t

    class _Reader:
        def __init__(self, _path: str) -> None:
            self.pages = [
                _FakePage("A"),
                _FakePage("B"),
                _FakePage("C"),
            ]

    fake_pypdf = _make_module(PdfReader=_Reader)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    v = PDFQualityValidator()
    res = v.extract_text_hybrid("dummy.pdf", max_pages=0)
    assert res.text_per_page == ["A"]


def test_extract_text_honors_max_pages_boundary(
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakePage:
        def __init__(self, t: str) -> None:
            self.t = t

        def extract_text(self, _extraction_mode: str | None = None) -> str:
            return self.t

    class _Reader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePage("A"), _FakePage("B")]

    fake_pypdf = _make_module(PdfReader=_Reader)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    v = PDFQualityValidator()
    res = v.extract_text_hybrid("dummy.pdf", max_pages=1)
    assert res.text_per_page == ["A"]


def test_extract_text_clamps_dpi_minimum(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    # Force OCR path so convert_from_path is used
    class _FakePage:
        def extract_text(self, _extraction_mode: str | None = None) -> str:
            return ""

    class _Reader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePage()]

    dpi_seen: list[int] = []

    def _convert_from_path(
        _pdf_path: str = "",
        dpi: int = 72,
        first_page: int = 1,
        last_page: int = 1,
        _poppler_path=None,
        **_kwargs,
    ) -> list[object]:
        dpi_seen.append(dpi)
        return [object()]

    def _image_to_string(_img: object, _lang: str, _timeout: float) -> str:
        return "X"

    fake_pypdf = _make_module(PdfReader=_Reader)
    fake_pdfminer_high = _make_module(extract_text=lambda *_a, **_k: "")
    fake_pdf2image = _make_module(convert_from_path=_convert_from_path)
    fake_pytesseract = _make_module(image_to_string=_image_to_string)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        if name == "pdfminer.high_level":
            return fake_pdfminer_high
        if name == "pdf2image":
            return fake_pdf2image
        if name == "pytesseract":
            return fake_pytesseract
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    pdf_path = tmp_path / "z.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    v = PDFQualityValidator()
    _ = v.extract_text_hybrid(str(pdf_path), dpi=0)
    assert dpi_seen and dpi_seen[0] >= 72


def test_extract_text_honors_dpi_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    class _FakePage:
        def extract_text(self, _extraction_mode: str | None = None) -> str:
            return ""

    class _Reader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePage()]

    dpi_seen: list[int] = []

    def _convert_from_path(
        _pdf_path: str = "",
        dpi: int = 72,
        first_page: int = 1,
        last_page: int = 1,
        _poppler_path=None,
        **_kwargs,
    ) -> list[object]:
        dpi_seen.append(dpi)
        return [object()]

    def _image_to_string(_img: object, _lang: str, _timeout: float) -> str:
        return "X"

    fake_pypdf = _make_module(PdfReader=_Reader)
    fake_pdfminer_high = _make_module(extract_text=lambda *_a, **_k: "")
    fake_pdf2image = _make_module(convert_from_path=_convert_from_path)
    fake_pytesseract = _make_module(image_to_string=_image_to_string)

    def _import_module(name: str):
        if name == "pypdf":
            return fake_pypdf
        if name == "pdfminer.high_level":
            return fake_pdfminer_high
        if name == "pdf2image":
            return fake_pdf2image
        if name == "pytesseract":
            return fake_pytesseract
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("importlib.import_module", _import_module)

    pdf_path = tmp_path / "y.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    v = PDFQualityValidator()
    _ = v.extract_text_hybrid(str(pdf_path), dpi=72)
    assert dpi_seen and dpi_seen[0] == 72
