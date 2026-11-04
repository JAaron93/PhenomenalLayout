import asyncio
import contextlib

import pytest

from core import translation_handler
from core.state_manager import state
from services.gcp_sync_translation_service import GcpSyncTranslator


class _EngineLeakManager:
    """Credentials-manager stub with an empty vault (engine fail-closed)."""

    def __init__(self) -> None:
        """Empty vault: no user ever holds credentials."""
        self.credentialed_users: set[str] = set()

    def has_credentials(self, user_id: str) -> bool:
        """Report credential presence — always false for the empty vault."""
        return user_id in self.credentialed_users


@pytest.mark.asyncio
async def test_start_translation_single_flight_cancels_previous(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    started_event = asyncio.Event()
    cancel_observed = asyncio.Event()

    async def fake_perform() -> None:
        started.append("started")
        started_event.set()
        try:
            # Block until cancelled.
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancel_observed.set()
            raise

    # Capture original global state
    old_file = state.current_file
    old_content = state.current_content
    old_lang = state.source_language

    try:
        monkeypatch.setattr(
            translation_handler,
            "perform_advanced_translation",
            fake_perform,
        )

        state.current_file = "dummy.pdf"
        state.current_content = {
            "type": "pdf_advanced",
            "text_by_page": {"1": ["x"]},
        }
        state.source_language = "en"

        res1 = await translation_handler.start_translation("de", 0, False)
        is_ready = res1[2]
        assert not is_ready
        first_task = state.get_tracked_translation_task()
        assert first_task is not None

        await asyncio.wait_for(started_event.wait(), timeout=2.0)

        res2 = await translation_handler.start_translation("fr", 0, False)
        is_ready2 = res2[2]
        assert not is_ready2
        second_task = state.get_tracked_translation_task()
        assert second_task is not None
        assert second_task is not first_task

        await asyncio.sleep(0)

        await asyncio.wait_for(cancel_observed.wait(), timeout=2.0)

        assert len(started) == 2

    finally:
        # Cleanup task if it exists
        task = state.get_tracked_translation_task()
        if task is not None:
            state.cancel_tracked_translation_task()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            state.drop_tracked_translation_task()

        # Restore original global state
        state.current_file = old_file
        state.current_content = old_content
        state.source_language = old_lang


def test_gcp_engine_close_never_retains_resources() -> None:
    """Engine close() is a safe lifecycle no-op; BYOK owns all resources.

    Replaces the Lingo-era session-close test: the GCP sync engine holds no
    host-side session, so close cycles must leave it state-stable.
    """
    translator = GcpSyncTranslator(_EngineLeakManager(), "leak-user")
    before = translator.get_statistics()

    translator.close()
    translator.close()

    assert translator.get_statistics() == before
