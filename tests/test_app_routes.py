"""Unit and integration tests for FastAPI app routes and UI endpoints (TASK-5.2).

Traceability: FR-01 to FR-15
1. Zero-Auth Cost Estimator Widget (/api/v1/cost/estimate)
2. Interactive GCP Onboarding Walkthrough Guide (/api/v1/byok/onboarding-guide)
3. BYOK Setup Panel & Dual Validation (/api/v1/byok/credentials, /api/v1/byok/validate)
4. Pre-Scan View with Fraktur OCR Rating badge (/api/v1/book/pre-scan)
5. Terminology Memory Table (/api/v1/vocabulary/{user_id})
6. Live Batch LRO Progress & Recovery (/api/v1/book/translate, /api/v1/book/status/{session_id}, /api/v1/book/resume/{session_id})
7. Scholarly Delivery Actions (Drive GIS export, direct download, fallback translation, dual-pane view)
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from api.auth import UserRole
from api.routes import api_router
from services.batch_job_recovery import ActiveJobState
from services.book_translation_orchestrator import (
    BookScanResult,
    CompletionSummary,
    FallbackResult,
)
from services.byok_credentials_manager import ValidationResult
from services.cost_estimator import CostQuote
from services.dual_pane_viewer import BilingualPagePair
from services.fraktur_classifier import OCRConfidence, ScriptAnalysisResult, ScriptType
from services.google_drive_exporter import DriveExportResult
from services.lro_progress_monitor import ProgressUpdate
from services.user_vocabulary_store import TermPreference


def _create_minimal_pdf_bytes(text: str = "Test Philosophical Document", pages: int = 1) -> bytes:
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
def client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(api_router, prefix="/api/v1")
    return TestClient(test_app, headers={"X-API-Key": "test-admin-key"})


class TestZeroAuthCostEstimatorRoute:
    """Requirement 1: Zero-Auth Cost Estimator Widget."""

    def test_cost_estimate_valid_pdf(self, client: TestClient) -> None:
        pdf_bytes = _create_minimal_pdf_bytes(pages=5)
        response = client.post(
            "/api/v1/cost/estimate",
            files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_pages"] == 5
        assert "base_cost" in data
        assert "storage_cost_1mo" in data
        assert "storage_cost_12mo" in data
        assert "tolerance_range" in data
        assert data["base_cost"] == pytest.approx(0.40)

    def test_cost_estimate_invalid_file_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/cost/estimate",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400


class TestOnboardingGuideRoute:
    """Requirement 2: Interactive GCP Onboarding Walkthrough Modal."""

    def test_get_onboarding_guide(self, client: TestClient) -> None:
        response = client.get("/api/v1/byok/onboarding-guide")
        assert response.status_code == 200
        data = response.json()
        assert "steps" in data
        assert len(data["steps"]) >= 6
        first_step = data["steps"][0]
        assert "step_number" in first_step
        assert "title" in first_step
        assert "gcloud_script" in data


class TestBYOKCredentialsRoutes:
    """Requirement 3: BYOK Setup Panel with instant dual validation."""

    @patch("api.routes.get_byok_credentials_manager")
    def test_set_and_validate_credentials(
        self, mock_get_mgr: MagicMock, client: TestClient
    ) -> None:
        mock_mgr = MagicMock()
        mock_mgr.set_credentials.return_value = None
        mock_mgr.validate_credentials.return_value = ValidationResult(
            status="VALID",
            translation_check_passed=True,
            storage_check_passed=True,
            error_details=None,
        )
        mock_get_mgr.return_value = mock_mgr

        response = client.post(
            "/api/v1/byok/credentials",
            json={
                "user_id": "user-123",
                "project_id": "test-proj",
                "bucket_name": "test-bucket",
                "sa_json": '{"type": "service_account"}',
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["translation_api_ok"] is True
        assert data["storage_bucket_ok"] is True

    @patch("api.routes.get_byok_credentials_manager")
    def test_validate_credentials_endpoint(
        self, mock_get_mgr: MagicMock, client: TestClient
    ) -> None:
        mock_mgr = MagicMock()
        mock_mgr.validate_credentials.return_value = ValidationResult(
            status="VALID",
            translation_check_passed=True,
            storage_check_passed=True,
            error_details=None,
        )
        mock_get_mgr.return_value = mock_mgr

        response = client.get("/api/v1/byok/validate?user_id=user-123")
        assert response.status_code == 200
        assert response.json()["is_valid"] is True


class TestPreScanAndVocabularyRoutes:
    """Requirement 4 & 5: Pre-Scan View, Fraktur OCR Badge & Terminology Memory."""

    @patch("api.routes.get_book_orchestrator")
    def test_book_pre_scan(
        self, mock_get_orch: MagicMock, client: TestClient
    ) -> None:
        mock_orch = MagicMock()
        mock_orch.pre_scan_book.return_value = BookScanResult(
            total_pages=10,
            script_analysis=ScriptAnalysisResult(
                script_type=ScriptType.ANTIQUA,
                ocr_confidence_score=0.95,
                ligature_counts={},
                font_descriptors=["Helvetica"],
                recommended_action="Direct batch translation",
                total_pages_analyzed=10,
                fraktur_ratio=0.0,
            ),
            ocr_confidence=OCRConfidence(
                confidence_score=0.95,
                script_type="Antiqua",
                recommended_action="Direct batch translation",
                preview_recommended=False,
            ),
            detected_neologisms=[],
            prefilled_terms={
                "Dasein": TermPreference(
                    german_term="Dasein",
                    preferred_translation="Being-there",
                )
            },
            cost_quote=CostQuote(
                total_pages=10,
                file_size_mb=1.0,
                base_cost=0.80,
                staging_overhead_cost=0.001,
                storage_cost_1mo=0.02,
                storage_cost_12mo=0.24,
                free_tier_covered=True,
                total_estimate=0.82,
                tolerance_range=(0.80, 5.82),
                estimation_time_sec=0.05,
            ),
            sample_text="Dasein im Widersacher",
        )
        mock_get_orch.return_value = mock_orch

        pdf_bytes = _create_minimal_pdf_bytes(pages=10)
        response = client.post(
            "/api/v1/book/pre-scan",
            data={"user_id": "user-123"},
            files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_pages"] == 10
        assert data["ocr_confidence"]["confidence_score"] == 0.95
        assert "Dasein" in data["prefilled_terms"]

    @patch("api.routes.get_user_vocabulary_store")
    def test_vocabulary_crud(
        self, mock_get_store: MagicMock, client: TestClient
    ) -> None:
        mock_store = MagicMock()
        mock_store.get_user_preferences.return_value = {
            "Seele": TermPreference(german_term="Seele", preferred_translation="Soul")
        }
        mock_store.save_preference.return_value = TermPreference(
            german_term="Geist",
            preferred_translation="Mind/Spirit",
        )
        mock_get_store.return_value = mock_store

        response = client.get("/api/v1/vocabulary/user-123")
        assert response.status_code == 200
        assert "Seele" in response.json()

        response = client.post(
            "/api/v1/vocabulary/user-123",
            json={"german_term": "Geist", "preferred_translation": "Mind/Spirit"},
        )
        assert response.status_code == 200
        mock_store.save_preference.assert_called_once()


class TestBatchTranslationAndRecoveryRoutes:
    """Requirement 6: Live Batch LRO Progress & Recovery."""

    @patch("api.routes.get_book_orchestrator")
    def test_start_batch_translation(
        self, mock_get_orch: MagicMock, client: TestClient
    ) -> None:
        mock_orch = MagicMock()
        mock_orch.start_book_translation.return_value = ActiveJobState(
            session_id="sess-xyz",
            user_id="user-123",
            book_id="book-101",
            lro_name="projects/test/locations/us-central1/operations/op-123",
            gcs_output_uri="gs://test-bucket/outputs/book-101/",
            total_pages=50,
            translated_pages=0,
            failed_pages=0,
            status="SUBMITTED",
        )
        mock_get_orch.return_value = mock_orch

        pdf_bytes = _create_minimal_pdf_bytes(pages=2)
        response = client.post(
            "/api/v1/book/translate",
            data={
                "user_id": "user-123",
                "session_id": "sess-xyz",
                "book_id": "book-101",
            },
            files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess-xyz"
        assert data["status"] == "SUBMITTED"

    @patch("api.routes.get_book_orchestrator")
    def test_get_progress_route(
        self, mock_get_orch: MagicMock, client: TestClient
    ) -> None:
        mock_orch = MagicMock()
        mock_orch.poll_translation_progress.return_value = ProgressUpdate(
            operation_name="op-123",
            state="RUNNING",
            total_pages=100,
            translated_pages=40,
            failed_pages=0,
            completion_pct=40.0,
            is_done=False,
        )
        mock_get_orch.return_value = mock_orch

        response = client.get("/api/v1/book/status/sess-xyz?user_id=user-123")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "RUNNING"
        assert data["completion_pct"] == 40.0


class TestScholarlyDeliveryRoutes:
    """Requirement 7: Scholarly Delivery Actions (Drive, Download, Fallback, Dual-Pane)."""

    @patch("api.routes.get_book_orchestrator")
    def test_export_to_google_drive_route(
        self, mock_get_orch: MagicMock, client: TestClient
    ) -> None:
        mock_orch = MagicMock()
        mock_orch.export_to_google_drive.return_value = DriveExportResult(
            file_id="drive-doc-456",
            file_name="translated.pdf",
            web_view_link="https://drive.google.com/file/d/drive-doc-456/view",
            web_content_link="https://drive.google.com/uc?id=drive-doc-456",
            created_time="2026-08-27T08:00:00Z",
        )
        mock_get_orch.return_value = mock_orch

        response = client.post(
            "/api/v1/book/export-drive",
            json={
                "user_id": "user-123",
                "session_id": "sess-xyz",
                "access_token": "ya29.gis-token",
                "filename": "klages_translated.pdf",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == "drive-doc-456"
        assert "drive.google.com" in data["web_view_link"]

    @patch("api.routes.get_book_orchestrator")
    def test_fallback_translation_route(
        self, mock_get_orch: MagicMock, client: TestClient
    ) -> None:
        mock_orch = MagicMock()
        mock_orch.trigger_fallback_page_translation.return_value = FallbackResult(
            session_id="sess-xyz",
            failed_pages_count=2,
            translated_pages=[],
            spliced_output_gcs_uri="gs://bucket/outputs/book/spliced.pdf",
            success=True,
        )
        mock_get_orch.return_value = mock_orch

        pdf_bytes = _create_minimal_pdf_bytes(pages=2)
        response = client.post(
            "/api/v1/book/fallback-translate",
            data={
                "user_id": "user-123",
                "session_id": "sess-xyz",
                "failed_page_indices": "1,2",
            },
            files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    @patch("api.routes.get_book_orchestrator")
    def test_dual_pane_view_route(
        self, mock_get_orch: MagicMock, client: TestClient
    ) -> None:
        mock_orch = MagicMock()
        mock_orch.get_bilingual_view.return_value = BilingualPagePair(
            page_number=1,
            total_pages_german=10,
            total_pages_english=10,
            german_text="German Original Text",
            english_text="English Translated Text",
        )
        mock_get_orch.return_value = mock_orch

        pdf_bytes = _create_minimal_pdf_bytes(pages=2)
        response = client.post(
            "/api/v1/book/dual-pane/sess-xyz?user_id=user-123&page_number=1",
            files={"file": ("source.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page_number"] == 1
        assert data["german_text"] == "German Original Text"
        assert data["english_text"] == "English Translated Text"

    @patch("api.routes.get_byok_credentials_manager")
    def test_clear_credentials(
        self, mock_get_mgr: MagicMock, client: TestClient
    ) -> None:
        mock_mgr = MagicMock()
        mock_get_mgr.return_value = mock_mgr
        response = client.delete("/api/v1/byok/credentials?user_id=user-123")
        assert response.status_code == 200
        assert response.json()["success"] is True

    @patch("api.routes.get_book_orchestrator")
    def test_resume_and_list_jobs(
        self, mock_get_orch: MagicMock, client: TestClient
    ) -> None:
        mock_orch = MagicMock()
        mock_orch.resume_job.return_value = ActiveJobState(
            session_id="sess-resumed",
            user_id="user-123",
            book_id="book-101",
            lro_name="projects/p/locations/l/operations/op1",
            gcs_output_uri="gs://b/outputs/sess-resumed/",
            total_pages=50,
            translated_pages=25,
            failed_pages=0,
            status="RUNNING",
        )
        mock_orch.list_user_jobs.return_value = [mock_orch.resume_job.return_value]
        mock_get_orch.return_value = mock_orch

        # Resume without user_id rejected
        res_missing = client.get("/api/v1/book/resume/sess-resumed")
        assert res_missing.status_code == 422

        # Resume with user_id succeeds
        res = client.get("/api/v1/book/resume/sess-resumed?user_id=user-123")
        assert res.status_code == 200
        assert res.json()["session_id"] == "sess-resumed"

        # List
        res = client.get("/api/v1/book/jobs/user-123")
        assert res.status_code == 200
        assert len(res.json()) == 1

    @patch("api.routes.get_book_orchestrator")
    def test_complete_and_download_job(
        self, mock_get_orch: MagicMock, client: TestClient
    ) -> None:
        mock_orch = MagicMock()
        mock_orch.handle_job_completion.return_value = CompletionSummary(
            session_id="sess-done",
            status="SUCCEEDED",
            total_pages=10,
            translated_pages=10,
            failed_pages=0,
            is_done=True,
            can_fallback=False,
            output_gcs_uri="gs://b/outputs/sess-done/translated.pdf",
        )
        mock_orch.download_translated_book.return_value = (
            b"%PDF-1.4 Mock Translated PDF",
            "sess-done_translated.pdf",
        )
        mock_get_orch.return_value = mock_orch

        # Complete
        res = client.post("/api/v1/book/complete/sess-done?user_id=user-123")
        assert res.status_code == 200
        assert res.json()["is_done"] is True

        # Download
        res = client.get("/api/v1/book/download/sess-done?user_id=user-123")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content == b"%PDF-1.4 Mock Translated PDF"

    @patch("api.routes.get_user_vocabulary_store")
    def test_bulk_vocabulary_and_tsv(
        self, mock_get_store: MagicMock, client: TestClient
    ) -> None:
        mock_store = MagicMock()
        mock_store.bulk_save_preferences.return_value = 2
        mock_store.export_tsv.return_value = b"de\ten\nGeist\tMind\nSeele\tSoul\n"
        mock_store.import_rfc4180_tsv.return_value = ["Geist", "Seele"]
        mock_get_store.return_value = mock_store

        # Bulk save
        res = client.post(
            "/api/v1/vocabulary/user-123/bulk",
            json=[
                {"german_term": "Geist", "preferred_translation": "Mind"},
                {"german_term": "Seele", "preferred_translation": "Soul"},
            ],
        )
        assert res.status_code == 200
        assert res.json()["saved_count"] == 2

        # Export TSV
        res = client.get("/api/v1/vocabulary/user-123/export")
        assert res.status_code == 200
        assert "text/tab-separated-values" in res.headers["content-type"]
        assert b"Geist\tMind" in res.content

        # Import TSV
        res = client.post(
            "/api/v1/vocabulary/user-123/import",
            json={"tsv_content": "de\ten\nGeist\tMind\nSeele\tSoul\n"},
        )
        assert res.status_code == 200
        assert res.json()["imported_count"] == 2

    def test_input_validation_errors(self, client: TestClient) -> None:
        # Invalid PDF extension
        res = client.post(
            "/api/v1/cost/estimate",
            files={"file": ("doc.txt", b"plain text", "text/plain")},
        )
        assert res.status_code == 400

        # Empty credentials payload
        res = client.post("/api/v1/byok/credentials", json={})
        assert res.status_code == 400

        # Empty vocabulary payload
        res = client.post("/api/v1/vocabulary/user-123", json={})
        assert res.status_code == 400


class TestOwnershipAndAuthorization:
    """Security verification ensuring caller cannot tamper with other users' resources."""

    def test_cross_user_credential_modification_rejected(self) -> None:
        """Verify non-admin caller cannot modify another user's BYOK credentials."""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        # Override auth to simulate an authenticated non-admin user 'attacker'
        from api.auth import get_current_user_dependency

        app.dependency_overrides[get_current_user_dependency] = lambda: {
            "user_id": "attacker",
            "role": UserRole.READ_ONLY,
            "authenticated": True,
        }
        client = TestClient(app)

        # Attempt to set credentials for victim
        res = client.post(
            "/api/v1/byok/credentials",
            json={
                "user_id": "victim",
                "project_id": "victim-proj",
                "bucket_name": "victim-bkt",
                "sa_json": '{"type": "service_account"}',
            },
        )
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]

        # Attempt to clear credentials for victim
        res_del = client.delete("/api/v1/byok/credentials?user_id=victim")
        assert res_del.status_code == 403

    def test_cross_user_vocabulary_modification_rejected(self) -> None:
        """Verify non-admin caller cannot alter another user's persistent vocabulary."""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        from api.auth import get_current_user_dependency

        app.dependency_overrides[get_current_user_dependency] = lambda: {
            "user_id": "attacker",
            "role": UserRole.READ_ONLY,
            "authenticated": True,
        }
        client = TestClient(app)

        # Attempt to save vocabulary for victim
        res = client.post(
            "/api/v1/vocabulary/victim",
            json={"german_term": "Dasein", "preferred_translation": "Being"},
        )
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]

        # Attempt to bulk save vocabulary for victim
        res_bulk = client.post(
            "/api/v1/vocabulary/victim/bulk",
            json=[{"german_term": "Dasein", "preferred_translation": "Being"}],
        )
        assert res_bulk.status_code == 403

    def test_cross_user_job_resume_rejected(self) -> None:
        """Verify non-admin caller cannot resume or inspect another user's job session."""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        from api.auth import get_current_user_dependency

        app.dependency_overrides[get_current_user_dependency] = lambda: {
            "user_id": "attacker",
            "role": UserRole.READ_ONLY,
            "authenticated": True,
        }
        client = TestClient(app)

        res = client.get("/api/v1/book/resume/victim-sess-123?user_id=victim")
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]

    def test_anonymous_caller_cannot_access_any_user_resources(self) -> None:
        """Verify unauthenticated/anonymous caller cannot access or mutate user resources, eliminating shared state."""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        from api.auth import ANONYMOUS_USER, get_current_user_dependency

        # Simulate unauthenticated anonymous request
        app.dependency_overrides[get_current_user_dependency] = lambda: ANONYMOUS_USER
        client = TestClient(app)

        # Attempt to set credentials for victim is rejected
        res = client.post(
            "/api/v1/byok/credentials",
            json={
                "user_id": "victim",
                "project_id": "victim-proj",
                "bucket_name": "victim-bkt",
                "sa_json": '{"type": "service_account"}',
            },
        )
        assert res.status_code == 401
        assert "Authentication required" in res.json()["detail"]

        # Attempt to access victim vocabulary is rejected
        res_voc = client.get("/api/v1/vocabulary/victim")
        assert res_voc.status_code == 401

        # Attempt to access anonymous vocabulary is also rejected to eliminate shared state
        res_anon = client.get("/api/v1/vocabulary/anonymous")
        assert res_anon.status_code == 400
        assert "Shared anonymous namespaces are prohibited" in res_anon.json()["detail"]

    def test_empty_identity_in_jwt_rejected(self) -> None:
        """Verify non-admin caller with empty user_id cannot bypass ownership checks."""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        from api.auth import get_current_user_dependency

        # Caller with empty user_id
        app.dependency_overrides[get_current_user_dependency] = lambda: {
            "user_id": "",
            "role": UserRole.READ_ONLY,
            "authenticated": True,
        }
        client = TestClient(app)

        res = client.get("/api/v1/vocabulary/scholar-01")
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]

    def test_disabled_authentication_permits_local_workflows(self) -> None:
        """Verify workflows function seamlessly when MEMORY_API_ENABLE_AUTH=false."""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        from api.auth import get_current_user_dependency

        app.dependency_overrides[get_current_user_dependency] = lambda: {
            "user_id": "scholar-01",
            "role": UserRole.READ_ONLY,
            "authenticated": False,
            "method": "disabled",
        }
        client = TestClient(app)

        with (
            patch("api.routes.is_auth_enabled", return_value=False),
            patch("api.routes.get_user_vocabulary_store") as mock_store_getter,
        ):
            mock_store = MagicMock()
            mock_store.get_preferences.return_value = {}
            mock_store_getter.return_value = mock_store

            # Distinct user namespace matching caller succeeds
            res = client.get("/api/v1/vocabulary/scholar-01")
            assert res.status_code == 200

            # Shared anonymous namespace is rejected to eliminate shared anonymous state
            res_anon = client.get("/api/v1/vocabulary/default_user")
            assert res_anon.status_code == 400
            assert "Shared anonymous namespaces are prohibited" in res_anon.json()["detail"]

            # Sibling victim namespace is rejected
            res_victim = client.get("/api/v1/vocabulary/victim")
            assert res_victim.status_code == 403
            assert "Access denied" in res_victim.json()["detail"]

    def test_prefix_user_cannot_access_or_manipulate_victim_job(self) -> None:
        """Verify user 'usr' cannot recover or manipulate session of 'usr_victim' via prefix collision."""
        from pathlib import Path

        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        from api.auth import get_current_user_dependency
        from services.batch_job_recovery import ActiveJobState

        # Authenticated as user 'usr'
        app.dependency_overrides[get_current_user_dependency] = lambda: {
            "user_id": "usr",
            "role": UserRole.READ_ONLY,
            "authenticated": True,
        }
        client = TestClient(app)

        # Mock orchestrator with recovery_manager returning victim's state
        mock_orch = MagicMock()
        mock_state = ActiveJobState(
            session_id="sess-victim-101",
            user_id="usr_victim",
            book_id="victim_book",
            lro_name="projects/1/locations/us-central1/operations/123",
            gcs_output_uri="gs://victim-bucket/outputs/victim_book/",
        )
        mock_orch.recovery_manager._find_job_by_session.return_value = (Path("/tmp/usr_victim_book.json"), mock_state)

        with patch("api.routes.get_book_orchestrator", return_value=mock_orch):
            # Attempt to poll status of victim's job as user 'usr'
            res_status = client.get("/api/v1/book/status/sess-victim-101?user_id=usr")
            assert res_status.status_code == 403
            assert "Access denied" in res_status.json()["detail"]

            # Attempt to complete victim's job as user 'usr'
            res_comp = client.post("/api/v1/book/complete/sess-victim-101?user_id=usr")
            assert res_comp.status_code == 403
            assert "Access denied" in res_comp.json()["detail"]

            # Attempt to download victim's job as user 'usr'
            res_dl = client.get("/api/v1/book/download/sess-victim-101?user_id=usr")
            assert res_dl.status_code == 403
            assert "Access denied" in res_dl.json()["detail"]
