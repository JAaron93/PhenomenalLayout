"""Thread-safe state management for document translation."""

import asyncio
import logging
import threading
import time
from contextlib import contextmanager
from collections.abc import Coroutine
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

UTC = ZoneInfo("UTC")
logger = logging.getLogger(__name__)


class AdvancedTranslationState:
    """Enhanced translation state management with comprehensive processing."""

    def __init__(self):
        """Initialize translation state with default values."""
        self.current_file: str | None = None
        self.current_content: dict[str, Any] | None = None
        self.source_language: str | None = None
        self.target_language: str | None = None
        self.translation_progress: int = 0
        self.translation_status: str = "idle"
        self.error_message: str = ""
        self.job_id: str | None = None
        self.output_file: str | None = None
        self.processing_info: dict[str, Any] = {}
        self.backup_path: str | None = None
        self.max_pages: int = 0  # 0 means translate all pages
        self.session_id: str | None = None
        self.neologism_analysis: dict[str, Any] | None = None
        self.user_choices: list[dict[str, Any]] = []
        self.philosophy_mode: bool = False
        self._translation_task: asyncio.Task[Any] | None = None
        self._translation_task_loop: asyncio.AbstractEventLoop | None = None

    def _assert_current_loop_matches_translation_task(self) -> None:
        task = self._translation_task
        loop = self._translation_task_loop
        if task is None:
            return
        if loop is None:
            raise RuntimeError(
                f"Tracked translation task {task!r} has no owning loop"
            )
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError(
                "No running event loop in current context; "
                f"tracked translation task {task!r} belongs to loop {loop!r}"
            ) from exc
        if current_loop is not loop:
            raise RuntimeError(
                "Tracked translation task belongs to a different event loop; "
                f"task={task!r} loop={loop!r} current_loop={current_loop!r}"
            )

    def create_and_track_translation_task(
        self, coro: Coroutine[Any, Any, Any]
    ) -> asyncio.Task[Any]:
        loop = asyncio.get_running_loop()
        task: asyncio.Task[Any] = loop.create_task(coro)
        self._translation_task = task
        self._translation_task_loop = loop
        return task

    def get_tracked_translation_task(self) -> asyncio.Task[Any] | None:
        self._assert_current_loop_matches_translation_task()
        return self._translation_task

    def cancel_tracked_translation_task(self) -> bool:
        self._assert_current_loop_matches_translation_task()
        task = self._translation_task
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def drop_tracked_translation_task(self, *, cancel: bool = False) -> None:
        """Drop tracked task references.

        By default, this does not cancel any running task. Pass cancel=True to
        cancel the tracked task (if active) before dropping it.
        """
        task = self._translation_task
        if cancel and task is not None and not task.done():
            self._assert_current_loop_matches_translation_task()
            task.cancel()
        self._translation_task = None
        self._translation_task_loop = None

    def clear_tracked_translation_task(self, task: asyncio.Task[Any]) -> None:
        self._assert_current_loop_matches_translation_task()
        if self._translation_task is task:
            self._translation_task = None
            self._translation_task_loop = None


