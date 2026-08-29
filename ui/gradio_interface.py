import contextlib
import json
import logging
from pathlib import Path
from typing import Any

import gradio as gr

from core.translation_handler import (
    download_translated_file,
    get_translation_status,
    process_file_upload_sync,
    start_translation_sync,
)
from utils.language_utils import DEFAULT_SUPPORTED_LANGUAGES


def render_metrics(metrics_dict: dict) -> str:
    """Render metrics dictionary into a human-readable string.

    Recognizes common keys like OCR confidence, layout scores, and
    text accuracy. Falls back to compact JSON if no known keys are present.
    """
    if not metrics_dict:
        return ""
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
    progress: gr.Progress = gr.Progress(track_tqdm=False),  # noqa: B008
):
    """Wrapper to handle validation errors and quality metrics.

    Returns a 6-tuple matching UI outputs:
    (preview, upload_status, detected_language, preprocessing, processing_info,
     quality_metrics)
    """
    if file is None:
        return "", "", "", "", "", ""
    if progress is not None:
        with contextlib.suppress(Exception):
            progress(0.05, desc="Validating file")
    try:
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
        if progress is not None:
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
        preprocessing = (
            result_dict.get("preprocessing_info")
            or result_dict.get("preprocessing")
            or ""
        )
        info_obj = (
            result_dict.get("info")
            or result_dict.get("processing_info")
            or result_dict.get("processing_details")
            or {}
        )
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
        if progress is not None:
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
        if progress is not None:
            with contextlib.suppress(Exception):
                progress(1.0)
        return vals[0], vals[1], vals[2], vals[3], vals[4], metrics

    # Unknown return; show generic status
    return "", "Upload complete", "", "", "", ""


def start_translation_with_progress(
    target_language,
    pages_to_translate,
    philosophy_mode,
    progress: gr.Progress = gr.Progress(track_tqdm=False),  # noqa: B008
):
    """Start translation and update a subtle progress indicator.

    Returns 4 values to update the UI:
    (progress_status, upload_status, download_btn, progress_timer)
    """
    if progress is not None:
        with contextlib.suppress(Exception):
            progress(0.05, desc="Starting translation")

    try:
        res = start_translation_sync(
            target_language,
            pages_to_translate,
            philosophy_mode,
        )
        if isinstance(res, (list, tuple)) and len(res) >= 4:
            if progress is not None:
                with contextlib.suppress(Exception):
                    progress(0.2, desc="Submitted to backend")
            return tuple(res[:4])
        status, upload_status, is_ready = res
    except Exception as e:
        logging.error("Translation start failed: %s", e, exc_info=True)
        status, upload_status, is_ready = f"❌ Error: {e!s}", "", False

    if progress is not None:
        with contextlib.suppress(Exception):
            progress(0.2, desc="Submitted to backend")

    is_error = "❌" in str(status) or "failed" in str(status).lower()
    timer_active = not is_ready and not is_error

    return (
        status,
        upload_status,
        gr.Button(interactive=is_ready),
        gr.Timer(active=timer_active),
    )


def estimate_cost_ui(file_obj: Any) -> str:
    """Compute and format an itemized GCP budget quote for the uploaded PDF."""
    if file_obj is None:
        return "Please upload a PDF file to calculate a budget quote."
    path = getattr(file_obj, "name", str(file_obj))
    try:
        from services.cost_estimator import GCPCostEstimator

        quote = GCPCostEstimator().estimate_book_cost(Path(path))
        return (
            f"### 📊 Itemized GCP Budget Quote\n\n"
            f"- **Total Pages:** {quote.total_pages}\n"
            f"- **File Size:** {quote.file_size_mb:.2f} MB\n"
            f"- **Document Translation ($0.080/page):** ${quote.base_cost:.2f}\n"
            f"- **7-Day Staging Lifecycle:** ${quote.staging_overhead_cost:.4f}\n"
            f"- **1-Month GCS Retention:** ${quote.storage_cost_1mo:.4f}\n"
            f"- **12-Month GCS Archive:** ${quote.storage_cost_12mo:.4f}\n"
            f"- **Always Free Tier (5 GB):** {'Covered' if quote.free_tier_covered else 'Not covered'}\n\n"
            f"**Total Estimated Cost:** ${quote.total_estimate:.2f} "
            f"(Tolerance Range: ${quote.tolerance_range[0]:.2f} - ${quote.tolerance_range[1]:.2f})\n\n"
            f"*(Calculated in {quote.estimation_time_sec * 1000:.1f} ms)*"
        )
    except Exception as exc:
        return f"❌ Cost estimation failed: {exc}"


