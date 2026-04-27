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
    assert detail.get("error_code") == "DOLPHIN_005"
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
    assert body["detail"]["error_code"] == "DOLPHIN_014"


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
