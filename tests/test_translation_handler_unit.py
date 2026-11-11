"""Unit tests for core/translation_handler.py pure and facade-bound pieces."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import core.translation_handler as th


class _NamedBytesIO(io.BytesIO):
    def __init__(self, data: bytes, name: str) -> None:
        super().__init__(data)
        self.name = name


@pytest.fixture()
def isolated_file_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(th.file_handler, "upload_dir", str(upload_dir))
    return upload_dir


class TestExtractFileInfo:
    def test_none_file_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="No file uploaded"):
            th.extract_file_info(None)

    def test_string_path_returns_info(self, tmp_path: Path) -> None:
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(b"%PDF-1.4 body")
        file_path, file_name, file_size = th.extract_file_info(str(pdf))
        assert file_path == str(pdf)
        assert file_name == "book.pdf"
        assert file_size == len(b"%PDF-1.4 body")

    def test_missing_string_path_raises_value_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost.pdf"
        with pytest.raises(ValueError, match="Could not read uploaded file"):
            th.extract_file_info(str(missing))

    def test_gradio_file_data_saves_under_upload_dir(
        self, isolated_file_handler: Path
    ) -> None:
        source = isolated_file_handler.parent / "source.pdf"
        source.write_bytes(b"%PDF-1.4 filedata")
        file_data = SimpleNamespace(name=str(source), size=123)
        file_path, file_name, file_size = th.extract_file_info(file_data)
        assert file_name == "source.pdf"
        assert file_size == 123
        assert Path(file_path).parent == isolated_file_handler
        assert Path(file_path).read_bytes() == b"%PDF-1.4 filedata"

    @pytest.mark.usefixtures("isolated_file_handler")
    def test_file_like_object_saves_and_sizes(self) -> None:
        payload = _NamedBytesIO(b"%PDF-1.4 stream", "doc.pdf")
        file_path, file_name, file_size = th.extract_file_info(payload)
        assert file_name == "doc.pdf"
        assert file_size == len(b"%PDF-1.4 stream")
        assert Path(file_path).read_bytes() == b"%PDF-1.4 stream"

    def test_unsupported_object_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unsupported file object"):
            th.extract_file_info(42)


class TestGenerateOutputFilename:
    @pytest.mark.parametrize(
        ("original", "language", "expected"),
        [
            ("thesis.pdf", "German", "translated_thesis_german_advanced.pdf"),
            ("a/b/Die_Sehnsucht.pdf", "EN", "translated_Die_Sehnsucht_en_advanced.pdf"),
        ],
    )
    def test_filename_format(
        self, original: str, language: str, expected: str
    ) -> None:
        assert th.generate_output_filename(original, language) == expected


class TestTranslationStatusResult:
    def test_sequence_protocol(self) -> None:
        result = th.TranslationStatusResult(
            message="m", progress=7, is_done=True, is_error=False, output_file="o.pdf"
        )
        assert len(result) == 5
        assert list(result) == ["m", 7, True, False, "o.pdf"]
        assert result[0] == "m"
        assert result[4] == "o.pdf"
        with pytest.raises(IndexError, match="out of range"):
            _ = result[5]

    def test_defaults_and_equality(self) -> None:
        first = th.TranslationStatusResult(
            message="m", progress=0, is_done=False, is_error=False
        )
        second = th.TranslationStatusResult(
            message="m", progress=0, is_done=False, is_error=False
        )
        assert first == second
        assert first.output_file is None


class TestGetTranslationStatus:
    def test_idle_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(th.state, "translation_status", "idle")
        result = th.get_translation_status()
        assert result.message == "Ready for advanced translation"
        assert (result.progress, result.is_done, result.is_error) == (0, False, False)

    def test_starting_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(th.state, "translation_status", "starting")
        result = th.get_translation_status()
        assert result.progress == 5
        assert result.is_done is False

    def test_processing_status_reports_progress(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(th.state, "translation_status", "processing")
        monkeypatch.setattr(th.state, "translation_progress", 63)
        result = th.get_translation_status()
        assert result.progress == 63
        assert "63%" in result.message

    def test_completed_status_carries_output_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(th.state, "translation_status", "completed")
        monkeypatch.setattr(th.state, "output_file", "/out/final.pdf")
        result = th.get_translation_status()
        assert result.is_done is True
        assert result.output_file == "/out/final.pdf"

    def test_error_status_carries_error_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(th.state, "translation_status", "error")
        monkeypatch.setattr(th.state, "error_message", "GCP down")
        result = th.get_translation_status()
        assert result.is_error is True
        assert "GCP down" in result.message

    def test_unknown_status_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(th.state, "translation_status", "bogus")
        assert th.get_translation_status().message == "Unknown status"


class TestDownloadTranslatedFile:
    def test_not_completed_returns_error_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(th.state, "translation_status", "idle")
        monkeypatch.setattr(th.state, "output_file", None)
        assert th.download_translated_file("PDF") == "❌ No translated file available"

    def test_non_pdf_format_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(th.state, "translation_status", "completed")
        monkeypatch.setattr(th.state, "output_file", "/out/final.pdf")
        result = th.download_translated_file("epub")
        assert "Only PDF downloads are supported" in result

    def test_completed_pdf_returns_output_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(th.state, "translation_status", "completed")
        monkeypatch.setattr(th.state, "output_file", "/out/final.pdf")
        assert th.download_translated_file("PDF") == "/out/final.pdf"


class TestProcessFileUploadSync:
    def test_none_file_returns_error_payload(self) -> None:
        result = th.process_file_upload_sync(None)
        assert result["success"] is False
        assert "No file uploaded" in result["status"]

    def test_inner_exception_returns_error_payload(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(_file: Any) -> th.ProcessFileUploadResult:
            raise RuntimeError("processing exploded")

        monkeypatch.setattr(th, "process_file_upload", boom)
        result = th.process_file_upload_sync(None)
        assert result["success"] is False
        assert "Processing failed" in result["status"]


class TestModuleLazyAttributes:
    def test_unknown_module_attribute_raises(self) -> None:
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = th.definitely_not_an_attribute