def _authenticate_gradio_caller(
    requested_user_id: str,
    auth_token: str = "",
    request: gr.Request | None = None,
) -> None:
    """Verify that the Gradio caller is authenticated and authorized to access requested_user_id.

    - Shared anonymous namespaces ('anonymous', 'default_user', 'local_user') are rejected
      to prevent cross-visitor state collision.
    - When authentication is disabled (is_auth_enabled() is False), permits local dev workflows
      with distinct user identifiers.
    - When authentication is enabled:
      - Rejects unauthenticated requests with PermissionError.
      - Requires non-empty user_id matching requested_user_id for non-admin tokens.
    """
    shared_namespaces = ("anonymous", "default_user", "local_user")
    if requested_user_id.lower() in shared_namespaces:
        raise PermissionError(
            f"Invalid user_id '{requested_user_id}': Shared anonymous namespaces are prohibited "
            "to isolate user credentials, vocabulary, and jobs. Please provide a distinct user identifier."
        )

    from api.auth import UserRole, is_auth_enabled, verify_api_key, verify_jwt_token

    if not is_auth_enabled():
        return

    token = auth_token.strip()
    if (
        not token
        and request is not None
        and hasattr(request, "headers")
        and request.headers
    ):
        token = request.headers.get("x-api-key") or ""
        if not token:
            auth_hdr = request.headers.get("authorization", "")
            if auth_hdr.lower().startswith("bearer "):
                token = auth_hdr[7:].strip()

    if not token:
        raise PermissionError(
            "Authentication required: Please provide an API Key or Bearer Token to access or modify user credentials and vocabulary."
        )

    # 1. Check API Key
    if verify_api_key(token):
        return  # Admin API key has global access

    # 2. Check JWT
    try:
        payload = verify_jwt_token(token)
        role = payload.get("role")
        auth_uid = payload.get("user_id")
        if role == UserRole.ADMIN:
            return
        if not auth_uid or auth_uid != requested_user_id:
            raise PermissionError(
                f"Access denied: Caller identity '{auth_uid}' cannot access or modify resources for '{requested_user_id}'."
            )
    except Exception as exc:
        if isinstance(exc, PermissionError):
            raise
        raise PermissionError(f"Invalid authentication token: {exc}") from exc


def validate_byok_ui(
    user_id: str,
    project_id: str,
    bucket_name: str,
    sa_json: str,
    auth_token: str = "",
    request: gr.Request | None = None,
) -> str:
    """Validate user BYOK credentials via non-billable API calls after enforcing ownership."""
    if (
        not user_id.strip()
        or not project_id.strip()
        or not bucket_name.strip()
        or not sa_json.strip()
    ):
        return "❌ Please enter User ID, Project ID, Bucket Name, and Service Account JSON."
    try:
        _authenticate_gradio_caller(
            user_id.strip(), auth_token=auth_token, request=request
        )
        from services.byok_credentials_manager import BYOKCredentialsManager

        mgr = BYOKCredentialsManager()
        mgr.set_credentials(
            user_id.strip(), project_id.strip(), bucket_name.strip(), sa_json.strip()
        )
        val = mgr.validate_credentials(user_id.strip())
        icon = "✅" if val.status == "VALID" else "❌"
        return (
            f"### {icon} Status: {val.status}\n\n"
            f"- **Cloud Translation API:** {'✅ Passed' if val.translation_check_passed else '❌ Failed'}\n"
            f"- **Cloud Storage Bucket:** {'✅ Passed' if val.storage_check_passed else '❌ Failed'}\n"
            f"- **Details:** {val.error_details or 'All validation checks passed successfully.'}"
        )
    except PermissionError as exc:
        return f"🔒 {exc}"
    except Exception as exc:
        return f"❌ Validation error: {exc}"


