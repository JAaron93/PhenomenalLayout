import asyncio

import pytest

from core import translation_handler
from core.state_manager import state
from services.translation_service import LingoTranslator


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
        _, is_running = res1[2]
        assert not is_running
        first_task = state.get_tracked_translation_task()
        assert first_task is not None

        await asyncio.wait_for(started_event.wait(), timeout=2.0)

        res2 = await translation_handler.start_translation("fr", 0, False)
        _, is_running2 = res2[2]
        assert not is_running2
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
            try:
                await task
            except asyncio.CancelledError:
                pass
            state.drop_tracked_translation_task()

        # Restore original global state
        state.current_file = old_file
        state.current_content = old_content
        state.source_language = old_lang


def test_lingo_translator_close_closes_session() -> None:
    translator = LingoTranslator(api_key="unit_test")

    class _Session:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    sess = _Session()
    translator.session = sess  # type: ignore[assignment]

    translator.close()
    assert sess.closed is True
