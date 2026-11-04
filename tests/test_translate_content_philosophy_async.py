import asyncio
import random
from typing import Any

import pytest

# Target under test
from core.translation_handler import translate_content


class FakeTranslator:
    """Async fake used to replace philosophy translator per-item path.

    Tracks in-flight concurrency, max observed concurrency, and total call count.
    Can inject failures for specific inputs (e.g., text == "BOOM").
    """

    def __init__(self, fail_on: str | None = None, random_latency: bool = False):
        self.cur = 0
        self.max = 0
        self.calls = 0
        self.fail_on = fail_on
        self.random_latency = random_latency

    async def translate(self, text: str, **_: Any) -> str:
        # track concurrency
        self.cur += 1
        self.max = max(self.max, self.cur)
        try:
            # add small latency to exercise ordering
            delay = 0.02
            if self.random_latency:
                delay = 0.01 + random.random() * 0.03  # 10-40 ms
            await asyncio.sleep(delay)
        finally:
            # decrement in-flight after work completes
            self.cur -= 1
            self.calls += 1

        if self.fail_on is not None and text == self.fail_on:
            raise RuntimeError("fail")
        return f"T:{text}"


@pytest.mark.asyncio
async def test_preserves_order_with_varied_latencies(monkeypatch: pytest.MonkeyPatch):
    # Arrange: page with multiple items to translate
    content = {
        "type": "pdf_advanced",
        "text_by_page": {0: ["a", "b", "c", "d", "e"]},
    }

    fake = FakeTranslator(random_latency=True)

    # Patch the philosophy translator method used by translate_content
    import core.translation_handler as th

    async def _fake_translate_text_with_neologism_handling(
        *, text: str, **kwargs: Any
    ) -> dict[str, str]:
        res = await fake.translate(text, **kwargs)
        return {"translated_text": res}

    monkeypatch.setattr(
        th.philosophy_translation_service,
        "translate_text_with_neologism_handling_async",
        _fake_translate_text_with_neologism_handling,
        raising=True,
    )

    # Act
    translated_by_page, _ = await translate_content(
        content=content,
        source_language="en",
        target_language="de",
        max_pages=None,
        progress_callback=None,
        philosophy_mode=True,
        session_id="s1",
    )

    # Assert: order preserved exactly
    page0 = translated_by_page[0]
    assert page0 == ["T:a", "T:b", "T:c", "T:d", "T:e"]
    # Some concurrency should have occurred
    assert fake.max >= 2


@pytest.mark.asyncio
async def test_skips_empty_inputs(monkeypatch: pytest.MonkeyPatch):
    # Arrange: include empty and whitespace-only strings
    content = {
        "type": "pdf_advanced",
        "text_by_page": {0: ["", "  ", "x", "y", "   ", "z"]},
    }

    fake = FakeTranslator()

    import core.translation_handler as th

    async def _fake_translate_text_with_neologism_handling(
        *, text: str, **kwargs: Any
    ) -> dict[str, str]:
        res = await fake.translate(text, **kwargs)
        return {"translated_text": res}

    monkeypatch.setattr(
        th.philosophy_translation_service,
        "translate_text_with_neologism_handling_async",
        _fake_translate_text_with_neologism_handling,
        raising=True,
    )

    # Act
    translated_by_page, _ = await translate_content(
        content=content,
        source_language="en",
        target_language="de",
        philosophy_mode=True,
        session_id="s1",
    )

    # Assert: only non-empty inputs translated, empties preserved
    page0 = translated_by_page[0]
    assert page0 == ["", "  ", "T:x", "T:y", "   ", "T:z"]
    non_empty_count = 3
    assert fake.calls == non_empty_count


@pytest.mark.asyncio
async def test_per_item_failure_falls_back(monkeypatch: pytest.MonkeyPatch):
    # Arrange: one item designed to fail
    content = {
        "type": "pdf_advanced",
        "text_by_page": {0: ["ok1", "BOOM", "ok2"]},
    }

    fake = FakeTranslator(fail_on="BOOM")

    import core.translation_handler as th

    async def _fake_translate_text_with_neologism_handling(
        *, text: str, **kwargs: Any
    ) -> dict[str, str]:
        res = await fake.translate(text, **kwargs)
        return {"translated_text": res}

    monkeypatch.setattr(
        th.philosophy_translation_service,
        "translate_text_with_neologism_handling_async",
        _fake_translate_text_with_neologism_handling,
        raising=True,
    )

    # Act
    translated_by_page, _ = await translate_content(
        content=content,
        source_language="en",
        target_language="de",
        philosophy_mode=True,
        session_id="s1",
    )

    # Assert: failed item falls back to original, others are translated
    page0 = translated_by_page[0]
    assert page0 == ["T:ok1", "BOOM", "T:ok2"]


@pytest.mark.asyncio
async def test_respects_concurrency_limit(monkeypatch: pytest.MonkeyPatch):
    # Arrange: many items and a strict concurrency limit
    content = {
        "type": "pdf_advanced",
        "text_by_page": {0: [f"t{i}" for i in range(40)]},
    }

    # Patch settings to limit concurrency to 5
    import core.translation_handler as th

    # ensure the instantiated settings object reflects the limit (auto-restored)
    monkeypatch.setattr(th.settings, "TRANSLATION_CONCURRENCY_LIMIT", 5, raising=True)

    fake = FakeTranslator(random_latency=False)

    async def _fake_translate_text_with_neologism_handling(
        *, text: str, **kwargs: Any
    ) -> dict[str, str]:
        res = await fake.translate(text, **kwargs)
        return {"translated_text": res}

    monkeypatch.setattr(
        th.philosophy_translation_service,
        "translate_text_with_neologism_handling_async",
        _fake_translate_text_with_neologism_handling,
        raising=True,
    )

    # Act
    await translate_content(
        content=content,
        source_language="en",
        target_language="de",
        philosophy_mode=True,
        session_id="s1",
    )

    # Assert: max observed concurrency should not exceed 5
    assert fake.max <= 5


@pytest.mark.asyncio
async def test_non_philosophy_path_unchanged(monkeypatch: pytest.MonkeyPatch):
    # Arrange: verify non-philosophy path behavior: empties preserved, order restored
    texts: list[str] = ["", "A", "  ", "B", "C", ""]
    content = {
        "type": "pdf_advanced",
        "text_by_page": {0: texts},
    }

    # ADR 0004 Track B: the non-philosophy path runs a credential-bound
    # engine resolved at submission time. Capture batch calls on the stub.

    captured_batches: list[list[str]] = []

    class _CapturingEngine:
        """User-bound engine stub recording translate_batch inputs."""

        async def translate_batch(
            self, texts: list[str], _source_lang: str, _target_lang: str
        ) -> list[str]:
            # record what we actually receive
            captured_batches.append(list(texts))
            # simulate work
            await asyncio.sleep(0.01)
            return [f"T:{t}" for t in texts]

    engine = _CapturingEngine()

    _ = monkeypatch  # patch point retained for engine-level tests

    # Act: non-philosophy path (engine bound explicitly, as the route does)
    translated_by_page, _ = await translate_content(
        content=content,
        source_language="en",
        target_language="de",
        philosophy_mode=False,  # important: go through non-philosophy branch
        session_id=None,
        translator=engine,
    )

    # Assert: batch received only the non-empty items in their relative order
    assert len(captured_batches) >= 1
    received = captured_batches[0]
    expected_non_empty = ["A", "B", "C"]
    assert received == expected_non_empty

    # Outputs preserve positions; empties unchanged
    page0 = translated_by_page[0]
    assert page0 == ["", "T:A", "  ", "T:B", "T:C", ""]
