"""Tests for upload/artifact path validation at processing boundaries."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from utils.file_handler import FileHandler


@pytest.fixture
def handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FileHandler:
    """FileHandler rooted in an isolated temp working directory."""
    monkeypatch.chdir(tmp_path)
    return FileHandler()


class _GradioFileStub:
    def __init__(self, name: str) -> None:
        self.name = name


class TestSaveUploadedFile:
    def test_accepts_source_in_temp_storage(
        self, handler: FileHandler, tmp_path: Path
    ) -> None:
        source = tmp_path / "uploaded.pdf"
        source.write_bytes(b"%PDF-1.4 test")
        saved = handler.save_uploaded_file(_GradioFileStub(str(source)))
        assert saved.startswith(handler.upload_dir + os.sep)
        assert saved.endswith(".pdf")
        assert Path(saved).read_bytes() == b"%PDF-1.4 test"

    def test_rejects_source_outside_managed_areas(self, handler: FileHandler) -> None:
        with pytest.raises(ValueError, match="outside managed storage"):
            handler.save_uploaded_file(_GradioFileStub("/etc/hosts.pdf"))

    def test_stores_validated_pdf_extension(
        self, handler: FileHandler, tmp_path: Path
    ) -> None:
        source = tmp_path / "doc.PDF"
        source.write_bytes(b"%PDF-1.4")
        saved = handler.save_uploaded_file(_GradioFileStub(str(source)))
        assert Path(saved).suffix == ".pdf"

    def test_rejects_unsupported_types(self, handler: FileHandler) -> None:
        with pytest.raises(ValueError, match="Unsupported file type"):
            handler.save_uploaded_file(_GradioFileStub("/etc/hostname.txt"))


class TestExtractFileInfo:
    def test_case1_temp_path_roundtrip(self, tmp_path: Path) -> None:
        from core.translation_handler import extract_file_info

        probe = tmp_path / "book.pdf"
        probe.write_bytes(b"%PDF-1.4")
        file_path, file_name, file_size = extract_file_info(str(probe))
        assert Path(file_path) == Path(os.path.realpath(probe))
        assert file_name == "book.pdf"
        assert file_size == len(b"%PDF-1.4")

    def test_case1_rejects_outside_paths(self) -> None:
        from core.translation_handler import extract_file_info

        with pytest.raises(ValueError, match="outside managed storage"):
            extract_file_info("/etc/hostname")


class TestExtractContentBoundary:
    async def test_rejects_paths_outside_managed_areas(self) -> None:
        from services.enhanced_document_processor import EnhancedDocumentProcessor

        processor = EnhancedDocumentProcessor()
        with pytest.raises(ValueError, match="outside managed storage"):
            await processor.extract_content("/nonexistent/file.pdf")

    async def test_missing_file_in_managed_area_raises_filenotfound(
        self, tmp_path: Path
    ) -> None:
        from services.enhanced_document_processor import EnhancedDocumentProcessor

        processor = EnhancedDocumentProcessor()
        with pytest.raises(FileNotFoundError):
            await processor.extract_content(str(tmp_path / "missing.pdf"))


class TestValidationEngineContext:
    def test_stats_managed_file_size(self, tmp_path: Path) -> None:
        from core.dynamic_validation_engine import DynamicValidationEngine

        probe = tmp_path / "doc.pdf"
        probe.write_bytes(b"%PDF-1.4" + b"0" * 100)
        engine = DynamicValidationEngine()
        context = engine._create_context(str(probe))
        assert context.file_size == probe.stat().st_size

    def test_explicit_size_is_preserved(self) -> None:
        from core.dynamic_validation_engine import DynamicValidationEngine

        engine = DynamicValidationEngine()
        context = engine._create_context("test.pdf", file_size=1024)
        assert context.file_size == 1024


class TestValidateQualityRoute:
    @staticmethod
    def _client() -> Any:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.routes import api_router, app_router

        app = FastAPI()
        app.include_router(app_router)
        app.include_router(api_router, prefix="/api/v1")
        return TestClient(app)

    def test_rejects_paths_outside_managed_areas(self) -> None:
        response = self._client().post(
            "/api/v1/pdf/validate-quality",
            json={
                "original_pdf": "/etc/hostname",
                "reconstructed_pdf": "/etc/hostname",
            },
        )
        assert response.status_code == 400
        assert "outside managed storage" in response.text

    def test_accepts_managed_paths(self, tmp_path: Path, monkeypatch: Any) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "uploads").mkdir()
        (tmp_path / "uploads" / "doc.pdf").write_bytes(b"%PDF-1.4")
        response = self._client().post(
            "/api/v1/pdf/validate-quality",
            json={
                "original_pdf": "uploads/doc.pdf",
                "reconstructed_pdf": "uploads/doc.pdf",
            },
        )
        assert response.status_code != 400