def pre_scan_ui(
    user_id: str,
    file_obj: Any,
    auth_token: str = "",
    request: gr.Request | None = None,
) -> tuple[str, str, str]:
    """Pre-scan book PDF for neologisms, Fraktur confidence, and vocabulary recall after enforcing ownership."""
    if not user_id.strip() or file_obj is None:
        return "Please provide User ID and upload a PDF.", "", ""
    path = getattr(file_obj, "name", str(file_obj))
    try:
        _authenticate_gradio_caller(
            user_id.strip(), auth_token=auth_token, request=request
        )
        from services.book_translation_orchestrator import BookTranslationOrchestrator

        orch = BookTranslationOrchestrator()
        res = orch.pre_scan_book(user_id=user_id.strip(), source=Path(path))
        badge = (
            f"### 🔤 Script Assessment & OCR Rating\n\n"
            f"- **Detected Script:** {res.script_analysis.script_type.value}\n"
            f"- **OCR Confidence Rating:** {res.ocr_confidence.confidence_score * 100:.1f}%\n"
            f"- **Fraktur Ratio:** {res.script_analysis.fraktur_ratio * 100:.1f}%\n"
            f"- **Recommended Action:** {res.ocr_confidence.recommended_action}\n"
            f"- **Total Book Pages:** {res.total_pages}\n"
        )
        neologisms = f"**Detected Neologisms ({len(res.detected_neologisms)}):**\n\n"
        for neo in res.detected_neologisms[:15]:
            term = getattr(neo, "term", str(neo))
            neologisms += f"- {term}\n"
        vocab = f"**Auto-Populated from User Terminology ({len(res.prefilled_terms)}):**\n\n"
        for k, v in res.prefilled_terms.items():
            pref = getattr(v, "preferred_translation", str(v))
            vocab += f"- **{k}** ➔ *{pref}*\n"
        return badge, neologisms, vocab
    except PermissionError as exc:
        return f"🔒 {exc}", "", ""
    except Exception as exc:
        return f"❌ Pre-scan failed: {exc}", "", ""


