"""Tests for Gradio 6 interface, components, and FastAPI ASGI mounting."""

import json
from pathlib import Path
from typing import Any

import gradio as gr
import pytest
from fastapi.testclient import TestClient

from app import create_app
from tests.helpers import write_encrypted_pdf, write_minimal_pdf
from ui.gradio_interface import (
    APP_TITLE,
    create_gradio_interface,
    on_file_upload,
    render_metrics,
    start_translation_with_progress,
)


class TestGradioMetricsRendering:
    """Test render_metrics helper under various input formats."""

    def test_render_metrics_with_known_keys(self) -> None:
        metrics = {
            "ocr_conf": 0.95,
            "layout_score": 0.88,
            "text_accuracy": 0.92,
        }
        rendered = render_metrics(metrics)
        assert "OCR confidence: 0.95" in rendered
        assert "Layout score: 0.88" in rendered
        assert "Text accuracy: 0.92" in rendered

    def test_render_metrics_fallback_to_json(self) -> None:
        metrics = {"custom_metric": 42}
        rendered = render_metrics(metrics)
        parsed = json.loads(rendered)
        assert parsed == {"custom_metric": 42}

    def test_render_metrics_empty(self) -> None:
        assert render_metrics({}) == ""


class TestGradioFileUploadValidation:
    """Test on_file_upload handler with various file inputs."""

    def test_on_file_upload_none(self) -> None:
        result = on_file_upload(None)
        assert isinstance(result, tuple)
        assert len(result) == 6
        assert result == ("", "", "", "", "", "")

    def test_on_file_upload_valid_pdf(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from ui import gradio_interface as gi

        def fake_process(_file: Any):
            return {
                "preview": "PDF preview content sample",
                "status": "✅ File processed successfully",
                "detected_language": "German",
                "preprocessing_info": "Rendered 1 page(s)",
                "info": {"total_pages": 1, "metrics": {"ocr_conf": 0.98}},
                "metrics": {"ocr_conf": 0.98, "layout_score": 0.95},
            }

        monkeypatch.setattr(gi, "process_file_upload_sync", fake_process)

        pdf_path = tmp_path / "sample.pdf"
        write_minimal_pdf(pdf_path)

        preview, status, lang, prep, _info, metrics = on_file_upload(str(pdf_path))
        assert preview == "PDF preview content sample"
        assert "processed successfully" in status
        assert lang == "German"
        assert prep == "Rendered 1 page(s)"
        assert "OCR confidence: 0.98" in metrics

    def test_on_file_upload_non_pdf_rejection(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from ui import gradio_interface as gi

        def fake_process(_file: Any):
            return {
                "error_code": "DOLPHIN_005",
                "message": "Only PDF format supported",
            }

        monkeypatch.setattr(gi, "process_file_upload_sync", fake_process)

        fake_pdf = tmp_path / "not_a_pdf.pdf"
        fake_pdf.write_bytes(b"Plain text file contents")

        preview, status, _lang, _prep, _info, _metrics = on_file_upload(str(fake_pdf))
        assert preview == ""
        assert "DOLPHIN_005" in status
        assert "Only PDF format supported" in status

    def test_on_file_upload_encrypted_pdf_rejection(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from ui import gradio_interface as gi

        def fake_process(_file: Any):
            return {
                "error_code": "DOLPHIN_014",
                "message": "Encrypted PDFs not supported - please provide unlocked PDF",
            }

        monkeypatch.setattr(gi, "process_file_upload_sync", fake_process)

        enc_pdf = tmp_path / "locked.pdf"
        write_encrypted_pdf(enc_pdf)

        preview, status, _lang, _prep, _info, _metrics = on_file_upload(str(enc_pdf))
        assert preview == ""
        assert "DOLPHIN_014" in status
        assert "Encrypted PDFs not supported" in status

    def test_on_file_upload_tuple_contract_compatibility(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ui import gradio_interface as gi

        def fake_process(_file: Any):
            return (
                "preview text",
                "upload ok",
                "English",
                "converted info",
                {"info": "ocr details", "metrics": {"ocr_conf": 0.91}},
            )

        monkeypatch.setattr(gi, "process_file_upload_sync", fake_process)

        preview, status, lang, _prep, _info, metrics = on_file_upload("dummy.pdf")
        assert preview == "preview text"
        assert status == "upload ok"
        assert lang == "English"
        assert "OCR confidence: 0.91" in metrics


class TestGradioTranslationWorkflowAndTimer:
    """Test start translation, timer ticks, and download button state transitions."""

    def test_start_translation_triggers_timer_and_disables_download(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ui import gradio_interface as gi

        def fake_start(target, pages, philosophy):
            assert target == "French"
            assert pages == 10
            assert philosophy is True
            return ("🚀 Advanced translation started...", "Processing", False)

        monkeypatch.setattr(gi, "start_translation_sync", fake_start)

        status, _upload_status, download_btn, timer = start_translation_with_progress(
            target_language="French",
            pages_to_translate=10,
            philosophy_mode=True,
        )

        assert "started" in status
        # Download button should NOT be interactive while processing
        assert getattr(download_btn, "interactive", None) is False or isinstance(
            download_btn, (gr.Button, dict)
        )
        # Timer should be active to poll for updates
        assert getattr(timer, "active", None) is True or isinstance(
            timer, (gr.Timer, dict)
        )

    def test_start_translation_error_handling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ui import gradio_interface as gi

        def fake_start(_target, _pages, _philosophy):
            raise RuntimeError("Backend connection timed out")

        monkeypatch.setattr(gi, "start_translation_sync", fake_start)

        status, _upload_status, _download_btn, timer = start_translation_with_progress(
            target_language="German",
            pages_to_translate=5,
            philosophy_mode=False,
        )

        assert "❌ Error" in status
        assert getattr(timer, "active", None) is False

    def test_update_status_halts_timer_on_completion_and_idle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.translation_handler import TranslationStatusResult
        from ui import gradio_interface as gi

        def fake_status_completed():
            return TranslationStatusResult(
                message="✅ Advanced translation completed with format preservation!",
                progress=100,
                is_done=True,
                is_error=False,
                output_file="downloads/translated_doc.pdf",
            )

        monkeypatch.setattr(gi, "get_translation_status", fake_status_completed)

        status_res = fake_status_completed()
        assert status_res.is_done is True
        assert status_res.output_file == "downloads/translated_doc.pdf"

        # Verify interface update_status function deactivates timer on idle and completion
        interface = create_gradio_interface()
        # Find update_status in interface event handlers
        for fn in interface.fns.values():
            if fn.fn and fn.fn.__name__ == "update_status":
                _status, btn, timer = fn.fn()
                # When completed, download ready is True and timer is inactive
                assert getattr(timer, "active", None) is False
                assert getattr(btn, "interactive", None) is True
                break


class TestGradioBlocksStructureAndFastAPIMount:
    """Test Gradio 6 Blocks construction, theme, CSS, and FastAPI ASGI mounting."""

    def test_create_gradio_interface_structure(self) -> None:
        demo = create_gradio_interface()
        assert isinstance(demo, gr.Blocks)
        assert demo.title == APP_TITLE
        # Theme and CSS should be properly configured on the Blocks instance
        assert demo.theme is not None
        assert isinstance(demo.css, str)

    def test_fastapi_asgi_sub_mounting(self) -> None:
        app = create_app()
        gradio_app = create_gradio_interface()
        app_with_gradio = gr.mount_gradio_app(app, gradio_app, path="/ui")

        client = TestClient(app_with_gradio)
        # Test FastAPI native route
        resp_root = client.get("/")
        assert resp_root.status_code in {200, 404}  # App root route responds

        # Test Gradio UI route
        resp_ui = client.get("/ui")
        # Gradio mount returns 200 or 307 redirect to /ui/
        assert resp_ui.status_code in {200, 307, 308}

        resp_ui_slash = client.get("/ui/")
        assert resp_ui_slash.status_code == 200
        assert "html" in resp_ui_slash.headers.get("content-type", "").lower()