class ThreadSafeTranslationJobs:
    """Thread-safe translation job management with automatic cleanup."""

    def __init__(self, retention_hours: int = 24):
        """Initialize thread-safe job manager.

        Args:
            retention_hours: Hours to retain completed jobs before cleanup
        """
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._retention_hours = retention_hours
        self._cleanup_interval = 3600  # Run cleanup every hour
        self._last_cleanup = time.time()

    def add_job(
        self,
        job_id: str,
        job_data: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> None:
        """Add a new job with timestamp.

        Creates a shallow copy of job_data to avoid mutating caller's dict.
        The job data is stored with a timestamp field - either provided
        or current UTC time.

        Args:
            job_id: Unique identifier for the job
            job_data: Dictionary containing job data
            timestamp: Optional timestamp to use; if None, uses current UTC time

        Note:
            To update job data after creation, use update_job() method.
        """
        with self._lock:
            # Create shallow copy to avoid mutating caller's dict
            job = dict(job_data)
            job["timestamp"] = timestamp or datetime.now(UTC)
            self._jobs[job_id] = job
            self._maybe_cleanup()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Get job data by ID.

        Returns:
            A shallow copy of the job data if found, None otherwise.
            Returned dict is safe to read but modifications won't affect
            the stored job. Use update_job() to modify job data.
        """
        with self._lock:
            job_data = self._jobs.get(job_id)
            return dict(job_data) if job_data is not None else None

    def update_job(self, job_id: str, updates: dict[str, Any]) -> bool:
        """Update job data. Returns True if job exists."""
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(updates)
                return True
            return False

    def remove_job(self, job_id: str) -> bool:
        """Remove a job. Returns True if job existed."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def get_all_jobs(self) -> dict[str, dict[str, Any]]:
        """Get a snapshot of all jobs.

        Returns:
            A dict containing shallow copies of all job data.
            Safe to read and modify without affecting stored jobs.
            Use update_job() to modify individual job data.
        """
        with self._lock:
            return {
                job_id: dict(job_data)
                for job_id, job_data in self._jobs.items()
            }

    def __contains__(self, job_id: str) -> bool:
        """Check if job exists."""
        with self._lock:
            return job_id in self._jobs

    def __getitem__(self, job_id: str) -> dict[str, Any]:
        """Get job data using subscript notation.

        Returns:
            A shallow copy of the job data.
            Returned dict is safe to read but modifications won't affect
            the stored job. Use update_job() to modify job data.

        Raises:
            KeyError: If job_id doesn't exist.
        """
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Job '{job_id}' not found")
            return dict(self._jobs[job_id])

    def __setitem__(self, job_id: str, job_data: dict[str, Any]) -> None:
        """Set job data using subscript notation.

        Preserves any existing timestamp in job_data; otherwise uses current UTC time.
        """
        existing_timestamp = job_data.get("timestamp")
        self.add_job(job_id, job_data, existing_timestamp)

    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed since last cleanup."""
        current_time = time.time()
        if current_time - self._last_cleanup >= self._cleanup_interval:
            self._cleanup_old_jobs()
            self._last_cleanup = current_time

    def _cleanup_old_jobs(self) -> None:
        """Remove jobs older than retention period."""
        cutoff_time = datetime.now(UTC) - timedelta(hours=self._retention_hours)
        jobs_to_remove = []

        for job_id, job_data in self._jobs.items():
            # Only cleanup completed or failed jobs
            if job_data.get("status") in ["completed", "failed", "error"]:
                timestamp = job_data.get("timestamp")
                if timestamp and timestamp < cutoff_time:
                    jobs_to_remove.append(job_id)

        for job_id in jobs_to_remove:
            del self._jobs[job_id]

        if jobs_to_remove:
            logger.info(
                "Cleaned up %s old translation jobs",
                len(jobs_to_remove),
            )

    def force_cleanup(self) -> int:
        """Force immediate cleanup. Returns number of jobs removed."""
        with self._lock:
            initial_count = len(self._jobs)
            self._cleanup_old_jobs()
            return initial_count - len(self._jobs)


class StateManager:
    """Manages request-scoped state instances."""

    def __init__(self):
        """Initialize state manager with empty state dictionary and thread lock."""
        self._states: dict[str, AdvancedTranslationState] = {}
        self._lock = threading.RLock()

    def get_state(self, session_id: str) -> AdvancedTranslationState:
        """Get or create state for a session."""
        with self._lock:
            if session_id not in self._states:
                self._states[session_id] = AdvancedTranslationState()
            return self._states[session_id]

    def remove_state(self, session_id: str) -> None:
        """Remove state for a session."""
        with self._lock:
            self._states.pop(session_id, None)

    @contextmanager
    def session_state(self, session_id: str):
        """Context manager for session state."""
        state = self.get_state(session_id)
        try:
            yield state
        finally:
            # Clean up state after use
            self.remove_state(session_id)


# Thread-safe job manager instance
translation_jobs = ThreadSafeTranslationJobs(retention_hours=24)

# State manager for request-scoped states
state_manager = StateManager()

# For backward compatibility - should be replaced with request-scoped state
# WARNING: This global state is not thread-safe and should be migrated
state = AdvancedTranslationState()


def get_request_state(session_id: str | None = None) -> AdvancedTranslationState:
    """Get state for current request/session.

    Args:
        session_id: Optional session identifier. If None, returns global state.

    Returns:
        State instance for the session

    Note:
        In production, session_id should always be provided to ensure
        thread-safety. The global state fallback is only for backward
        compatibility.
    """
    if session_id:
        return state_manager.get_state(session_id)
    else:
        # WARNING: Using global state - not thread-safe
        logger.warning(
            "Using global state instance - this is not thread-safe. "
            "Please provide a session_id for proper state isolation."
        )
        return state
