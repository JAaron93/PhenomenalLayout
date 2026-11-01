import asyncio
from typing import Any

import pytest

# Target module
from core.translation_handler import translate_content


class StubPhilosophyService:
    def __init__(self, behavior: dict[str, Any]):
        """
        behavior: mapping of input text -> action
        - value is a string: return that as translated_text
        - value is Exception subclass instance to raise
        """
        self.behavior = behavior

    async def translate_text_with_neologism_handling_async(
        self,
        *,
        text: str,
        source_lang: str,  # noqa: ARG002  (keyword-only provider protocol)
        target_lang: str,  # noqa: ARG002  (keyword-only provider protocol)
        provider: str,  # noqa: ARG002  (keyword-only provider protocol)
        session_id: str,  # noqa: ARG002  (keyword-only provider protocol)
    ) -> dict[str, str]:
        action = self.behavior.get(text)
        if isinstance(action, Exception):
            raise action
        if isinstance(action, str):
            return {"translated_text": action}
        # default: echo with suffix to show it was processed
        return {"translated_text": text + "_X"}


@pytest.mark.asyncio
async def test_per_item_failure_falls_back_and_batch_continues(monkeypatch):
    # Arrange content with one page and three elements
    content = {
        "type": "pdf_advanced",
        "text_by_page": {0: ["ok", "fail", "ok2"]},
    }

    # Stub service: translate ok -> OK_T, ok2 -> OK2_T, fail -> raise Exception
    behavior = {
        "ok": "OK_T",
        "ok2": "OK2_T",
        "fail": RuntimeError("boom"),
    }
    stub = StubPhilosophyService(behavior)

    # Patch the philosophy service used inside translate_content
    import core.translation_handler as th

    monkeypatch.setattr(th, "philosophy_translation_service", stub, raising=True)

    # Act
    translated_by_page, output_filename = await translate_content(
        content=content,
        source_language="en",
        target_language="es",
        max_pages=None,
        progress_callback=None,
        philosophy_mode=True,
        session_id="test-session",
    )

    # Assert: failing element falls back to original, others translated
    page0 = translated_by_page[0]
    assert page0 == ["OK_T", "fail", "OK2_T"]
    # output filename is produced by caller; translate_content just returns a suggestion
    assert isinstance(output_filename, str)


@pytest.mark.asyncio
async def test_cancelled_error_propagates(monkeypatch):
    # Arrange
    content = {
        "type": "pdf_advanced",
        "text_by_page": {0: ["ok", "cancel"]},
    }

    behavior = {
        "ok": "OK_T",
        "cancel": asyncio.CancelledError(),
    }
    stub = StubPhilosophyService(behavior)

    import core.translation_handler as th

    monkeypatch.setattr(th, "philosophy_translation_service", stub, raising=True)

    # Act + Assert: CancelledError should bubble up
    with pytest.raises(asyncio.CancelledError):
        await translate_content(
            content=content,
            source_language="en",
            target_language="es",
            max_pages=None,
            progress_callback=None,
            philosophy_mode=True,
            session_id="test-session",
        )
