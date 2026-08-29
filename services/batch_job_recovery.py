"""Batch Job Recovery & Resumption Manager (TASK-3.2).

Persists active GCP LRO Operation metadata, session ID, user ID, and target GCS
output paths to the persistent Modal volume (/data/sessions/{user_id}_{book_id}.json).
Enables seamless session reconnection and live progress bar restoration after browser
closing or Modal container scale-to-zero.

Traceability: FR-12, NFR-02, NFR-08
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config.settings import gcp_settings
from services.lro_progress_monitor import LROProgressMonitor

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions & Data Models
# ---------------------------------------------------------------------------


class JobNotFoundError(Exception):
    """Raised when an active job session cannot be located on disk."""


@dataclass
class ActiveJobState:
    """Persisted snapshot of a long-running batch document translation job."""

    session_id: str
    user_id: str
    book_id: str
    lro_name: str
    gcs_output_uri: str
    total_pages: int = 0
    translated_pages: int = 0
    failed_pages: int = 0
    status: str = "SUBMITTED"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert state to JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActiveJobState:
        """Construct state instance from deserialized dictionary."""
        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            book_id=data["book_id"],
            lro_name=data["lro_name"],
            gcs_output_uri=data["gcs_output_uri"],
            total_pages=int(data.get("total_pages", 0)),
            translated_pages=int(data.get("translated_pages", 0)),
            failed_pages=int(data.get("failed_pages", 0)),
            status=data.get("status", "SUBMITTED"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            extra_metadata=data.get("extra_metadata", {}),
        )


# ---------------------------------------------------------------------------
# BatchJobRecoveryManager
# ---------------------------------------------------------------------------


class BatchJobRecoveryManager:
    """Manages persistence and re-attachment for cloud batch translation jobs."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        """Initialise manager with persistent volume directory.

        Args:
            storage_dir: Base directory for job state files. Defaults to
                ``{gcp_settings.modal_volume_path}/sessions``.
        """
        if storage_dir is not None:
            self._storage_dir = Path(storage_dir)
        else:
            self._storage_dir = Path(gcp_settings.modal_volume_path) / "sessions"

        self._storage_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_active_job(
        self,
        user_id: str,
        session_id: str,
        book_id: str,
        lro_name: str,
        gcs_output_uri: str,
        total_pages: int = 0,
        extra_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist an active translation job state atomically to disk.

        Args:
            user_id: Unique user identifier.
            session_id: Book translation session ID.
            book_id: Unique book/document identifier.
            lro_name: Full GCP LRO resource name.
            gcs_output_uri: Target GCS directory for translated PDFs.
            total_pages: Document page count.
            extra_metadata: Optional dictionary of supplementary job metadata.

        Returns:
            Absolute file path of the persisted JSON state file.
        """
        now = time.time()
        state = ActiveJobState(
            session_id=session_id,
            user_id=user_id,
            book_id=book_id,
            lro_name=lro_name,
            gcs_output_uri=gcs_output_uri,
            total_pages=total_pages,
            translated_pages=0,
            failed_pages=0,
            status="SUBMITTED",
            created_at=now,
            updated_at=now,
            extra_metadata=extra_metadata or {},
        )

        file_path = self._job_file_path(user_id, book_id)
        self._write_state_atomically(file_path, state)
        logger.info(
            "Saved active job state for user '%s', book '%s' (session '%s')",
            user_id,
            book_id,
            session_id,
        )
        return str(file_path)

    def resume_active_job(
        self,
        session_id: str,
        user_id: str | None = None,
        progress_monitor: LROProgressMonitor | None = None,
    ) -> ActiveJobState:
        """Recall saved job state and optionally re-attach to live LRO monitoring.

        Adheres to NFR-08: Reconnection executes in strictly under 1.0 second.

        Args:
            session_id: Active session identifier to reconnect to.
            user_id: Optional user identifier to narrow search scope.
            progress_monitor: Optional LROProgressMonitor instance to poll fresh
                progress directly from Google Cloud.

        Returns:
            ActiveJobState containing the latest recovered job state.

        Raises:
            JobNotFoundError: If no matching job session exists.
        """
        file_path, state = self._find_job_by_session(session_id, user_id=user_id)
        if state is None or file_path is None:
            raise JobNotFoundError(f"No active job found for session '{session_id}'")

        if user_id and state.user_id != user_id:
            raise PermissionError(
                f"Access denied: Job session '{session_id}' belongs to user '{state.user_id}', not '{user_id}'"
            )

        # If an active progress monitor is supplied, refresh status against GCP
        if progress_monitor is not None:
            try:
                update = progress_monitor.poll_once(state.user_id, state.lro_name)
                state.translated_pages = update.translated_pages
                state.failed_pages = update.failed_pages
                state.status = update.state
                state.updated_at = time.time()
                self._write_state_atomically(file_path, state)
                logger.info(
                    "Re-attached and refreshed LRO '%s': %d/%d pages (%s)",
                    state.lro_name,
                    state.translated_pages,
                    state.total_pages,
                    state.status,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to refresh live LRO state for '%s': %s",
                    state.lro_name,
                    exc,
                )

        return state

    def list_active_jobs(self, user_id: str) -> list[ActiveJobState]:
        """List all active or saved translation jobs for a user.

        Args:
            user_id: User identifier to list jobs for.

        Returns:
            List of ActiveJobState instances belonging to the user.
        """
        jobs: list[ActiveJobState] = []
        prefix = f"{user_id}_"

        for file_path in self._storage_dir.glob("*.json"):
            if not file_path.name.startswith(prefix):
                continue
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                state = ActiveJobState.from_dict(data)
                if state.user_id == user_id:
                    jobs.append(state)
            except Exception as exc:
                logger.warning("Skipping corrupted job file '%s': %s", file_path, exc)

        return jobs

    def update_job_progress(
        self,
        session_id: str,
        translated_pages: int,
        failed_pages: int,
        status: str,
        user_id: str | None = None,
    ) -> ActiveJobState:
        """Update and persist progress fields for an existing job.

        Args:
            session_id: Target session identifier.
            translated_pages: Number of translated pages.
            failed_pages: Number of failed pages.
            status: New LRO status.
            user_id: Optional user identifier to narrow search.

        Returns:
            Updated ActiveJobState.
        """
        file_path, state = self._find_job_by_session(session_id, user_id=user_id)
        if state is None or file_path is None:
            raise JobNotFoundError(f"Cannot update: job '{session_id}' not found")

        state.translated_pages = translated_pages
        state.failed_pages = failed_pages
        state.status = status
        state.updated_at = time.time()

        self._write_state_atomically(file_path, state)
        return state

    def delete_job(self, session_id: str, user_id: str | None = None) -> bool:
        """Delete persisted job state file upon job cleanup.

        Args:
            session_id: Target session identifier.
            user_id: Optional user identifier to narrow search.

        Returns:
            True if the job file was removed, False otherwise.
        """
        file_path, _ = self._find_job_by_session(session_id, user_id=user_id)
        if file_path is None or not file_path.exists():
            return False

        try:
            file_path.unlink()
            logger.info("Cleaned up job session file '%s'", file_path)
            return True
        except OSError as exc:
            logger.warning("Error deleting job session file '%s': %s", file_path, exc)
            return False

    def cleanup_job(self, session_id: str, user_id: str | None = None) -> bool:
        """Remove a completed or cancelled job record from disk.

        Args:
            session_id: Session identifier to delete.
            user_id: Optional user identifier to narrow search.

        Returns:
            True if job was found and removed, False otherwise.
        """
        return self.delete_job(session_id, user_id=user_id)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _job_file_path(self, user_id: str, book_id: str) -> Path:
        """Derive standard file path for a user and book."""
        return self._storage_dir / f"{user_id}_{book_id}.json"

    def _find_job_by_session(
        self, session_id: str, user_id: str | None = None
    ) -> tuple[Path | None, ActiveJobState | None]:
        """Locate job file and state matching the given session_id and user_id."""
        pattern = f"{user_id}_*.json" if user_id else "*.json"
        for file_path in self._storage_dir.glob(pattern):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if data.get("session_id") == session_id:
                    state = ActiveJobState.from_dict(data)
                    # Enforce strict owner matching to prevent prefix collision
                    # (e.g. user_id 'user' matching file 'user_sub_book.json')
                    if user_id and state.user_id != user_id:
                        continue
                    return file_path, state
            except Exception:
                continue
        return None, None

    @staticmethod
    def _write_state_atomically(target_path: Path, state: ActiveJobState) -> None:
        """Write JSON state atomically via temporary file replacement."""
        data_str = json.dumps(state.to_dict(), indent=2, ensure_ascii=False)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_path.parent,
            delete=False,
        ) as tmp:
            tmp.write(data_str)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_name = tmp.name

        os.replace(temp_name, target_path)
