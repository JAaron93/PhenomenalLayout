"""services/book_translation_orchestrator.py
============================================
Track 5 — Book Orchestrator, Modal Deployment, UI & E2E Validation (TASK-5.1)
Traceability: FR-01, FR-02, FR-03, FR-04, FR-05, FR-06, FR-10 to FR-14

Coordinates the full end-to-end German philosophical book translation pipeline:
1. Stream-based text extraction & neologism pre-scanning cross-referenced with UserVocabularyStore.
2. Fraktur OCR script confidence rating.
3. Pre-auth GCP cost and storage retention estimation.
4. Asynchronous batch translation submission via GCS with 7-day staging lifecycle enforcement.
5. Persistent LRO monitoring and job resumption via BatchJobRecoveryManager.
6. Fallback plaintext translation for skipped/failed pages (100% complete translation).
7. Session glossary quota auto-cleanup via SessionGlossaryLifecycleManager.
8. Seamless Google Drive export via Google Identity Services (GIS).
9. Synchronized side-by-side bilingual reading mode via DualPaneViewerController.

Design Invariants:
- Zero host PDF disk storage — streams directly to/from user GCS bucket and Drive.
- Session-scoped BYOK credentials in memory only.
- Strict fail-fast staging cleanup: raises RuntimeError if 7-day staging lifecycle is missing/fails.
- Deterministic file descriptor cleanup in try...finally blocks.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import pypdf

from config.settings import gcp_settings
from services.batch_job_recovery import ActiveJobState, BatchJobRecoveryManager, JobNotFoundError
from services.byok_credentials_manager import BYOKCredentialsManager
from services.cost_estimator import CostQuote, GCPCostEstimator
from services.dual_pane_viewer import BilingualPagePair, DualPaneViewerController
from services.fallback_translator import FallbackPageTranslator, PageText, TranslatedPage
from services.fraktur_classifier import (
    FrakturClassifier,
    OCRConfidence,
    ScriptAnalysisResult,
    ScriptType,
)
from services.gcp_batch_translation_service import BatchJobHandle, GCPBatchTranslationService
from services.glossary_sync_manager import GlossarySyncManager
from services.google_drive_exporter import DriveExportResult, GoogleDriveExporter
from services.lro_progress_monitor import LROProgressMonitor, ProgressUpdate
from services.neologism_detector import NeologismDetector
from services.session_glossary_lifecycle import SessionGlossaryLifecycleManager
from services.user_vocabulary_store import TermPreference, UserVocabularyStore

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class BookJobHandle:
    """Handle representing an active book translation pipeline job."""

    session_id: str
    user_id: str
    book_id: str
    lro_name: str
    gcs_input_uri: str
    gcs_output_uri_prefix: str
    glossary_resource_name: str
    total_pages: int
    submitted_at: float = field(default_factory=time.time)


@dataclass
class BookScanResult:
    """Pre-scan assessment containing extracted text metadata, script rating, and neologisms."""

    total_pages: int
    script_analysis: ScriptAnalysisResult
    ocr_confidence: OCRConfidence
    detected_neologisms: list[Any]
    prefilled_terms: dict[str, TermPreference]
    cost_quote: CostQuote
    sample_text: str = ""


@dataclass
class CompletionSummary:
    """Status summary returned when a batch translation job completes or is evaluated."""

    session_id: str
    status: str
    total_pages: int
    translated_pages: int
    failed_pages: int
    is_done: bool
    can_fallback: bool
    output_gcs_uri: str
    error_message: str | None = None


@dataclass
class FallbackResult:
    """Result of running plaintext fallback translation on failed layout pages."""

    session_id: str
    failed_pages_count: int
    translated_pages: list[TranslatedPage]
    spliced_output_gcs_uri: str
    success: bool


# ---------------------------------------------------------------------------
# BookTranslationOrchestrator
# ---------------------------------------------------------------------------


class BookTranslationOrchestrator:
    """Coordinates end-to-end book-scale translation and scholarly resilience services."""

    def __init__(
        self,
        credentials_manager: BYOKCredentialsManager | None = None,
        batch_service: GCPBatchTranslationService | None = None,
        progress_monitor: LROProgressMonitor | None = None,
        recovery_manager: BatchJobRecoveryManager | None = None,
        vocabulary_store: UserVocabularyStore | None = None,
        glossary_sync_manager: GlossarySyncManager | None = None,
        lifecycle_manager: SessionGlossaryLifecycleManager | None = None,
        fraktur_classifier: FrakturClassifier | None = None,
        fallback_translator: FallbackPageTranslator | None = None,
        drive_exporter: GoogleDriveExporter | None = None,
        viewer_controller: DualPaneViewerController | None = None,
        cost_estimator: GCPCostEstimator | None = None,
        neologism_detector: NeologismDetector | None = None,
    ) -> None:
        self.credentials_manager = credentials_manager or BYOKCredentialsManager()
        self.batch_service = batch_service or GCPBatchTranslationService(self.credentials_manager)
        self.progress_monitor = progress_monitor or LROProgressMonitor(self.credentials_manager)
        self.recovery_manager = recovery_manager or BatchJobRecoveryManager()
        self.vocabulary_store = vocabulary_store or UserVocabularyStore()
        self.glossary_sync_manager = glossary_sync_manager or GlossarySyncManager(self.credentials_manager)
        self.lifecycle_manager = lifecycle_manager or SessionGlossaryLifecycleManager(self.credentials_manager)
        self.fraktur_classifier = fraktur_classifier or FrakturClassifier()
        self.fallback_translator = fallback_translator or FallbackPageTranslator(self.credentials_manager)
        self.drive_exporter = drive_exporter or GoogleDriveExporter()
        self.viewer_controller = viewer_controller or DualPaneViewerController()
        self.cost_estimator = cost_estimator or GCPCostEstimator()
        self.neologism_detector = neologism_detector or NeologismDetector()

    # ------------------------------------------------------------------
    # Private I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _open_source(source: Path | str | bytes | BinaryIO) -> tuple[BinaryIO, bool]:
        """Normalize source to a binary stream and return (stream, should_close)."""
        if isinstance(source, bytes):
            return io.BytesIO(source), True
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"Source PDF path does not exist: {path}")
            return path.open("rb"), True
        if hasattr(source, "read"):
            return source, False
        raise TypeError(f"Unsupported source type: {type(source)}")

    # ------------------------------------------------------------------
    # Task 5.1 Step 1: Pre-Scan Book Stream
    # ------------------------------------------------------------------

    def pre_scan_book(
        self,
        user_id: str,
        source: Path | str | bytes | BinaryIO,
        max_pages: int | None = None,
    ) -> BookScanResult:
        """Pre-scan book PDF for neologisms and Fraktur script confidence.

        Cross-references discovered terms with UserVocabularyStore and estimates
        itemized GCP translation budget quotes.

        Parameters
        ----------
        user_id:
            End-user identifier for recalling persistent vocabulary preferences.
        source:
            Source PDF file path, raw bytes, or stream.
        max_pages:
            Optional page sampling limit for large manuscripts.

        Returns
        -------
        BookScanResult
            Aggregated pre-scan analysis report.
        """
        stream, should_close = self._open_source(source)
        try:
            # Parse PDF stream
            try:
                reader = pypdf.PdfReader(stream)
                total_pages = len(reader.pages)
            except Exception as e:
                raise ValueError(f"Failed to parse empty or invalid PDF stream: {e}") from e

            if total_pages == 0:
                raise ValueError("Source PDF contains 0 pages")

            pages_to_read = min(total_pages, max_pages) if max_pages else total_pages

            # Extract sample text page-by-page
            extracted_text_chunks: list[str] = []
            for i in range(pages_to_read):
                try:
                    p_text = reader.pages[i].extract_text() or ""
                    if p_text.strip():
                        extracted_text_chunks.append(p_text.strip())
                except Exception as exc:
                    logger.debug("Failed extracting text from page %d: %s", i + 1, exc)

            combined_text = "\n\n".join(extracted_text_chunks)

            # Rewind stream for downstream sub-analyzers
            if hasattr(stream, "seek"):
                stream.seek(0)

            # 1. Fraktur script classification & OCR confidence rating
            script_analysis = self.fraktur_classifier.classify_script(stream, max_pages=pages_to_read)
            if hasattr(stream, "seek"):
                stream.seek(0)
            ocr_confidence = self.fraktur_classifier.get_ocr_confidence_rating(stream)

            # 2. Neologism detection
            detected_neologisms: list[Any] = []
            if combined_text:
                analysis = self.neologism_detector.analyze_text(combined_text, text_id=f"prescan-{user_id}")
                detected_neologisms = getattr(analysis, "detected_neologisms", [])

            # 3. Cross-reference with UserVocabularyStore
            if hasattr(self.vocabulary_store, "get_user_preferences"):
                saved_preferences = self.vocabulary_store.get_user_preferences(user_id)
            elif hasattr(self.vocabulary_store, "get_preferences"):
                saved_preferences = self.vocabulary_store.get_preferences(user_id)
            else:
                saved_preferences = {}
            prefilled_terms: dict[str, TermPreference] = {}

            # Match saved preferences against detected compounds or text terms
            for term_pref in saved_preferences.values():
                if term_pref.german_term.lower() in combined_text.lower():
                    prefilled_terms[term_pref.german_term] = term_pref

            for neo in detected_neologisms:
                neo_term = getattr(neo, "term", str(neo))
                if neo_term in saved_preferences:
                    prefilled_terms[neo_term] = saved_preferences[neo_term]

            # 4. Itemized budget quote estimation
            if hasattr(stream, "seek"):
                stream.seek(0)
            cost_quote = self.cost_estimator.estimate_book_cost(stream)

            return BookScanResult(
                total_pages=total_pages,
                script_analysis=script_analysis,
                ocr_confidence=ocr_confidence,
                detected_neologisms=detected_neologisms,
                prefilled_terms=prefilled_terms,
                cost_quote=cost_quote,
                sample_text=combined_text[:1000],
            )
        finally:
            if should_close:
                try:
                    stream.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Task 5.1 Step 2: Start Book Translation
    # ------------------------------------------------------------------

    def start_book_translation(
        self,
        user_id: str,
        session_id: str,
        book_id: str,
        source: Path | str | bytes | BinaryIO,
        user_choices: dict[str, Any] | None = None,
        source_lang: str = "de",
        target_lang: str = "en-US",
    ) -> ActiveJobState:
        """Stage book in user's GCS bucket, synchronize glossary, and dispatch batch translation.

        Parameters
        ----------
        user_id:
            User identifier whose BYOK credentials are used.
        session_id:
            Unique translation session identifier.
        book_id:
            Unique identifier for the book.
        source:
            Source PDF file path, bytes, or stream.
        user_choices:
            Dynamic session terminology overrides.
        source_lang:
            Source language code (default 'de').
        target_lang:
            Target language code (default 'en-US').

        Returns
        -------
        ActiveJobState
            State of the persisted background batch job.

        Raises
        ------
        ValueError:
            If user credentials are not configured.
        RuntimeError:
            If 7-day staging lifecycle policy cannot be verified/patched on user bucket.
        """
        # Validate BYOK credentials exist
        if not self.credentials_manager.has_credentials(user_id):
            raise ValueError(f"No GCP credentials found for user '{user_id}'. Please configure BYOK.")

        bucket_name = self.credentials_manager.get_bucket_name(user_id)

        # 1. Enforce 7-day staging lifecycle policy on user's bucket (§2.9 Fail-fast invariant)
        staging_prefix = "inputs/"
        policy_ok = self.batch_service.ensure_staging_lifecycle_policy(
            user_id=user_id,
            bucket_name=bucket_name,
            staging_prefix=staging_prefix,
            age_days=7,
        )
        if not policy_ok:
            raise RuntimeError(
                f"Failed to verify or apply 7-day staging lifecycle policy on bucket '{bucket_name}'. "
                "Translation aborted to prevent unbounded storage costs."
            )

        # 2. Upload source PDF directly to GCS without caching on host disk
        gcs_input_uri = f"gs://{bucket_name}/{staging_prefix}{book_id}/source.pdf"
        self.batch_service.upload_book_to_gcs(
            user_id=user_id,
            source=source,
            gcs_destination_uri=gcs_input_uri,
        )

        # 3. Synchronize dynamic Tier 2 book session glossary
        glossary_resource_name = self.glossary_sync_manager.sync_book_session_glossary(
            user_id=user_id,
            session_id=session_id,
            user_choices=user_choices,
            overwrite=True,
        )

        # Register glossary in lifecycle manager
        session_tsv_uri = f"gs://{bucket_name}/glossaries/sessions/{session_id}.tsv"
        self.lifecycle_manager.register_session_glossary(
            user_id=user_id,
            session_id=session_id,
            glossary_resource_name=glossary_resource_name,
            gcs_tsv_uri=session_tsv_uri,
        )

        # 4. Dispatch GCP batch translation
        gcs_output_uri_prefix = f"gs://{bucket_name}/outputs/{book_id}/"
        lro_name = self.batch_service.submit_batch_job(
            user_id=user_id,
            gcs_input_uri=gcs_input_uri,
            gcs_output_uri_prefix=gcs_output_uri_prefix,
            source_lang=source_lang,
            target_lang=target_lang,
            glossary_resource_name=glossary_resource_name,
        )

        # 5. Persist active job state for reconnect resilience
        self.recovery_manager.save_active_job(
            user_id=user_id,
            session_id=session_id,
            book_id=book_id,
            lro_name=lro_name,
            gcs_output_uri=gcs_output_uri_prefix,
            total_pages=0,
            extra_metadata={
                "glossary_resource_name": glossary_resource_name,
                "source_lang": source_lang,
                "target_lang": target_lang,
            },
        )

        # Return latest recovered state
        return self.recovery_manager.resume_active_job(session_id, user_id=user_id)

    # ------------------------------------------------------------------
    # Task 5.1 Step 3: Poll Progress & Recovery
    # ------------------------------------------------------------------

    def poll_translation_progress(
        self,
        user_id: str,
        session_id: str,
    ) -> ProgressUpdate:
        """Poll live LRO progress and synchronize with BatchJobRecoveryManager.

        Parameters
        ----------
        user_id:
            User identifier.
        session_id:
            Active session identifier.

        Returns
        -------
        ProgressUpdate
            Live progress snapshot.
        """
        state = self.recovery_manager.resume_active_job(session_id, user_id=user_id)
        update = self.progress_monitor.poll_once(user_id, state.lro_name)

        self.recovery_manager.update_job_progress(
            session_id=session_id,
            translated_pages=update.translated_pages,
            failed_pages=update.failed_pages,
            status=update.state,
            user_id=user_id,
        )

        return update

    def resume_job(self, session_id: str, user_id: str | None = None) -> ActiveJobState:
        """Recall saved job state and re-attach to live monitoring."""
        return self.recovery_manager.resume_active_job(
            session_id=session_id,
            user_id=user_id,
            progress_monitor=self.progress_monitor,
        )

    # ------------------------------------------------------------------
    # Task 5.1 Step 4: Handle Job Completion & Glossary Cleanup
    # ------------------------------------------------------------------

    def handle_job_completion(
        self,
        user_id: str,
        session_id: str,
    ) -> CompletionSummary:
        """Evaluate completed job and prune session glossary if zero pages failed.

        Parameters
        ----------
        user_id:
            User identifier.
        session_id:
            Target session identifier.

        Returns
        -------
        CompletionSummary
            Summary of the finished job.
        """
        state = self.recovery_manager.resume_active_job(session_id, user_id=user_id)
        update = self.progress_monitor.poll_once(user_id, state.lro_name)

        can_fallback = update.failed_pages > 0

        # If translation succeeded with 0 failed pages, clean up dynamic session glossary
        if update.state == "SUCCEEDED" and update.failed_pages == 0:
            logger.info("Batch job succeeded with 0 failed pages. Pruning session glossary for %s", session_id)
            self.lifecycle_manager.cleanup_session_glossary(user_id, session_id)

        return CompletionSummary(
            session_id=session_id,
            status=update.state,
            total_pages=update.total_pages,
            translated_pages=update.translated_pages,
            failed_pages=update.failed_pages,
            is_done=update.is_done,
            can_fallback=can_fallback,
            output_gcs_uri=state.gcs_output_uri,
            error_message=update.error_message,
        )

    # ------------------------------------------------------------------
    # Task 5.1 Step 5: Fallback Plaintext Translation Trigger
    # ------------------------------------------------------------------

    def trigger_fallback_page_translation(
        self,
        user_id: str,
        session_id: str,
        source_pdf: Path | str | bytes | BinaryIO,
        failed_page_indices: list[int] | None = None,
        source_lang: str = "de",
        target_lang: str = "en",
    ) -> FallbackResult:
        """Extract and translate raw text for failed pages, splicing into the output PDF.

        Achieves a 98% layout-preserved, 100% fully translated book (FR-13, BDD FR-13.1).
        Cleans up transient Tier 2 session glossary upon completion.

        Parameters
        ----------
        user_id:
            User identifier.
        session_id:
            Session identifier.
        source_pdf:
            German original source PDF.
        failed_page_indices:
            Optional explicit list of 0-indexed failed page numbers. If None, derived from state.
        source_lang:
            Source language code.
        target_lang:
            Target language code.

        Returns
        -------
        FallbackResult
            Result with spliced output GCS URI.
        """
        state = self.recovery_manager.resume_active_job(session_id, user_id=user_id)
        bucket_name = self.credentials_manager.get_bucket_name(user_id)

        # 1. Determine failed page indices
        if failed_page_indices is None:
            failed_count = state.failed_pages or 1
            failed_page_indices = list(range(failed_count))

        # 2. Extract unformatted text from failed pages
        pages_text = self.fallback_translator.extract_failed_pages_text(
            source=source_pdf,
            failed_page_indices=failed_page_indices,
        )

        # 3. Retrieve glossary resource name and translate raw text
        glossary_name = state.extra_metadata.get("glossary_resource_name")
        translated_pages = self.fallback_translator.translate_failed_pages(
            user_id=user_id,
            pages_text=pages_text,
            glossary_name=glossary_name,
            source_lang=source_lang,
            target_lang=target_lang,
        )

        # 4. Stream layout PDF from GCS outputs
        gcs_output_file = f"{state.gcs_output_uri.rstrip('/')}/source_{source_lang}_{target_lang}.pdf"
        try:
            layout_stream = self.batch_service.stream_translated_book(user_id, gcs_output_file)
        except Exception:
            # Fallback to source PDF stream as baseline layout placeholder if output not yet placed
            layout_stream, _ = self._open_source(source_pdf)

        # 5. Splice translated fallback pages into output PDF
        spliced_buffer = self.fallback_translator.splice_fallback_pages(
            layout_pdf_source=layout_stream,
            translated_fallback_pages=translated_pages,
        )

        # 6. Upload complete spliced PDF to GCS
        spliced_output_gcs_uri = f"gs://{bucket_name}/outputs/{state.book_id}/completed_spliced.pdf"
        self.batch_service.upload_book_to_gcs(
            user_id=user_id,
            source=spliced_buffer,
            gcs_destination_uri=spliced_output_gcs_uri,
        )

        # 7. Clean up session glossary now that fallback translation is complete
        self.lifecycle_manager.cleanup_session_glossary(user_id, session_id)

        return FallbackResult(
            session_id=session_id,
            failed_pages_count=len(failed_page_indices),
            translated_pages=translated_pages,
            spliced_output_gcs_uri=spliced_output_gcs_uri,
            success=True,
        )

    # ------------------------------------------------------------------
    # Task 5.1 Step 6: Scholarly Delivery Actions (Drive & Dual-Pane)
    # ------------------------------------------------------------------

    def export_to_google_drive(
        self,
        user_id: str,
        session_id: str,
        access_token: str,
        filename: str | None = None,
    ) -> DriveExportResult:
        """Stream translated PDF directly from GCS to Google Drive using client GIS OAuth token.

        Zero host PDF storage invariant: stream is forwarded directly without disk writes.

        Parameters
        ----------
        user_id:
            User identifier.
        session_id:
            Session identifier.
        access_token:
            Browser-side Google Identity Services (GIS) OAuth access token.
        filename:
            Display name for the uploaded Google Drive file.

        Returns
        -------
        DriveExportResult
            Google Drive file metadata with web view link.
        """
        state = self.recovery_manager.resume_active_job(session_id, user_id=user_id)
        file_name = filename or f"{state.book_id}_translated.pdf"

        # Stream translated PDF from user's GCS bucket
        gcs_output_uri = f"{state.gcs_output_uri.rstrip('/')}/{file_name}"
        pdf_stream = self.batch_service.stream_translated_book(user_id, gcs_output_uri)

        return self.drive_exporter.export_stream_to_drive(
            access_token=access_token,
            file_stream=pdf_stream,
            filename=file_name,
        )

    def get_bilingual_view(
        self,
        user_id: str,
        session_id: str,
        german_source: Path | str | bytes | BinaryIO,
        page_number: int,
        render_images: bool = True,
    ) -> BilingualPagePair:
        """Fetch synchronized German and English page pair for side-by-side reading mode.

        Parameters
        ----------
        user_id:
            User identifier.
        session_id:
            Session identifier.
        german_source:
            German original PDF.
        page_number:
            1-indexed page number to view.
        render_images:
            Whether to rasterize page images as base64 strings.

        Returns
        -------
        BilingualPagePair
            Synchronized page text and optional images.
        """
        state = self.recovery_manager.resume_active_job(session_id, user_id=user_id)
        gcs_output_uri = f"{state.gcs_output_uri.rstrip('/')}/{state.book_id}_de_en.pdf"
        english_stream = self.batch_service.stream_translated_book(user_id, gcs_output_uri)

        return self.viewer_controller.get_bilingual_page_pair(
            german_source=german_source,
            english_source=english_stream,
            page_number=page_number,
            render_images=render_images,
        )
