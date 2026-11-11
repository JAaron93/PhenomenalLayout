"""Tests for file handling utilities (utils/file_handler.py)."""

from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from utils.file_handler import FileHandler, atomic_write_json, atomic_write_text


class _FakeFileLike:
    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._buffer = io.BytesIO(data)

    def read(self) -> bytes:
        return self._buffer.read()


class _ExplodingRead(_FakeFileLike):
    def read(self) -> bytes:
        raise RuntimeError("read failed mid-stream")


class _BrokenStream:
    def read(self, _size: int = -1) -> bytes:
        raise RuntimeError("stream read failed")

    def close(self) -> None:
        raise RuntimeError("stream close failed")


def make_upload(data: bytes, filename: str | None) -> UploadFile:
    headers = Headers({"content-type": "application/pdf"})
    return UploadFile(file=io.BytesIO(data), filename=filename, headers=headers)


@pytest.fixture()
def handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FileHandler:
    dirs = (
        str(tmp_path / "uploads"),
        str(tmp_path / "downloads"),
        str(tmp_path / "temp"),
    )
    monkeypatch.setattr("utils.file_handler.MANAGED_FILE_DIRS", dirs)
    return FileHandler()


class TestFileHandlerInit:
    def test_creates_all_managed_directories(self, handler: FileHandler) -> None:
        for directory in (handler.upload_dir, handler.download_dir, handler.temp_dir):
            assert Path(directory).is_dir()


class TestSaveUploadedFile:
    def test_saves_file_like_upload(self, handler: FileHandler) -> None:
        fake = _FakeFileLike("thesis.pdf", b"%PDF-1.4 body")
        saved = handler.save_uploaded_file(fake)
        saved_path = Path(saved)
        assert saved_path.parent == Path(handler.upload_dir)
        assert saved_path.suffix == ".pdf"
        assert saved_path.read_bytes() == b"%PDF-1.4 body"

    def test_rejects_unsupported_type_and_writes_nothing(
        self, handler: FileHandler
    ) -> None:
        with pytest.raises(ValueError, match="Unsupported file type"):
            handler.save_uploaded_file(_FakeFileLike("thesis.txt", b"data"))
        assert list(Path(handler.upload_dir).iterdir()) == []

    def test_copies_path_named_object(self, handler: FileHandler, tmp_path: Path) -> None:
        # Characterizes the real contract: the non-file-like branch resolves
        # `file.name`, which for Gradio FileData objects is the FULL temp
        # path string (not a basename). A pathlib.Path input would resolve
        # its basename relative to CWD and fail the managed-path check.
        class _PathNamedUpload:
            def __init__(self, path: Path) -> None:
                self.name = str(path)

        source = tmp_path / "source.pdf"
        source.write_bytes(b"%PDF-1.4 copy")
        saved = Path(handler.save_uploaded_file(_PathNamedUpload(source)))
        assert saved.read_bytes() == b"%PDF-1.4 copy"

    def test_propagates_read_errors(self, handler: FileHandler) -> None:
        with pytest.raises(RuntimeError, match="read failed"):
            handler.save_uploaded_file(_ExplodingRead("thesis.pdf", b"data"))


