from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import api_router, app_router
from tests.helpers import write_encrypted_pdf, write_minimal_pdf


def _make_app() -> TestClient:
    app = FastAPI()
    app.include_router(app_router)
    app.include_router(api_router, prefix="/api")
    return TestClient(app)


def test_upload_rejects_non_pdf(tmp_path: Path) -> None:
    client = _make_app()
    nonpdf = tmp_path / "f.txt"
    nonpdf.write_text("hello")
    with nonpdf.open("rb") as fh:
        res = client.post(
            "/api/upload",
            files={"file": ("f.txt", fh, "text/plain")},
        )
    assert res.status_code == 400
    body = res.json()
    # Validate structured error payload
    assert isinstance(body, dict)
    assert "detail" in body
    detail = body["detail"]
    assert isinstance(detail, dict)
    assert detail.get("error_code") == "DOC_INVALID_FORMAT"
    message = detail.get("message", "")
    assert isinstance(message, str) and message
    assert "Only PDF format" in message
    # Optional fields if present
    timestamp = detail.get("timestamp")
    if timestamp is not None:
        assert isinstance(timestamp, str)
    context = detail.get("context")
    if context is not None:
        assert isinstance(context, dict)


def test_upload_rejects_encrypted_pdf(tmp_path: Path) -> None:
    client = _make_app()
    enc = tmp_path / "enc.pdf"
    write_encrypted_pdf(enc)
    with enc.open("rb") as fh:
        res = client.post(
            "/api/upload",
            files={"file": ("enc.pdf", fh, "application/pdf")},
        )
    assert res.status_code == 400
    body = res.json()
    assert body["detail"]["error_code"] == "DOC_ENCRYPTED_PDF"


def test_upload_accepts_valid_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_app()
    pdf = tmp_path / "ok.pdf"
    write_minimal_pdf(pdf)

    # Monkeypatch save to use our tmp file path passthrough
    from core.translation_handler import document_processor, file_handler

    def _save_upload_file(_file):
        # emulate returning a saved path
        return str(pdf)

    async def _extract_content(_path: str):
        return {"type": "pdf", "metadata": {}}

    monkeypatch.setattr(file_handler, "save_upload_file", _save_upload_file)
    monkeypatch.setattr(
        document_processor,
        "extract_content",
        _extract_content,
    )

    with pdf.open("rb") as fh:
        res = client.post(
            "/api/upload",
            files={"file": ("ok.pdf", fh, "application/pdf")},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "ok.pdf"
    assert body["content_type"] == "pdf"


def test_upload_cleans_up_file_on_encryption_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that when an encrypted PDF is rejected, it does not leak on disk."""
    from core.translation_handler import file_handler

    # Use monkeypatch.setattr so the original upload_dir is restored after teardown
    monkeypatch.setattr(file_handler, "upload_dir", str(tmp_path / "uploads"))
    Path(file_handler.upload_dir).mkdir(parents=True, exist_ok=True)

    client = _make_app()
    enc = tmp_path / "enc.pdf"
    write_encrypted_pdf(enc)

    with enc.open("rb") as fh:
        res = client.post(
            "/api/upload",
            files={"file": ("enc.pdf", fh, "application/pdf")},
        )
    assert res.status_code == 400
    # Confirm no files were leaked in upload_dir
    leaked = [p for p in Path(file_handler.upload_dir).iterdir() if p.name != ".gitkeep"]
    assert leaked == []


def test_upload_cleans_up_file_on_corrupt_header_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that when a corrupt PDF header fails validation, it does not leak on disk."""
    from core.translation_handler import file_handler

    # Use monkeypatch.setattr so the original upload_dir is restored after teardown
    monkeypatch.setattr(file_handler, "upload_dir", str(tmp_path / "uploads"))
    Path(file_handler.upload_dir).mkdir(parents=True, exist_ok=True)

    client = _make_app()
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"NOT A REAL PDF HEADER")

    with corrupt.open("rb") as fh:
        res = client.post(
            "/api/upload",
            files={"file": ("corrupt.pdf", fh, "application/pdf")},
        )
    assert res.status_code == 400
    assert res.json()["detail"]["error_code"] == "DOC_INVALID_FORMAT"
    leaked = [p for p in Path(file_handler.upload_dir).iterdir() if p.name != ".gitkeep"]
    assert leaked == []


def test_bilingual_view_rejects_non_pdf_file() -> None:
    from api.auth import create_jwt_token

    client = _make_app()
    token = create_jwt_token("alice")
    res = client.post(
        "/api/book/dual-pane/sess-1?user_id=alice&page_number=1",
        files={"file": ("invalid.txt", b"plain text", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "Only PDF files are supported" in res.json()["detail"]


def test_bilingual_view_rejects_empty_file() -> None:
    from api.auth import create_jwt_token

    client = _make_app()
    token = create_jwt_token("alice")
    res = client.post(
        "/api/book/dual-pane/sess-1?user_id=alice&page_number=1",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "Uploaded file is empty" in res.json()["detail"]

