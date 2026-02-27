import contextlib
import json
import logging
from pathlib import Path

import gradio as gr

from core.translation_handler import (
    download_translated_file,
    get_translation_status,
    process_file_upload_sync,
    start_translation_sync,
)


def render_metrics(metrics_dict: dict) -> str:
    """Render metrics dictionary into a human-readable string.

    Recognizes common keys like OCR confidence, layout scores, and
    text accuracy. Falls back to compact JSON if no known keys are present.
    """
    parts: list[str] = []
    ocr = metrics_dict.get("ocr_conf") or metrics_dict.get("ocr_confidence")
    if isinstance(ocr, (int, float)):
        parts.append(f"OCR confidence: {float(ocr):.2f}")
    layout = (
        metrics_dict.get("layout_score")
        or metrics_dict.get("layout_similarity")
        or metrics_dict.get("layout_preservation")
        or metrics_dict.get("layout_preservation_score")
    )
    if isinstance(layout, (int, float)):
        parts.append(f"Layout score: {float(layout):.2f}")
    text_acc = metrics_dict.get("text_accuracy")
    if isinstance(text_acc, (int, float)):
        parts.append(f"Text accuracy: {float(text_acc):.2f}")
    if not parts:
        # Fallback to compact JSON if nothing recognized
        with contextlib.suppress(Exception):
            return json.dumps(metrics_dict)
    return "; ".join(parts)


# Application title used across UI and docs
APP_TITLE = "Advanced PDF Document Translator"

# Ensure the module docstring reflects the single source of truth title
__doc__ = f"Gradio interface for {APP_TITLE}."


def on_file_upload(
    file,
    progress=None,
):
    """Wrapper to handle validation errors and quality metrics.

    Returns a 6-tuple matching UI outputs:
    (preview, upload_status, detected_language, preprocessing, processing_info,
     quality_metrics)
    """
    if progress is None:
        progress = gr.Progress(track_tqdm=False)
    try:
        with contextlib.suppress(Exception):
            progress(0.05, desc="Validating file")
        result = process_file_upload_sync(file)
    except Exception as exc:  # Fallback for unexpected client/server issues
        logging.error(
            "Unexpected error during file upload: %s",
            exc,
            exc_info=True,
        )
        msg = f"Upload failed: {exc}"
        return "", msg, "", "", "", ""

    # If server returned a structured error
    if isinstance(result, dict) and "error_code" in result:
        code = result.get("error_code", "")
        message = result.get("message", "Validation failed")
        friendly = message
        if code == "DOLPHIN_005":
            friendly = "Only PDF format supported"
        elif code == "DOLPHIN_014":
            friendly = "Encrypted PDFs not supported - please provide unlocked PDF"
        with contextlib.suppress(Exception):
            progress(1.0)
        return "", f"{code}: {friendly}", "", "", "", ""

    # If server returned a structured non-error dict, try to map keys
    if isinstance(result, dict):
        result_dict = result  # help type-checkers
        preview = result_dict.get("preview") or ""
        upload_status = (
            result_dict.get("status") or result_dict.get("upload_status") or ""
        )
        detected_language = result_dict.get("detected_language") or ""
        preprocessing = result_dict.get("preprocessing") or ""
        info_obj = result_dict.get("info") or result_dict.get("processing_info") or {}
        progress_obj = result_dict.get("progress") or {}
        metrics_obj = result_dict.get("metrics") or (
            info_obj.get("metrics") if isinstance(info_obj, dict) else None
        )
        # Render progress into a short line, if present
        if isinstance(progress_obj, dict):
            desc = str(progress_obj.get("desc") or "")
            val = progress_obj.get("value")
            pct = None
            try:
                pct = int(float(val) * 100) if val is not None else None
            except (TypeError, ValueError):
                pct = None
            if pct is not None:
                prog_line = f"Progress: {desc} {pct}%"
            else:
                prog_line = f"Progress: {desc}"
            # If info is a string, append; if dict, add field
            if isinstance(info_obj, str):
                info_obj = (info_obj + "\n" + prog_line).strip()
            elif isinstance(info_obj, dict):
                info_obj = {**info_obj, "progress_text": prog_line}
            else:
                info_obj = prog_line
        metrics_str = ""
        if isinstance(metrics_obj, dict):
            metrics_str = render_metrics(metrics_obj)
        with contextlib.suppress(Exception):
            progress(1.0)
        return (
            preview,
            upload_status,
            detected_language,
            preprocessing,
            info_obj,
            metrics_str,
        )

    # Otherwise assume tuple/list contract from process_file_upload
    if isinstance(result, (tuple, list)):
        # Pad or slice to first 5 slots; quality metrics default empty
        vals = list(result)[:5]
        while len(vals) < 5:
            vals.append("")
        # Try to derive simple metrics if present in processing info
        metrics = ""
        try:
            info = vals[4]
            if isinstance(info, dict) and "metrics" in info:
                metrics = render_metrics(info["metrics"])
            # Also surface any basic progress field into a short note
            if isinstance(info, dict) and "progress" in info:
                _p = info.get("progress")
                if isinstance(_p, dict):
                    desc = str(_p.get("desc") or "")
                    val = _p.get("value")
                    pct = None
                    try:
                        if val is not None:
                            pct = int(float(val) * 100)
                    except (TypeError, ValueError):
                        pct = None
                    if pct is not None:
                        note = f"Progress: {desc} {pct}%"
                    else:
                        note = f"Progress: {desc}"
                    # Convert dict into friendly text line if needed
                    vals[4] = {**info, "progress_text": note}
        except Exception:  # ignore extraction errors
            metrics = ""
        with contextlib.suppress(Exception):
            progress(1.0)
        return vals[0], vals[1], vals[2], vals[3], vals[4], metrics

    # Unknown return; show generic status
    return "", "Upload complete", "", "", "", ""