def create_gradio_interface() -> gr.Blocks:
    """Create the advanced Gradio interface for PDF translation with OCR.

    This builds the Blocks UI, wires events, and returns the interface.
    """
    # Load supported languages from config (fallback to defaults)
    languages_path = Path(__file__).parent.parent / "config" / "languages.json"
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
        # -------------------------------------------------------------------
        # Track 5: GCP Migration & Scholarly Studio (TASK-5.2)
        # -------------------------------------------------------------------
        with gr.Accordion(
            "🏛️ GCP Book Translation, BYOK & Scholarly Studio", open=True
        ):
            gr.Markdown(
                "Zero host storage full-length book translation via Google Cloud Document Translation & GCS."
            )

            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 💰 1. Zero-Auth GCP Cost & Storage Estimator")
                    cost_input = gr.File(label="Upload Book PDF", file_types=[".pdf"])
                    calc_quote_btn = gr.Button(
                        "Calculate Budget Quote", variant="secondary"
                    )
                    cost_quote_display = gr.Markdown(
                        "Upload a PDF to view itemized translation and retention costs."
                    )

                    with gr.Accordion(
                        "📘 2. Interactive GCP Onboarding Walkthrough", open=False
                    ):
                        gr.Markdown(
                            "1. Create or select a GCP project (`projects.create`).\n"
                            "2. Enable Cloud Translation API (`translate.googleapis.com`).\n"
                            "3. Create a regional GCS bucket in `us-central1`.\n"
                            "4. Create Service Account with Translation User and Storage Object Admin roles.\n"
                            "5. Generate a JSON key and paste it below.\n\n"
                            "```bash\n"
                            "gcloud services enable translate.googleapis.com storage.googleapis.com\n"
                            "gcloud iam service-accounts create book-translator\n"
                            "```"
                        )

                    gr.Markdown("### 🔑 3. Bring Your Own Key (BYOK) Setup")
                    byok_token = gr.Textbox(
                        label="API Key or Bearer Token",
                        type="password",
                        placeholder="Enter API key or JWT token (or login via session)",
                    )
                    byok_uid = gr.Textbox(label="User ID", value="scholar-01")
                    byok_pid = gr.Textbox(
                        label="GCP Project ID", placeholder="my-gcp-project"
                    )
                    byok_bkt = gr.Textbox(
                        label="GCS Bucket Name", placeholder="my-translation-bucket"
                    )
                    byok_key = gr.Textbox(
                        label="Service Account JSON",
                        placeholder='{"type": "service_account", ...}',
                        lines=2,
                    )
                    validate_key_btn = gr.Button(
                        "Validate Credentials", variant="primary"
                    )
                    byok_status_display = gr.Markdown("Awaiting credentials...")

                with gr.Column():
                    gr.Markdown("### 🔍 4. Pre-Scan & Fraktur Script Confidence")
                    prescan_token = gr.Textbox(
                        label="API Key or Bearer Token",
                        type="password",
                        placeholder="Enter API key or JWT token (or login via session)",
                    )
                    prescan_uid = gr.Textbox(label="User ID", value="scholar-01")
                    prescan_input = gr.File(
                        label="Select Book PDF", file_types=[".pdf"]
                    )
                    run_prescan_btn = gr.Button(
                        "Run Pre-Scan Assessment", variant="primary"
                    )
                    script_badge_display = gr.Markdown("Awaiting pre-scan...")
                    neo_display = gr.Markdown("Neologisms will be displayed here...")
                    vocab_display = gr.Markdown(
                        "Saved user terminology will be displayed here..."
                    )

            calc_quote_btn.click(
                fn=estimate_cost_ui, inputs=[cost_input], outputs=[cost_quote_display]
            )
            validate_key_btn.click(
                fn=validate_byok_ui,
                inputs=[byok_uid, byok_pid, byok_bkt, byok_key, byok_token],
                outputs=[byok_status_display],
            )
            run_prescan_btn.click(
                fn=pre_scan_ui,
                inputs=[prescan_uid, prescan_input, prescan_token],
                outputs=[script_badge_display, neo_display, vocab_display],
            )

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

                # Timer for auto-refreshing progress while translation runs
                progress_timer = gr.Timer(value=1.0, active=False)

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

        # Status update function for manual refresh and timer tick
        def update_status(_progress: "gr.Progress | None" = None):
            if _progress is None:
                _progress = gr.Progress(track_tqdm=False)
            res = get_translation_status()
            if hasattr(res, "message"):
                status = res.message
                is_done = bool(res.is_done)
                is_error = bool(res.is_error)
            elif isinstance(res, (list, tuple)):
                status = res[0]
                is_done = bool(res[2]) if len(res) > 2 else False
                is_error = bool(res[3]) if len(res) > 3 else False
            else:
                status = str(res)
                is_done = False
                is_error = False

            status_str = str(status).lower()
            if not is_error and ("❌" in str(status) or "failed" in status_str):
                is_error = True
            is_idle = (
                "ready for advanced translation" in status_str
                or "idle" in status_str
            )
            is_active = (not is_done) and (not is_error) and (not is_idle)
            return (
                status,
                gr.Button(interactive=is_done),
                gr.Timer(active=is_active),
            )

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