class TestSaveUploadFile:
    def test_saves_upload_and_closes_stream(self, handler: FileHandler) -> None:
        upload = make_upload(b"%PDF-1.4 body", "doc.pdf")
        saved = Path(handler.save_upload_file(upload))
        assert saved.parent == Path(handler.upload_dir)
        assert saved.suffix == ".pdf"
        assert saved.read_bytes() == b"%PDF-1.4 body"
        assert upload.file.closed is True

    def test_rejects_missing_filename(self, handler: FileHandler) -> None:
        upload = make_upload(b"data", None)
        with pytest.raises(ValueError, match="no filename"):
            handler.save_upload_file(upload)
        assert list(Path(handler.upload_dir).iterdir()) == []

    def test_rejects_unsupported_extension(self, handler: FileHandler) -> None:
        upload = make_upload(b"data", "doc.txt")
        with pytest.raises(ValueError, match="Unsupported file type"):
            handler.save_upload_file(upload)
        assert list(Path(handler.upload_dir).iterdir()) == []

    def test_cleans_up_partial_write_on_stream_failure(
        self, handler: FileHandler
    ) -> None:
        upload = UploadFile(
            file=cast(Any, _BrokenStream()),
            filename="doc.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        with pytest.raises(RuntimeError, match="stream read failed"):
            handler.save_upload_file(upload)
        assert list(Path(handler.upload_dir).iterdir()) == []


class TestCreateTempFile:
    def test_creates_file_with_suffix_in_temp_dir(self, handler: FileHandler) -> None:
        temp_path = Path(handler.create_temp_file(suffix=".pdf"))
        assert temp_path.parent == Path(handler.temp_dir)
        assert temp_path.suffix == ".pdf"
        assert temp_path.exists()


class TestCleanupFile:
    def test_removes_existing_file(self, handler: FileHandler) -> None:
        target = Path(handler.temp_dir) / "stale.pdf"
        target.write_bytes(b"data")
        assert handler.cleanup_file(str(target)) is True
        assert not target.exists()

    def test_missing_file_returns_false(self, handler: FileHandler) -> None:
        missing = Path(handler.temp_dir) / "never-existed.pdf"
        assert handler.cleanup_file(str(missing)) is False


class TestGetFileInfo:
    def test_reports_existing_file(self, handler: FileHandler) -> None:
        target = Path(handler.temp_dir) / "info.pdf"
        target.write_bytes(b"12345")
        info = handler.get_file_info(str(target))
        assert info["path"] == str(target)
        assert info["size"] == 5
        assert info["is_dir"] is False
        assert "created" in info and "modified" in info

    def test_missing_file_raises(self, handler: FileHandler) -> None:
        missing = Path(handler.temp_dir) / "ghost.pdf"
        with pytest.raises(FileNotFoundError, match=r"ghost\.pdf"):
            handler.get_file_info(str(missing))


class TestCleanupOldFiles:
    def _age_file(self, path: Path, hours: float) -> None:
        stale = time.time() - hours * 3600
        os.utime(path, (stale, stale))

    def test_removes_only_files_older_than_max_age(self, handler: FileHandler) -> None:
        old = Path(handler.temp_dir) / "old.pdf"
        new = Path(handler.temp_dir) / "new.pdf"
        old.write_bytes(b"old")
        new.write_bytes(b"new")
        self._age_file(old, hours=48)
        assert handler.cleanup_old_files(max_age_hours=24) == 1
        assert not old.exists()
        assert new.exists()

    def test_scans_all_managed_directories(self, handler: FileHandler) -> None:
        for directory in (handler.upload_dir, handler.download_dir, handler.temp_dir):
            stale = Path(directory) / "stale.pdf"
            stale.write_bytes(b"stale")
            self._age_file(stale, hours=48)
        assert handler.cleanup_old_files(max_age_hours=24) == 3

    def test_skips_missing_directories(
        self, handler: FileHandler, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(handler, "download_dir", "/nonexistent/downloads")
        assert handler.cleanup_old_files() == 0

    def test_counts_unremovable_files_as_errors(
        self, handler: FileHandler, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simulate the unremovable file via unlink patching rather than
        # directory permissions: a root test runner would bypass chmod.
        stale = Path(handler.temp_dir) / "stale.pdf"
        stale.write_bytes(b"stale")
        self._age_file(stale, hours=48)
        real_unlink = Path.unlink

        def refuse_unlink(path: Path, *args: object) -> None:
            if path.name == "stale.pdf":
                raise PermissionError(f"refusing to unlink {path}")
            real_unlink(path)

        monkeypatch.setattr(Path, "unlink", refuse_unlink)
        assert handler.cleanup_old_files(max_age_hours=24) == 0
        assert stale.exists()


class TestAtomicWriteJson:
    def test_round_trips_json_payload(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        payload = {"a": 1, "nested": {"b": [1, 2]}, "umlaut": "Klüges"}
        atomic_write_json(target, payload)
        assert json.loads(target.read_text(encoding="utf-8")) == payload
        assert "Klüges" in target.read_text(encoding="utf-8")

    def test_accepts_str_target_and_custom_indent(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        atomic_write_json(str(target), {"k": "v"}, indent=4)
        assert json.loads(target.read_text(encoding="utf-8")) == {"k": "v"}

    def test_creates_nested_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "a" / "b" / "state.json"
        atomic_write_json(target, {"ok": True})
        assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}

    def test_overwrite_replaces_previous_contents(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        atomic_write_json(target, {"gen": 1})
        atomic_write_json(target, {"gen": 2})
        assert json.loads(target.read_text(encoding="utf-8")) == {"gen": 2}

    def test_leaves_no_temporary_files_behind(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        atomic_write_json(target, {"a": 1})
        assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


class TestAtomicWriteText:
    def test_round_trips_utf8_text(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        atomic_write_text(target, "Sein und Zeit — §1")
        assert target.read_text(encoding="utf-8") == "Sein und Zeit — §1"

    def test_honors_custom_encoding(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        atomic_write_text(target, "Käse", encoding="latin-1")
        assert target.read_bytes() == b"K\xe4se"

    def test_accepts_str_target(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        atomic_write_text(str(target), "ok")
        assert target.read_text(encoding="utf-8") == "ok"

    def test_leaves_no_temporary_files_behind(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        atomic_write_text(target, "ok")
        assert [p.name for p in tmp_path.iterdir()] == ["notes.txt"]
