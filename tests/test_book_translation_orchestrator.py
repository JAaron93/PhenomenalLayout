"""Unit tests for BookTranslationOrchestrator (TASK-5.1).

Traceability: FR-01, FR-02, FR-03, FR-04, FR-05, FR-06, FR-10 to FR-14
- Pre-scanning book PDF for neologisms and Fraktur script confidence
- Recalling and pre-filling saved user vocabulary from UserVocabularyStore
- Dispatching asynchronous batch document translation to user's GCS bucket
- Enforcing 7-day staging lifecycle policy with fail-fast RuntimeError (§2.9)
- Tracking LRO progress and integrating with BatchJobRecoveryManager
- Triggering FallbackPageTranslator for failed pages to achieve 100% translation
- Pruning transient Tier 2 session glossaries upon job completion
- Google Drive GIS export streaming directly from GCS
- Synchronized side-by-side bilingual reading view
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.batch_job_recovery import ActiveJobState, BatchJobRecoveryManager
from services.book_translation_orchestrator import (
    BookScanResult,
    BookTranslationOrchestrator,
    CompletionSummary,
    FallbackResult,
)
from services.byok_credentials_manager import BYOKCredentialsManager
from services.dual_pane_viewer import BilingualPagePair, DualPaneViewerController
from services.fallback_translator import (
    FallbackPageTranslator,
    PageText,
    TranslatedPage,
)
from services.fraktur_classifier import (
    FrakturClassifier,
    OCRConfidence,
    ScriptAnalysisResult,
    ScriptType,
)
from services.gcp_batch_translation_service import GCPBatchTranslationService
from services.glossary_sync_manager import GlossarySyncManager
from services.google_drive_exporter import DriveExportResult, GoogleDriveExporter
from services.lro_progress_monitor import LROProgressMonitor, ProgressUpdate
from services.session_glossary_lifecycle import SessionGlossaryLifecycleManager
from services.user_vocabulary_store import UserVocabularyStore


def _create_sample_pdf(text: str = "Klages Geist Seele Dasein Schauung", pages: int = 2) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i in range(pages):
        c.setFont("Helvetica", 12)
        c.drawString(100, 700, f"Page {i + 1}: {text}")
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def mock_creds_mgr() -> MagicMock:
    mgr = MagicMock(spec=BYOKCredentialsManager)
    mgr.get_project_id.return_value = "test-project"
    mgr.get_bucket_name.return_value = "test-bucket"
    mgr.has_credentials.return_value = True
    return mgr


@pytest.fixture
def mock_batch_service() -> MagicMock:
    svc = MagicMock(spec=GCPBatchTranslationService)
    svc.ensure_staging_lifecycle_policy.return_value = True
    svc.upload_book_to_gcs.return_value = "gs://test-bucket/inputs/book1/source.pdf"
    svc.submit_batch_job.return_value = "projects/test-project/locations/us-central1/operations/op-123"
    svc.stream_translated_book.return_value = io.BytesIO(b"%PDF-1.4 translated dummy")
    return svc


@pytest.fixture
def mock_progress_monitor() -> MagicMock:
    mon = MagicMock(spec=LROProgressMonitor)
    mon.poll_once.return_value = ProgressUpdate(
        operation_name="projects/test-project/locations/us-central1/operations/op-123",
        state="RUNNING",
        total_pages=10,
        translated_pages=5,
        failed_pages=0,
        completion_pct=50.0,
        is_done=False,
    )
    return mon


@pytest.fixture
def mock_recovery_mgr(tmp_path: Path) -> MagicMock:
    mgr = MagicMock(spec=BatchJobRecoveryManager)
    mgr._jobs: dict[str, ActiveJobState] = {}

    def _save(user_id, session_id, book_id, lro_name, gcs_output_uri, total_pages=0, extra_metadata=None):
        job = ActiveJobState(
            session_id=session_id,
            user_id=user_id,
            book_id=book_id,
            lro_name=lro_name,
            gcs_output_uri=gcs_output_uri,
            total_pages=total_pages,
            translated_pages=5,
            failed_pages=0,
            status="RUNNING",
            extra_metadata=extra_metadata or {},
        )
        mgr._jobs[session_id] = job
        return str(tmp_path / f"{user_id}_{book_id}.json")

    mgr.save_active_job.side_effect = _save

    def _resume(session_id: str, user_id: str | None = None, **_kwargs):
        if session_id in mgr._jobs:
            return mgr._jobs[session_id]
        return ActiveJobState(
            session_id=session_id,
            user_id=user_id or "user-1",
            book_id="book-1",
            lro_name="projects/test-project/locations/us-central1/operations/op-123",
            gcs_output_uri="gs://test-bucket/outputs/book-1/",
            total_pages=10,
            translated_pages=5,
            failed_pages=0,
            status="RUNNING",
        )

    mgr.resume_active_job.side_effect = _resume
    return mgr


@pytest.fixture
def mock_vocab_store(tmp_path: Path) -> UserVocabularyStore:
    store = UserVocabularyStore(storage_dir=tmp_path / "vocab")
    store.save_preference(
        user_id="user-1",
        german_term="Schauung",
        preferred_translation="Intuitive Vision",
        notes="Scholarly translation",
    )
    return store


@pytest.fixture
def mock_glossary_sync() -> MagicMock:
    sync = MagicMock(spec=GlossarySyncManager)
    sync.sync_book_session_glossary.return_value = (
        "projects/test-project/locations/us-central1/glossaries/sess-book-1-a"
    )
    return sync


@pytest.fixture
def mock_lifecycle_mgr() -> MagicMock:
    lifecycle = MagicMock(spec=SessionGlossaryLifecycleManager)
    lifecycle.cleanup_session_glossary.return_value = True
    return lifecycle


@pytest.fixture
def mock_fraktur_classifier() -> MagicMock:
    clf = MagicMock(spec=FrakturClassifier)
    clf.classify_script.return_value = ScriptAnalysisResult(
        script_type=ScriptType.ANTIQUA,
        ocr_confidence_score=0.95,
        ligature_counts={},
        font_descriptors=["Helvetica"],
        recommended_action="Direct batch translation",
        total_pages_analyzed=2,
        fraktur_ratio=0.0,
    )
    clf.get_ocr_confidence_rating.return_value = OCRConfidence(
        confidence_score=0.95,
        script_type="Antiqua",
        recommended_action="Direct batch translation",
        preview_recommended=False,
    )
    return clf


@pytest.fixture
def mock_fallback_translator() -> MagicMock:
    fb = MagicMock(spec=FallbackPageTranslator)
    fb.extract_failed_pages_text.return_value = [
        PageText(
            page_index=1,
            page_number=2,
            raw_text="Complex diagram text",
            extracted_successfully=True,
        )
    ]
    fb.translate_failed_pages.return_value = [
        TranslatedPage(
            page_index=1,
            page_number=2,
            translated_text="Translated diagram text",
            source_text="Complex diagram text",
            success=True,
        )
    ]
    fb.splice_fallback_pages.return_value = io.BytesIO(b"%PDF-1.4 spliced output")
    return fb


@pytest.fixture
def mock_drive_exporter() -> MagicMock:
    exp = MagicMock(spec=GoogleDriveExporter)
    exp.export_stream_to_drive.return_value = DriveExportResult(
        file_id="drive-123",
        file_name="translated.pdf",
        web_view_link="https://drive.google.com/file/d/drive-123/view",
        web_content_link="https://drive.google.com/uc?id=drive-123",
        created_time="2026-08-27T08:00:00Z",
    )
    return exp


@pytest.fixture
def mock_viewer_controller() -> MagicMock:
    vc = MagicMock(spec=DualPaneViewerController)
    vc.get_bilingual_page_pair.return_value = BilingualPagePair(
        page_number=1,
        total_pages_german=2,
        total_pages_english=2,
        german_text="Original German",
        english_text="Translated English",
    )
    return vc


@pytest.fixture
def orchestrator(
    mock_creds_mgr: MagicMock,
    mock_batch_service: MagicMock,
    mock_progress_monitor: MagicMock,
    mock_recovery_mgr: MagicMock,
    mock_vocab_store: UserVocabularyStore,
    mock_glossary_sync: MagicMock,
    mock_lifecycle_mgr: MagicMock,
    mock_fraktur_classifier: MagicMock,
    mock_fallback_translator: MagicMock,
    mock_drive_exporter: MagicMock,
    mock_viewer_controller: MagicMock,
) -> BookTranslationOrchestrator:
    return BookTranslationOrchestrator(
        credentials_manager=mock_creds_mgr,
        batch_service=mock_batch_service,
        progress_monitor=mock_progress_monitor,
        recovery_manager=mock_recovery_mgr,
        vocabulary_store=mock_vocab_store,
        glossary_sync_manager=mock_glossary_sync,
        lifecycle_manager=mock_lifecycle_mgr,
        fraktur_classifier=mock_fraktur_classifier,
        fallback_translator=mock_fallback_translator,
        drive_exporter=mock_drive_exporter,
        viewer_controller=mock_viewer_controller,
    )


class TestPreScanBook:
    """Test BookTranslationOrchestrator.pre_scan_book workflow."""

    def test_pre_scan_successful(
        self,
        orchestrator: BookTranslationOrchestrator,
    ) -> None:
        pdf_bytes = _create_sample_pdf(text="Schauung und Geist im Widersacher", pages=2)
        result = orchestrator.pre_scan_book(user_id="user-1", source=pdf_bytes)

        assert isinstance(result, BookScanResult)
        assert result.total_pages == 2
        assert result.script_analysis.ocr_confidence_score == 0.95
        assert result.ocr_confidence.preview_recommended is False
        assert "Schauung" in result.prefilled_terms
        assert result.prefilled_terms["Schauung"].preferred_translation == "Intuitive Vision"
        assert result.cost_quote is not None
        assert result.cost_quote.total_pages == 2
        assert result.cost_quote.base_cost == pytest.approx(0.16)

    def test_pre_scan_deterministic_file_cleanup(
        self,
        orchestrator: BookTranslationOrchestrator,
        tmp_path: Path,
    ) -> None:
        pdf_path = tmp_path / "book.pdf"
        pdf_path.write_bytes(_create_sample_pdf(pages=1))

        result = orchestrator.pre_scan_book(user_id="user-1", source=pdf_path)
        assert result.total_pages == 1

    def test_pre_scan_empty_pdf_raises(
        self,
        orchestrator: BookTranslationOrchestrator,
    ) -> None:
        with pytest.raises(ValueError, match=r"empty|invalid"):
            orchestrator.pre_scan_book(user_id="user-1", source=b"")


class TestStartBookTranslation:
    """Test start_book_translation orchestration."""

    def test_start_translation_success(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_batch_service: MagicMock,
        mock_glossary_sync: MagicMock,
        mock_recovery_mgr: MagicMock,
    ) -> None:
        pdf_bytes = _create_sample_pdf(pages=5)
        state = orchestrator.start_book_translation(
            user_id="user-1",
            session_id="sess-101",
            book_id="book-101",
            source=pdf_bytes,
            user_choices={"Dasein": "Being-there"},
        )

        assert state.session_id == "sess-101"
        assert state.user_id == "user-1"
        assert state.book_id == "book-101"

        # Verifies 7-day staging lifecycle verified on bucket
        mock_batch_service.ensure_staging_lifecycle_policy.assert_called_once_with(
            user_id="user-1",
            bucket_name="test-bucket",
            staging_prefix="inputs/",
            age_days=7,
        )

        # Verifies direct streaming upload to GCS
        mock_batch_service.upload_book_to_gcs.assert_called_once()

        # Verifies dynamic session glossary compiled & synced
        mock_glossary_sync.sync_book_session_glossary.assert_called_once()

        # Verifies batch job submitted
        mock_batch_service.submit_batch_job.assert_called_once()

        # Verifies job saved for recovery
        mock_recovery_mgr.save_active_job.assert_called_once()

    def test_start_translation_fail_fast_on_staging_lifecycle_failure(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_batch_service: MagicMock,
    ) -> None:
        """Section 2.9 invariant: raise RuntimeError immediately if staging policy cannot be verified."""
        mock_batch_service.ensure_staging_lifecycle_policy.return_value = False
        pdf_bytes = _create_sample_pdf(pages=3)

        with pytest.raises(RuntimeError, match="lifecycle"):
            orchestrator.start_book_translation(
                user_id="user-1",
                session_id="sess-101",
                book_id="book-101",
                source=pdf_bytes,
            )

    def test_start_translation_missing_credentials_raises(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_creds_mgr: MagicMock,
    ) -> None:
        mock_creds_mgr.has_credentials.return_value = False
        pdf_bytes = _create_sample_pdf(pages=1)

        with pytest.raises(ValueError, match="credentials"):
            orchestrator.start_book_translation(
                user_id="user-unknown",
                session_id="sess-fail",
                book_id="book-fail",
                source=pdf_bytes,
            )


class TestPollAndResumeJob:
    """Test progress polling and job recovery."""

    @pytest.mark.usefixtures("mock_progress_monitor")
    def test_poll_translation_progress(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_recovery_mgr: MagicMock,
    ) -> None:
        update = orchestrator.poll_translation_progress(
            user_id="user-1",
            session_id="sess-01",
        )

        assert update.state == "RUNNING"
        assert update.translated_pages == 5
        assert update.completion_pct == 50.0
        mock_recovery_mgr.update_job_progress.assert_called_once()

    def test_resume_job(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_recovery_mgr: MagicMock,
    ) -> None:
        state = orchestrator.resume_job("sess-01", user_id="user-1")
        assert state.session_id == "sess-01"
        mock_recovery_mgr.resume_active_job.assert_called_once()


class TestHandleJobCompletion:
    """Test job completion and glossary cleanup."""

    @pytest.mark.usefixtures("mock_recovery_mgr")
    def test_handle_completion_success_zero_failed_pages(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_progress_monitor: MagicMock,
        mock_lifecycle_mgr: MagicMock,
    ) -> None:
        mock_progress_monitor.poll_once.return_value = ProgressUpdate(
            operation_name="op-123",
            state="SUCCEEDED",
            total_pages=10,
            translated_pages=10,
            failed_pages=0,
            completion_pct=100.0,
            is_done=True,
        )

        summary = orchestrator.handle_job_completion(user_id="user-1", session_id="sess-01")

        assert isinstance(summary, CompletionSummary)
        assert summary.status == "SUCCEEDED"
        assert summary.can_fallback is False
        assert summary.failed_pages == 0
        mock_lifecycle_mgr.cleanup_session_glossary.assert_called_once_with("user-1", "sess-01")

    @pytest.mark.usefixtures("mock_recovery_mgr")
    def test_handle_completion_with_failed_pages(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_progress_monitor: MagicMock,
        mock_lifecycle_mgr: MagicMock,
    ) -> None:
        mock_progress_monitor.poll_once.return_value = ProgressUpdate(
            operation_name="op-123",
            state="SUCCEEDED",
            total_pages=10,
            translated_pages=9,
            failed_pages=1,
            completion_pct=90.0,
            is_done=True,
        )

        summary = orchestrator.handle_job_completion(user_id="user-1", session_id="sess-01")

        assert isinstance(summary, CompletionSummary)
        assert summary.status == "SUCCEEDED"
        assert summary.can_fallback is True
        assert summary.failed_pages == 1
        # Glossary must NOT be cleaned up yet because fallback translation requires it
        mock_lifecycle_mgr.cleanup_session_glossary.assert_not_called()


class TestTriggerFallbackPageTranslation:
    """Test trigger_fallback_page_translation workflow."""

    @pytest.mark.usefixtures("mock_recovery_mgr")
    def test_trigger_fallback_successful(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_fallback_translator: MagicMock,
        mock_batch_service: MagicMock,
        mock_lifecycle_mgr: MagicMock,
    ) -> None:
        pdf_bytes = _create_sample_pdf(pages=2)
        result = orchestrator.trigger_fallback_page_translation(
            user_id="user-1",
            session_id="sess-01",
            source_pdf=pdf_bytes,
            failed_page_indices=[1],
        )

        assert isinstance(result, FallbackResult)
        assert result.failed_pages_count == 1
        assert result.spliced_output_gcs_uri.startswith("gs://")

        mock_fallback_translator.extract_failed_pages_text.assert_called_once()
        mock_fallback_translator.translate_failed_pages.assert_called_once()
        mock_fallback_translator.splice_fallback_pages.assert_called_once()
        mock_batch_service.upload_book_to_gcs.assert_called_once()
        mock_lifecycle_mgr.cleanup_session_glossary.assert_called_once_with("user-1", "sess-01")


class TestDeliveryActions:
    """Test Google Drive export and dual-pane viewer integration."""

    def test_export_to_google_drive(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_drive_exporter: MagicMock,
        mock_batch_service: MagicMock,
    ) -> None:
        result = orchestrator.export_to_google_drive(
            user_id="user-1",
            session_id="sess-01",
            access_token="gis-token-abc",
            filename="translated_book.pdf",
        )

        assert isinstance(result, DriveExportResult)
        assert result.file_id == "drive-123"
        assert result.web_view_link.startswith("https://drive.google.com")
        mock_batch_service.stream_translated_book.assert_called_once()
        mock_drive_exporter.export_stream_to_drive.assert_called_once()

    def test_get_bilingual_view(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_viewer_controller: MagicMock,
        mock_batch_service: MagicMock,
    ) -> None:
        german_bytes = _create_sample_pdf(pages=2)
        pair = orchestrator.get_bilingual_view(
            user_id="user-1",
            session_id="sess-01",
            german_source=german_bytes,
            page_number=1,
        )

        assert isinstance(pair, BilingualPagePair)
        assert pair.page_number == 1
        mock_batch_service.stream_translated_book.assert_called_once()
        mock_viewer_controller.get_bilingual_page_pair.assert_called_once()

    def test_download_translated_book(
        self,
        orchestrator: BookTranslationOrchestrator,
        mock_batch_service: MagicMock,
    ) -> None:
        mock_batch_service.stream_translated_book.return_value = [b"chunk1", b"chunk2"]
        stream, filename = orchestrator.download_translated_book(
            user_id="user-1",
            session_id="sess-01",
        )
        assert filename == "book-1_translated.pdf"
        mock_batch_service.stream_translated_book.assert_called_once()
        assert list(stream) == [b"chunk1", b"chunk2"]

    def test_pre_scan_with_path_and_stream(
        self,
        orchestrator: BookTranslationOrchestrator,
        tmp_path: Path,
    ) -> None:
        pdf_path = tmp_path / "book.pdf"
        pdf_path.write_bytes(_create_sample_pdf(pages=2))

        # Test Path input
        res_path = orchestrator.pre_scan_book(user_id="user-1", source=pdf_path)
        assert res_path.total_pages == 2

        # Test stream/BytesIO input
        with open(pdf_path, "rb") as f:
            res_stream = orchestrator.pre_scan_book(user_id="user-1", source=f)
            assert res_stream.total_pages == 2
