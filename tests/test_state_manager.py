"""Tests for thread-safe state management (core/state_manager.py)."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import pytest

from core.state_manager import (
    AdvancedTranslationState,
    StateManager,
    ThreadSafeTranslationJobs,
    get_request_state,
    state,
    state_manager,
    translation_jobs,
)


def make_jobs_store() -> ThreadSafeTranslationJobs:
    return ThreadSafeTranslationJobs(retention_hours=24)


class TestAdvancedTranslationStateDefaults:
    def test_default_field_values(self) -> None:
        fresh = AdvancedTranslationState()
        assert fresh.current_file is None
        assert fresh.translation_status == "idle"
        assert fresh.translation_progress == 0
        assert fresh.error_message == ""
        assert fresh.max_pages == 0
        assert fresh.philosophy_mode is False


class TestTaskTracking:
    async def test_create_and_track_returns_same_task(self) -> None:
        tracked = AdvancedTranslationState()

        async def noop() -> None: ...

        task = tracked.create_and_track_translation_task(noop())
        try:
            assert tracked.get_tracked_translation_task() is task
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def test_no_task_returns_none_and_cancel_is_false(self) -> None:
        tracked = AdvancedTranslationState()
        assert tracked.get_tracked_translation_task() is None
        assert tracked.cancel_tracked_translation_task() is False

    async def test_cancel_running_task_returns_true(self) -> None:
        tracked = AdvancedTranslationState()

        async def sleep_forever() -> None:
            await asyncio.sleep(3600)

        task = tracked.create_and_track_translation_task(sleep_forever())
        assert tracked.cancel_tracked_translation_task() is True
        with suppress(asyncio.CancelledError):
            await task
        assert task.cancelled()

    async def test_drop_tracked_without_cancel_keeps_task_running(self) -> None:
        tracked = AdvancedTranslationState()

        async def sleep_forever() -> None:
            await asyncio.sleep(3600)

        task = tracked.create_and_track_translation_task(sleep_forever())
        tracked.drop_tracked_translation_task()
        assert tracked.get_tracked_translation_task() is None
        assert not task.done()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def test_drop_tracked_with_cancel_stops_task(self) -> None:
        tracked = AdvancedTranslationState()

        async def sleep_forever() -> None:
            await asyncio.sleep(3600)

        task = tracked.create_and_track_translation_task(sleep_forever())
        tracked.drop_tracked_translation_task(cancel=True)
        assert tracked.get_tracked_translation_task() is None
        with suppress(asyncio.CancelledError):
            await task
        assert task.cancelled()

    async def test_clear_tracked_only_matches_own_task(self) -> None:
        tracked = AdvancedTranslationState()

        async def noop() -> None: ...

        task = tracked.create_and_track_translation_task(noop())
        other = asyncio.get_running_loop().create_task(noop())
        tracked.clear_tracked_translation_task(other)
        assert tracked.get_tracked_translation_task() is task
        tracked.clear_tracked_translation_task(task)
        assert tracked.get_tracked_translation_task() is None
        other.cancel()
        with suppress(asyncio.CancelledError):
            await other
        with suppress(asyncio.CancelledError):
            await task

    def test_tracked_task_without_loop_raises(self) -> None:
        tracked = AdvancedTranslationState()
        loop = asyncio.new_event_loop()
        try:

            async def noop() -> None: ...

            task = loop.create_task(noop())
            tracked._translation_task = task
            tracked._translation_task_loop = None
            with pytest.raises(RuntimeError, match="no owning loop"):
                tracked.get_tracked_translation_task()
        finally:
            tracked._translation_task = None
            coro = task.get_coro()
            if coro is not None:
                coro.close()
            loop.close()

    def test_tracked_task_in_foreign_loop_raises_when_checked(
        self,
    ) -> None:
        tracked = AdvancedTranslationState()
        owner_loop = asyncio.new_event_loop()
        try:

            async def noop() -> None: ...

            task = owner_loop.create_task(noop())
            tracked._translation_task = task
            tracked._translation_task_loop = owner_loop

            async def check() -> None:
                with pytest.raises(RuntimeError, match="different event loop"):
                    tracked.get_tracked_translation_task()

            asyncio.run(check())
        finally:
            tracked._translation_task = None
            coro = task.get_coro()
            if coro is not None:
                coro.close()
            owner_loop.close()


class TestThreadSafeTranslationJobs:
    def test_add_and_get_round_trip(self) -> None:
        store = make_jobs_store()
        store.add_job("j1", {"status": "processing"})
        job = store.get_job("j1")
        assert job is not None
        assert job["status"] == "processing"
        assert isinstance(job["timestamp"], datetime)

    def test_add_job_copies_caller_dict(self) -> None:
        store = make_jobs_store()
        payload = {"status": "processing"}
        store.add_job("j1", payload)
        payload["status"] = "mutated"
        stored = store.get_job("j1")
        assert stored is not None
        assert stored["status"] == "processing"

    def test_get_missing_job_returns_none(self) -> None:
        assert make_jobs_store().get_job("ghost") is None

    def test_update_job_existing_and_missing(self) -> None:
        store = make_jobs_store()
        store.add_job("j1", {"status": "processing"})
        assert store.update_job("j1", {"progress": 42}) is True
        updated = store.get_job("j1")
        assert updated is not None
        assert updated["progress"] == 42
        assert store.update_job("ghost", {"progress": 1}) is False

    def test_remove_job_once(self) -> None:
        store = make_jobs_store()
        store.add_job("j1", {"status": "processing"})
        assert store.remove_job("j1") is True
        assert store.remove_job("j1") is False

    def test_get_all_jobs_returns_copies(self) -> None:
        store = make_jobs_store()
        store.add_job("j1", {"status": "processing"})
        snapshot = store.get_all_jobs()
        snapshot["j1"]["status"] = "mutated"
        snapshot["extra"] = {}
        stored = store.get_job("j1")
        assert stored is not None
        assert stored["status"] == "processing"
        assert "extra" not in store

    def test_contains_and_getitem(self) -> None:
        store = make_jobs_store()
        store.add_job("j1", {"status": "processing"})
        assert "j1" in store
        assert "ghost" not in store
        assert store["j1"]["status"] == "processing"
        with pytest.raises(KeyError, match="ghost"):
            store["ghost"]

    def test_setitem_preserves_existing_timestamp(self) -> None:
        store = make_jobs_store()
        stamp = datetime.now(UTC) - timedelta(hours=1)
        store["j1"] = {"status": "completed", "timestamp": stamp}
        stored = store.get_job("j1")
        assert stored is not None
        assert stored["timestamp"] == stamp

    def test_force_cleanup_removes_only_old_terminal_jobs(self) -> None:
        store = make_jobs_store()
        old = datetime.now(UTC) - timedelta(hours=48)
        store.add_job("old-completed", {"status": "completed"}, timestamp=old)
        store.add_job("old-running", {"status": "processing"}, timestamp=old)
        store.add_job("fresh", {"status": "completed"})
        assert store.force_cleanup() == 1
        assert "old-completed" not in store
        assert "old-running" in store
        assert "fresh" in store

    def test_missing_job_id_raises_keyerror_on_getitem(self) -> None:
        store = make_jobs_store()
        with pytest.raises(KeyError):
            _ = store["nope"]


class TestStateManager:
    def test_get_state_creates_and_reuses(self) -> None:
        manager = StateManager()
        first = manager.get_state("session-1")
        second = manager.get_state("session-1")
        assert first is second
        other = manager.get_state("session-2")
        assert other is not first

    def test_remove_state(self) -> None:
        manager = StateManager()
        first = manager.get_state("session-1")
        manager.remove_state("session-1")
        replacement = manager.get_state("session-1")
        assert replacement is not first

    def test_session_state_context_cleans_up(self) -> None:
        manager = StateManager()
        with manager.session_state("session-1") as session:
            assert session is manager.get_state("session-1")
        with pytest.raises(KeyError):
            _ = manager._states["session-1"]


class TestGetRequestState:
    def test_session_id_routes_to_manager(self) -> None:
        assert get_request_state("session-1") is state_manager.get_state("session-1")

    def test_no_session_id_returns_global_state(self) -> None:
        assert get_request_state() is state

    def test_module_singletons_are_distinct(self) -> None:
        assert translation_jobs is not None
        assert state is not state_manager.get_state("__unused__")