def start_translation_with_progress(
    target_language,
    pages_to_translate,
    philosophy_mode,
    progress=None,
):
    """Start translation and update a subtle progress indicator.

    Returns the same tuple as ``start_translation``.
    """
    if progress is None:
        progress = gr.Progress(track_tqdm=False)
    with contextlib.suppress(Exception):
        progress(0.05, desc="Starting translation")
        result = start_translation_sync(
            target_language,
            pages_to_translate,
            philosophy_mode,
        )
    with contextlib.suppress(Exception):
        progress(0.2, desc="Submitted to backend")
    return result


def create_gradio_interface() -> gr.Blocks:
    """Create the advanced Gradio interface for PDF translation with OCR.

    This builds the Blocks UI, wires events, and returns the interface.
    """
    # Load supported languages from config (fallback to defaults)
    languages_path = Path(__file__).parent.parent / "config" / "languages.json"
    from utils.language_utils import DEFAULT_SUPPORTED_LANGUAGES
    try:
        data = json.loads(languages_path.read_text())
        supported_languages = data.get(
            "supported_languages",
            DEFAULT_SUPPORTED_LANGUAGES,
        )
    except FileNotFoundError:
        supported_languages = DEFAULT_SUPPORTED_LANGUAGES
    except json.JSONDecodeError:
        supported_languages = DEFAULT_SUPPORTED_LANGUAGES

    # Load CSS from external file
    css_path = Path(__file__).parent.parent / "static" / "styles.css"
    try:
        css_content = css_path.read_text()
    except FileNotFoundError:
        # Fallback if CSS file not found
        css_content = ""
        logging.warning("CSS file not found at %s", css_path)

    with gr.Blocks(
        title=APP_TITLE,
    ) as interface:
        with gr.Row():
            with gr.Column(scale=1):
                # File Upload Section
                gr.Markdown("## 📤 Upload Document")

                file_upload = gr.File(
                    label="Choose PDF File",
                    file_types=[".pdf"],
                    file_count="single",
                    elem_classes=["upload-area"],
                )

                upload_status = gr.Textbox(
                    label="Upload Status",
                    interactive=False,
                    lines=4,
                    max_lines=6,
                )

                # Pre-processing Display
                gr.Markdown("## 🔄 Pre-processing Steps")
                preprocessing_status = gr.Textbox(
                    label="PDF-to-Image Conversion",
                    interactive=False,
                    lines=6,
                    placeholder="Upload a PDF to see pre-processing steps...",
                    elem_classes=["preprocessing-panel"],
                )

                # Advanced Processing Info
                gr.Markdown("## 🔍 OCR Processing Details")
                processing_info = gr.Textbox(
                    label="Dolphin OCR Analysis",
                    interactive=False,
                    lines=8,
                    placeholder=("Pre-processing will show Dolphin OCR analysis..."),
                    elem_classes=["info-panel"],
                )

                # Quality metrics
                gr.Markdown("## 📈 Quality Metrics")
                quality_metrics = gr.Textbox(
                    label="Basic Quality Metrics",
                    interactive=False,
                    lines=6,
                    placeholder="OCR confidence, layout scores, etc.",
                )

            with gr.Column(scale=2):
                # Preview Section
                gr.Markdown("## 👀 Document Preview")

                document_preview = gr.Textbox(
                    label="Content Preview",
                    lines=12,
                    interactive=False,
                    placeholder=(
                        "Upload a document to see preview with advanced "
                        "processing info..."
                    ),
                )

                # Language and Translation Section
                with gr.Row():
                    with gr.Column():
                        detected_language = gr.Textbox(
                            label="Detected Source Language", interactive=False
                        )

                    with gr.Column():
                        target_language = gr.Dropdown(
                            label="Target Language",
                            choices=supported_languages,
                            value="English",
                        )

                # Page limit slider (increased from 200 to 2000 pages)
                pages_slider = gr.Slider(
                    minimum=1,
                    maximum=2000,
                    step=1,
                    value=50,
                    label="Pages to translate",
                )

                # Philosophy mode toggle
                philosophy_mode = gr.Checkbox(
                    label=("Enable Philosophy Mode (Neologism Detection)"),
                    value=False,
                )
                # Translation Controls
                translate_btn = gr.Button(
                    "🚀 Start Advanced Translation",
                    variant="primary",
                    size="lg",
                )

                # Progress Section
                gr.Markdown("## 📊 Translation Progress")

                with gr.Row():
                    progress_status = gr.Textbox(
                        label="Status", interactive=False, scale=4
                    )
                    refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=1)

                # Progress section without standalone Progress bar
                # progress_bar = gr.Progress()

                # Timer for auto-refreshing progress while translation runs
                progress_timer = gr.Timer(1.0, active=False)

                # Export Section
                gr.Markdown("## 💾 Download Translated Document")

                with gr.Row():
                    output_format = gr.Dropdown(
                        label="Output Format",
                        choices=["PDF"],
                        value="PDF",
                    )

                    download_btn = gr.Button(
                        "📥 Download", variant="secondary", interactive=False
                    )

                download_file = gr.File(label="Download File", visible=False)

        # Event Handlers
        file_upload.change(
            fn=on_file_upload,
            inputs=[file_upload],
            outputs=[
                document_preview,
                upload_status,
                detected_language,
                preprocessing_status,
                processing_info,
                quality_metrics,
            ],
        )

        translate_btn.click(
            fn=start_translation_with_progress,
            inputs=[target_language, pages_slider, philosophy_mode],
            outputs=[
                progress_status,
                upload_status,
                download_btn,
                progress_timer,
            ],
        )

        # Status update function for manual refresh
        def update_status(_progress: "gr.Progress | None" = None):
            if _progress is None:
                _progress = gr.Progress(track_tqdm=False)
            if _progress is None:
                gr.Progress(track_tqdm=False)
            status, _unused, download_ready = get_translation_status()
            timer_update = gr.Timer(active=not bool(download_ready))
            return status, gr.update(interactive=download_ready), timer_update

        # Connect refresh button to status update
        # Manual refresh
        refresh_btn.click(
            fn=update_status,
            outputs=[progress_status, download_btn, progress_timer],
        )

        # Auto refresh via timer while translation is running
        progress_timer.tick(
            fn=update_status,
            outputs=[progress_status, download_btn, progress_timer],
        )

        download_btn.click(
            fn=download_translated_file,
            inputs=[output_format],
            outputs=[download_file],
        )

    # Apply theme and css directly to the Blocks instance to avoid Gradio 6 deprecation warnings on the constructor.
    # Note: When mounting via gr.mount_gradio_app in FastAPI, launch() is not called directly,
    # so we set these properties before mounting/launching.
    interface.theme = gr.themes.Soft()
    interface.css = css_content

    return interface
