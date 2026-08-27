"""Unit tests for BatchJobRecoveryManager (TASK-3.2).

Traceability: FR-12, NFR-02, NFR-08
- Active LRO metadata persistence to /data/sessions/{user_id}_{book_id}.json
- Resuming active jobs and re-attaching to live LRO polling
- Sub-second job resumption latency (NFR-08: <= 1.0s)
- Safe concurrent/atomic persistence and error recovery
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.batch_job_recovery import (
    ActiveJobState,
    BatchJobRecoveryManager,
    JobNotFoundError,
)
from services.lro_progress_monitor import LROProgressMonitor, ProgressUpdate


@pytest.fixture
def temp_storage_dir(tmp_path: Path) -> Path:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


@pytest.fixture
def recovery_manager(temp_storage_dir: Path) -> BatchJobRecoveryManager:
    return BatchJobRecoveryManager(storage_dir=temp_storage_dir)


class TestSaveAndListJobs:
    """Verify job persistence and querying."""

    def test_save_active_job(
        self, recovery_manager: BatchJobRecoveryManager, temp_storage_dir: Path
    ) -> None:
        file_path = recovery_manager.save_active_job(
            user_id="translator-01",
            session_id="book-sess-800",
            book_id="klages_1929",
            lro_name="projects/test-proj/locations/us-central1/operations/op-789",
            gcs_output_uri="gs://test-bucket/outputs/book-sess-800/",
            total_pages=800,
            extra_metadata={"language": "de"},
        )

        expected_path = temp_storage_dir / "translator-01_klages_1929.json"
        assert Path(file_path) == expected_path
        assert expected_path.exists()

        data = json.loads(expected_path.read_text(encoding="utf-8"))
        assert data["user_id"] == "translator-01"
        assert data["session_id"] == "book-sess-800"
        assert data["book_id"] == "klages_1929"
        assert data["total_pages"] == 800
        assert data["status"] == "SUBMITTED"

    def test_list_active_jobs(self, recovery_manager: BatchJobRecoveryManager) -> None:
        recovery_manager.save_active_job(
            user_id="user-A",
            session_id="sess-A1",
            book_id="book-1",
            lro_name="op-1",
            gcs_output_uri="gs://b/out1/",
        )
        recovery_manager.save_active_job(
            user_id="user-A",
            session_id="sess-A2",
            book_id="book-2",
            lro_name="op-2",
            gcs_output_uri="gs://b/out2/",
        )
        recovery_manager.save_active_job(
            user_id="user-B",
            session_id="sess-B1",
            book_id="book-3",
            lro_name="op-3",
            gcs_output_uri="gs://b/out3/",
        )

        user_a_jobs = recovery_manager.list_active_jobs("user-A")
        assert len(user_a_jobs) == 2
        sessions = {j.session_id for j in user_a_jobs}
        assert sessions == {"sess-A1", "sess-A2"}

        user_b_jobs = recovery_manager.list_active_jobs("user-B")
        assert len(user_b_jobs) == 1
        assert user_b_jobs[0].session_id == "sess-B1"


class TestResumeActiveJob:
    """Verify state recall, live LRO re-attachment, and latency constraints."""

    def test_resume_active_job_offline(
        self, recovery_manager: BatchJobRecoveryManager
    ) -> None:
        recovery_manager.save_active_job(
            user_id="user-1",
            session_id="sess-100",
            book_id="book-100",
            lro_name="op-100",
            gcs_output_uri="gs://b/out/",
            total_pages=500,
        )

        state = recovery_manager.resume_active_job("sess-100")
        assert isinstance(state, ActiveJobState)
        assert state.session_id == "sess-100"
        assert state.user_id == "user-1"
        assert state.book_id == "book-100"
        assert state.total_pages == 500

    def test_resume_active_job_with_lro_reattach(
        self, recovery_manager: BatchJobRecoveryManager
    ) -> None:
        recovery_manager.save_active_job(
            user_id="translator-01",
            session_id="book-sess-800",
            book_id="klages_1929",
            lro_name="projects/test/locations/us-central1/operations/op-789",
            gcs_output_uri="gs://test-bucket/outputs/",
            total_pages=800,
        )

        mock_monitor = MagicMock(spec=LROProgressMonitor)
        mock_monitor.poll_once.return_value = ProgressUpdate(
            operation_name="projects/test/locations/us-central1/operations/op-789",
            state="RUNNING",
            total_pages=800,
            translated_pages=520,
            failed_pages=1,
            completion_pct=65.0,
            is_done=False,
        )

        state = recovery_manager.resume_active_job(
            "book-sess-800", progress_monitor=mock_monitor
        )

        assert state.translated_pages == 520
        assert state.failed_pages == 1
        assert state.status == "RUNNING"
        mock_monitor.poll_once.assert_called_once_with(
            "translator-01",
            "projects/test/locations/us-central1/operations/op-789",
        )

    def test_job_resumption_latency_under_1_second(
        self, recovery_manager: BatchJobRecoveryManager
    ) -> None:
        """Adheres to NFR-08: Reconnecting must take less than 1.0 second."""
        recovery_manager.save_active_job(
            user_id="user-perf",
            session_id="sess-perf",
            book_id="book-perf",
            lro_name="op-perf",
            gcs_output_uri="gs://b/out/",
            total_pages=1000,
        )

        start = time.perf_counter()
        state = recovery_manager.resume_active_job("sess-perf")
        elapsed = time.perf_counter() - start

        assert state.session_id == "sess-perf"
        assert elapsed < 1.0, (
            f"Resumption took {elapsed:.4f}s >= 1.0s (NFR-08 violation)"
        )


class TestUpdateAndCleanup:
    """Verify progress updates and session cleanup."""

    def test_update_job_progress(
        self, recovery_manager: BatchJobRecoveryManager
    ) -> None:
        recovery_manager.save_active_job(
            user_id="u1",
            session_id="s1",
            book_id="b1",
            lro_name="op1",
            gcs_output_uri="gs://b/out/",
            total_pages=100,
        )

        updated = recovery_manager.update_job_progress(
            session_id="s1",
            translated_pages=50,
            failed_pages=2,
            status="RUNNING",
        )
        assert updated.translated_pages == 50
        assert updated.failed_pages == 2
        assert updated.status == "RUNNING"

        # Verify persisted file reflects updates
        reloaded = recovery_manager.resume_active_job("s1")
        assert reloaded.translated_pages == 50

    def test_cleanup_job(
        self, recovery_manager: BatchJobRecoveryManager, temp_storage_dir: Path
    ) -> None:
        recovery_manager.save_active_job(
            user_id="u1",
            session_id="s1",
            book_id="b1",
            lro_name="op1",
            gcs_output_uri="gs://b/out/",
        )
        file_path = temp_storage_dir / "u1_b1.json"
        assert file_path.exists()

        result = recovery_manager.cleanup_job("s1")
        assert result is True
        assert not file_path.exists()

        # Cleaning up non-existent job returns False
        assert recovery_manager.cleanup_job("s1") is False

    def test_resume_nonexistent_job_raises_job_not_found(
        self, recovery_manager: BatchJobRecoveryManager
    ) -> None:
        with pytest.raises(JobNotFoundError, match="No active job found"):
            recovery_manager.resume_active_job("missing-session")

    def test_corrupted_json_file_handled_gracefully(
        self, recovery_manager: BatchJobRecoveryManager, temp_storage_dir: Path
    ) -> None:
        corrupted_file = temp_storage_dir / "user_bad.json"
        corrupted_file.write_text("invalid json content {{{", encoding="utf-8")

        # Listing jobs should skip corrupted file without crashing
        jobs = recovery_manager.list_active_jobs("user")
        assert len(jobs) == 0

    def test_prefix_user_cannot_recover_or_list_sibling_user_jobs(
        self, recovery_manager: BatchJobRecoveryManager
    ) -> None:
        """Verify user 'usr' cannot match or list jobs of 'usr_victim' through glob prefix collision."""
        recovery_manager.save_active_job(
            user_id="usr_victim",
            session_id="sess-vic-1",
            book_id="book_vic",
            lro_name="op-vic",
            gcs_output_uri="gs://b/vic/",
        )

        # list_active_jobs for 'usr' must not return jobs of 'usr_victim'
        usr_jobs = recovery_manager.list_active_jobs("usr")
        assert len(usr_jobs) == 0

        # resume_active_job for 'usr' attempting to access victim session raises JobNotFoundError
        with pytest.raises(JobNotFoundError):
            recovery_manager.resume_active_job("sess-vic-1", user_id="usr")
