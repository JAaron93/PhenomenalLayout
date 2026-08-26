"""Unit tests for SessionGlossaryLifecycleManager (TASK-2.4, FR-14, NFR-03).

Verifies:
- Registration and tracking of dynamic Tier 2 session glossaries
- Auto-cleanup of GCP regional glossary resources and GCS TSV blobs
- Project glossary quota auditing and warning alerts at threshold (900/1000)
- Expiration and pruning of stale session glossaries
- Persistence of session tracking metadata across manager reloads
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.api_core import exceptions as gcp_exceptions
from google.cloud import translate_v3 as translate

from services.byok_credentials_manager import BYOKCredentialsManager
from services.session_glossary_lifecycle import (
    SessionGlossaryLifecycleManager,
    SessionGlossaryRecord,
)


@pytest.fixture
def temp_meta_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_creds_mgr() -> MagicMock:
    mgr = MagicMock(spec=BYOKCredentialsManager)
    mgr.get_project_id.return_value = "test-project-123"
    mgr.get_bucket_name.return_value = "user-trans-bucket"

    # Mock Translation Client
    mock_trans = MagicMock(spec=translate.TranslationServiceClient)
    mgr.get_translation_client.return_value = mock_trans

    # Mock Storage Client
    mock_storage = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_storage.bucket.return_value = mock_bucket
    mgr.get_storage_client.return_value = mock_storage

    return mgr


@pytest.fixture
def lifecycle_mgr(mock_creds_mgr: MagicMock, temp_meta_dir: Path) -> SessionGlossaryLifecycleManager:
    return SessionGlossaryLifecycleManager(
        credentials_manager=mock_creds_mgr,
        storage_dir=temp_meta_dir,
        location="us-central1",
    )


class TestSessionGlossaryRegistration:
    """Test tracking and persistence of session glossaries."""

    def test_register_session_glossary(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager
    ) -> None:
        rec = lifecycle_mgr.register_session_glossary(
            user_id="user_1",
            session_id="book-sess-42",
            glossary_resource_name="projects/test-project-123/locations/us-central1/glossaries/sess-book-sess-42",
            gcs_tsv_uri="gs://user-trans-bucket/glossaries/sessions/sess-book-sess-42.tsv",
        )
        assert rec.user_id == "user_1"
        assert rec.session_id == "book-sess-42"
        assert rec.status == "active"
        assert rec.created_at > 0

        active_sessions = lifecycle_mgr.list_active_sessions("user_1")
        assert len(active_sessions) == 1
        assert active_sessions[0].session_id == "book-sess-42"

    def test_persistence_across_instances(
        self, mock_creds_mgr: MagicMock, temp_meta_dir: Path
    ) -> None:
        mgr1 = SessionGlossaryLifecycleManager(
            credentials_manager=mock_creds_mgr,
            storage_dir=temp_meta_dir,
        )
        mgr1.register_session_glossary(
            user_id="user_1",
            session_id="persisted-sess",
            glossary_resource_name="projects/p/locations/l/glossaries/g1",
            gcs_tsv_uri="gs://b/g1.tsv",
        )

        mgr2 = SessionGlossaryLifecycleManager(
            credentials_manager=mock_creds_mgr,
            storage_dir=temp_meta_dir,
        )
        active = mgr2.list_active_sessions("user_1")
        assert len(active) == 1
        assert active[0].session_id == "persisted-sess"


class TestSessionGlossaryCleanup:
    """Test cleanup of GCP Translation glossaries and GCS TSVs."""

    def test_cleanup_session_glossary_success(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager, mock_creds_mgr: MagicMock
    ) -> None:
        lifecycle_mgr.register_session_glossary(
            user_id="user_1",
            session_id="sess-clean-1",
            glossary_resource_name="projects/test-project-123/locations/us-central1/glossaries/sess-clean-1",
            gcs_tsv_uri="gs://user-trans-bucket/glossaries/sessions/sess-clean-1.tsv",
        )

        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_op = MagicMock()
        mock_trans.delete_glossary.return_value = mock_op

        storage_client = mock_creds_mgr.get_storage_client.return_value
        mock_bucket = storage_client.bucket.return_value
        mock_blob = mock_bucket.blob.return_value

        success = lifecycle_mgr.cleanup_session_glossary("user_1", "sess-clean-1")
        assert success is True

        mock_trans.delete_glossary.assert_called_once_with(
            name="projects/test-project-123/locations/us-central1/glossaries/sess-clean-1"
        )
        mock_op.result.assert_called_once()
        mock_blob.delete.assert_called_once()

        # Session should no longer be listed in active sessions
        assert len(lifecycle_mgr.list_active_sessions("user_1")) == 0

    def test_cleanup_nonexistent_session_returns_false(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager
    ) -> None:
        assert lifecycle_mgr.cleanup_session_glossary("user_1", "nonexistent") is False

    def test_cleanup_handles_already_deleted_gcp_glossary(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager, mock_creds_mgr: MagicMock
    ) -> None:
        lifecycle_mgr.register_session_glossary(
            user_id="user_1",
            session_id="sess-already-gone",
            glossary_resource_name="projects/test-project-123/locations/us-central1/glossaries/sess-already-gone",
            gcs_tsv_uri="gs://user-trans-bucket/glossaries/sessions/sess-already-gone.tsv",
        )

        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_trans.delete_glossary.side_effect = gcp_exceptions.NotFound("Glossary already deleted")

        success = lifecycle_mgr.cleanup_session_glossary("user_1", "sess-already-gone")
        assert success is True


class TestAuditProjectGlossaries:
    """Test quota tracking and alerts against the 1,000 regional quota limit."""

    def test_audit_normal_usage(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value

        # Mock list_glossaries returning 3 glossaries
        g1 = MagicMock(name="g1", entry_count=120)
        g1.name = "projects/test-project-123/locations/us-central1/glossaries/g1"
        g2 = MagicMock(name="g2", entry_count=50)
        g2.name = "projects/test-project-123/locations/us-central1/glossaries/g2"
        mock_trans.list_glossaries.return_value = [g1, g2]

        report = lifecycle_mgr.audit_project_glossaries("user_1")
        assert len(report["glossaries"]) == 2
        assert report["total_count"] == 2
        assert report["quota_limit"] == 1000
        assert report["warning_threshold"] == 900
        assert report["approaching_quota"] is False

    def test_audit_approaching_quota_triggers_warning(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        fake_glossaries = [MagicMock(name=f"g{i}") for i in range(920)]
        mock_trans.list_glossaries.return_value = fake_glossaries

        report = lifecycle_mgr.audit_project_glossaries("user_1")
        assert report["total_count"] == 920
        assert report["approaching_quota"] is True


class TestExpirationCleanup:
    """Test pruning of stale session glossaries."""

    def test_cleanup_expired_glossaries(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager, mock_creds_mgr: MagicMock
    ) -> None:
        now = time.time()
        # Register old session (30 hours old)
        rec_old = lifecycle_mgr.register_session_glossary(
            user_id="user_1",
            session_id="old-sess",
            glossary_resource_name="projects/test-project-123/locations/us-central1/glossaries/old-sess",
            gcs_tsv_uri="gs://user-trans-bucket/glossaries/sessions/old-sess.tsv",
        )
        rec_old.created_at = now - (30 * 3600)
        lifecycle_mgr._save_user_sessions("user_1")

        # Register fresh session (1 hour old)
        lifecycle_mgr.register_session_glossary(
            user_id="user_1",
            session_id="fresh-sess",
            glossary_resource_name="projects/test-project-123/locations/us-central1/glossaries/fresh-sess",
            gcs_tsv_uri="gs://user-trans-bucket/glossaries/sessions/fresh-sess.tsv",
        )

        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_op = MagicMock()
        mock_trans.delete_glossary.return_value = mock_op

        cleaned_count = lifecycle_mgr.cleanup_expired_glossaries("user_1", max_age_hours=24)
        assert cleaned_count == 1

        active = lifecycle_mgr.list_active_sessions("user_1")
        assert len(active) == 1
        assert active[0].session_id == "fresh-sess"


class TestLifecycleErrorBranches:
    """Test exception branches and resiliency."""

    def test_cleanup_handles_exceptions(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager, mock_creds_mgr: MagicMock
    ) -> None:
        lifecycle_mgr.register_session_glossary(
            user_id="user_err",
            session_id="err-sess",
            glossary_resource_name="projects/p/locations/l/glossaries/err-g",
            gcs_tsv_uri="gs://user-trans-bucket/glossaries/sessions/err-g.tsv",
        )
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_trans.delete_glossary.side_effect = RuntimeError("GCP API timeout")

        storage_client = mock_creds_mgr.get_storage_client.return_value
        mock_blob = storage_client.bucket.return_value.blob.return_value
        mock_blob.delete.side_effect = RuntimeError("GCS storage error")

        # When transient errors occur, cleanup returns False and retains active record for retry
        res = lifecycle_mgr.cleanup_session_glossary("user_err", "err-sess")
        assert res is False
        assert len(lifecycle_mgr.list_active_sessions("user_err")) == 1

        # When the transient issue resolves, subsequent cleanup retry succeeds
        mock_trans.delete_glossary.side_effect = None
        mock_delete_op = MagicMock()
        mock_trans.delete_glossary.return_value = mock_delete_op
        mock_blob.delete.side_effect = None

        retry_res = lifecycle_mgr.cleanup_session_glossary("user_err", "err-sess")
        assert retry_res is True
        assert len(lifecycle_mgr.list_active_sessions("user_err")) == 0

    def test_audit_handles_list_exception(
        self, lifecycle_mgr: SessionGlossaryLifecycleManager, mock_creds_mgr: MagicMock
    ) -> None:
        mock_trans = mock_creds_mgr.get_translation_client.return_value
        mock_trans.list_glossaries.side_effect = RuntimeError("Network error")

        report = lifecycle_mgr.audit_project_glossaries("user_err")
        assert report["total_count"] == 0
        assert report["glossaries"] == []

    def test_corrupted_meta_file_handled(
        self, mock_creds_mgr: MagicMock, temp_meta_dir: Path
    ) -> None:
        corrupted_file = temp_meta_dir / "user_corrupted.json"
        corrupted_file.write_text("{ corrupt json ", encoding="utf-8")

        mgr = SessionGlossaryLifecycleManager(
            credentials_manager=mock_creds_mgr,
            storage_dir=temp_meta_dir,
        )
        active = mgr.list_active_sessions("user_corrupted")
        assert active == []

    def test_default_storage_fallback_on_oserror(
        self, mock_creds_mgr: MagicMock
    ) -> None:
        mgr = SessionGlossaryLifecycleManager(credentials_manager=mock_creds_mgr)
        assert mgr.storage_dir.exists()
