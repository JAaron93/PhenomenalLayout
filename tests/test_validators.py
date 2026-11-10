"""Tests for input validation utilities (utils/validators.py)."""

from __future__ import annotations

import io
from typing import Any, cast

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from utils.language_utils import DEFAULT_SUPPORTED_LANGUAGES
from utils.validators import FileValidator


def make_upload(
    data: bytes,
    filename: str | None,
    content_type: str = "application/pdf",
) -> UploadFile:
    headers = Headers({"content-type": content_type})
    return UploadFile(file=io.BytesIO(data), filename=filename, headers=headers)


class TestFileValidatorInit:
    def test_reads_size_limit_from_settings(self) -> None:
        validator = FileValidator()
        assert validator.max_file_size > 0

    def test_pdf_only_allowlists(self) -> None:
        validator = FileValidator()
        assert validator.allowed_extensions == {".pdf"}
        assert validator.allowed_mimetypes == {"application/pdf"}


class TestValidateFile:
    def setup_method(self) -> None:
        self.validator = FileValidator()

    def test_accepts_valid_pdf(self) -> None:
        assert self.validator.validate_file("report.pdf", 1024) == {"valid": True}

    @pytest.mark.parametrize("filename", ["report.PDF", "dir/sub/report.pdf"])
    def test_accepts_case_and_path_variants(self, filename: str) -> None:
        assert self.validator.validate_file(filename, 1024) == {"valid": True}

    def test_rejects_missing_filename(self) -> None:
        result = self.validator.validate_file("", 1024)
        assert result["valid"] is False
        assert "No filename" in result["error"]

    @pytest.mark.parametrize("filename", ["report.txt", "report", "report.docx"])
    def test_rejects_unsupported_extensions(self, filename: str) -> None:
        result = self.validator.validate_file(filename, 1024)
        assert result["valid"] is False
        assert "Unsupported file type" in result["error"]

    def test_rejects_oversize_file(self) -> None:
        oversize = self.validator.max_file_size + 1
        result = self.validator.validate_file("report.pdf", oversize)
        assert result["valid"] is False
        assert "File too large" in result["error"]

    def test_accepts_file_at_exact_size_limit(self) -> None:
        assert self.validator.validate_file(
            "report.pdf", self.validator.max_file_size
        ) == {"valid": True}

    def test_rejects_empty_file(self) -> None:
        result = self.validator.validate_file("report.pdf", 0)
        assert result["valid"] is False
        assert "empty" in result["error"]

    def test_returns_validation_error_on_unexpected_exception(self) -> None:
        result = self.validator.validate_file(cast(str, 123), 1024)
        assert result["valid"] is False
        assert "Validation error" in result["error"]


class TestValidateUploadFile:
    def setup_method(self) -> None:
        self.validator = FileValidator()

    def test_accepts_valid_pdf_upload(self) -> None:
        upload = make_upload(b"%PDF-1.4 content", "report.pdf")
        assert self.validator.validate_upload_file(upload) == {"valid": True}

    def test_rejects_unsupported_content_type(self) -> None:
        upload = make_upload(b"%PDF-1.4 content", "report.pdf", "text/plain")
        result = self.validator.validate_upload_file(upload)
        assert result["valid"] is False
        assert "Unsupported content type" in result["error"]

    def test_rejects_missing_filename(self) -> None:
        upload = make_upload(b"%PDF-1.4 content", None)
        result = self.validator.validate_upload_file(upload)
        assert result["valid"] is False
        assert "Missing filename" in result["error"]

    def test_rejects_oversize_upload_before_reading(self) -> None:
        self.validator.max_file_size = 10
        upload = make_upload(b"x" * 11, "report.pdf")
        result = self.validator.validate_upload_file(upload)
        assert result["valid"] is False
        assert "File too large" in result["error"]

    def test_oversize_path_leaves_stream_pointer_at_eof(self) -> None:
        # Pins current behavior: the oversize check returns before the
        # seek-back at utils/validators.py:130, so the stream position is
        # left at EOF (the docstring's "pointer preserved" claim does not
        # hold on this path). Flagged in the coverage PR for a follow-up.
        self.validator.max_file_size = 10
        upload = make_upload(b"x" * 11, "report.pdf")
        self.validator.validate_upload_file(upload)
        assert upload.file.tell() == 11

    def test_success_path_restores_stream_pointer(self) -> None:
        upload = make_upload(b"%PDF-1.4 content", "report.pdf")
        upload.file.seek(5)
        assert self.validator.validate_upload_file(upload) == {"valid": True}
        assert upload.file.tell() == 5

    def test_returns_validation_error_on_unexpected_exception(self) -> None:
        class ExplodingContentType:
            file: Any = io.BytesIO(b"data")
            filename: str | None = "report.pdf"

            @property
            def content_type(self) -> str:
                raise RuntimeError("content-type exploded")

        upload = cast(UploadFile, ExplodingContentType())
        result = self.validator.validate_upload_file(upload)
        assert result["valid"] is False
        assert "Validation error" in result["error"]


class TestLoadLanguageConfig:
    def test_loads_real_config_file(self) -> None:
        config = FileValidator()._load_language_config()
        assert "German" in config["supported_languages"]
        assert config["supported_formats"] == ["PDF"]

    def test_falls_back_to_defaults_when_config_unreadable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_oserror(*args: object, **kwargs: object) -> dict[str, object]:
            raise OSError("config unavailable")

        monkeypatch.setattr("utils.validators.json.load", raise_oserror)
        config = FileValidator()._load_language_config()
        assert config["supported_languages"] == DEFAULT_SUPPORTED_LANGUAGES
        assert config["supported_formats"] == ["PDF"]


class TestValidateLanguage:
    def setup_method(self) -> None:
        self.validator = FileValidator()

    @pytest.mark.parametrize(
        ("language", "expected"),
        [("english", True), ("English", True), ("  German  ", True)],
    )
    def test_case_insensitive_matching(
        self, language: str, expected: bool
    ) -> None:
        assert self.validator.validate_language(language)["valid"] is expected

    def test_rejects_empty_selection(self) -> None:
        result = self.validator.validate_language("")
        assert result["valid"] is False
        assert "No language selected" in result["error"]

    def test_rejects_whitespace_only_selection(self) -> None:
        result = self.validator.validate_language("   ")
        assert result["valid"] is False

    def test_rejects_unsupported_language_with_supported_list(self) -> None:
        result = self.validator.validate_language("Klingon")
        assert result["valid"] is False
        assert "German" in result["error"]


class TestValidateOutputFormat:
    def setup_method(self) -> None:
        self.validator = FileValidator()

    @pytest.mark.parametrize("format_type", ["pdf", "PDF", "Pdf"])
    def test_case_insensitive_matching(self, format_type: str) -> None:
        assert self.validator.validate_output_format(format_type) == {"valid": True}

    def test_rejects_empty_selection(self) -> None:
        result = self.validator.validate_output_format("")
        assert result["valid"] is False
        assert "No output format selected" in result["error"]

    def test_rejects_unsupported_format(self) -> None:
        result = self.validator.validate_output_format("EPUB")
        assert result["valid"] is False
        assert "Unsupported format" in result["error"]
