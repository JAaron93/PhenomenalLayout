from __future__ import annotations

import asyncio
import math

import pytest

import services.async_document_processor as adp
from dolphin_ocr.layout import LayoutStrategy, StrategyType
from services.layout_aware_translation_service import (
    TextBlock,
    TranslationResult,
)


class FakeOCR:
    def __init__(self, blocks_per_page: int = 4) -> None:
        self.blocks_per_page = blocks_per_page

    def process_document_images(self, images: list[bytes]) -> dict:
        pages = []
        for _ in images:
            text_blocks = []
            for i in range(self.blocks_per_page):
                text_blocks.append(
                    {
                        "text": f"t{i}",
                        "bbox": [10.0, 10.0, 100.0, 20.0],
                        "font_info": {
                            "family": "Helvetica",
                            "size": 12,
                            "weight": "normal",
                            "style": "normal",
                            "color": (0, 0, 0),
                        },
                        "confidence": 0.9,
                    }
                )
            pages.append({"text_blocks": text_blocks})
        return {"pages": pages}


class FakeTranslator:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def translate_document_batch(
        self,
        *,
        text_blocks: list[TextBlock],
        source_lang: str,
        target_lang: str,
    ) -> list[TranslationResult]:
        self.calls.append(len(text_blocks))
        results: list[TranslationResult] = []
        for b in text_blocks:
            strat = LayoutStrategy(
                type=StrategyType.NONE, font_scale=1.0, wrap_lines=1
            )
            results.append(
                TranslationResult(
                    source_text=b.text,
                    raw_translation=b.text + "_tx",
                    adjusted_text=b.text + "_tx",
                    strategy=strat,
                    analysis=None,  # type: ignore[arg-type]
                    adjusted_font=b.layout.font,
                    adjusted_bbox=b.layout.bbox,
                    quality_score=1.0,
                    ocr_confidence=b.layout.ocr_confidence,
                    translation_confidence=0.9,
                )
            )
        return results


class DummyReconstructor:
    def reconstruct_pdf_document(
        self,
        *,
        translated_layout,
        original_file_path: str,
        output_path: str,
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_async_translation_batching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ocr = FakeOCR(blocks_per_page=5)  # 20 blocks total
    translator = FakeTranslator()
    recon = DummyReconstructor()

    async def fake_get_layout(_path):
        return ocr.process_document_images([b"dummy"] * 4)

    monkeypatch.setattr("services.dolphin_client.get_layout", fake_get_layout)

    proc = adp.AsyncDocumentProcessor(
        translation_service=translator,  # type: ignore[arg-type]
        reconstructor=recon,  # type: ignore[arg-type]
        translation_batch_size=6,
        translation_concurrency=3,
        max_concurrent_requests=2,
    )

    req = adp.AsyncDocumentRequest(
        file_path="/tmp/in.pdf",
        source_language="en",
        target_language="de",
    )

    layout = await proc.process_document(req)
    assert len(layout.pages) == 4

    # Expect ceil(20/6) = 4 batches
    assert sum(translator.calls) == 20
    assert len(translator.calls) == math.ceil(20 / 6)


@pytest.mark.asyncio
async def test_token_bucket_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ocr = FakeOCR(blocks_per_page=1)
    translator = FakeTranslator()
    recon = DummyReconstructor()

    async def fake_get_layout(_path):
        return ocr.process_document_images([b"dummy"])

    monkeypatch.setattr("services.dolphin_client.get_layout", fake_get_layout)

    proc = adp.AsyncDocumentProcessor(
        translation_service=translator,  # type: ignore[arg-type]
        reconstructor=recon,  # type: ignore[arg-type]
        ocr_rate_capacity=1,
        ocr_rate_per_sec=100.0,
    )

    calls = {"count": 0}

    async def fake_acquire(_self) -> None:  # type: ignore[override]
        calls["count"] += 1
        await asyncio.sleep(0)

    monkeypatch.setattr(
        adp._TokenBucket, "acquire", fake_acquire, raising=True
    )

    req = adp.AsyncDocumentRequest(
        file_path="/tmp/in.pdf",
        source_language="en",
        target_language="de",
    )
    await proc.process_document(req)
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_concurrency_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ocr = FakeOCR(blocks_per_page=1)
    translator = FakeTranslator()
    recon = DummyReconstructor()

    async def fake_get_layout(_path):
        return ocr.process_document_images([b"dummy"])

    monkeypatch.setattr("services.dolphin_client.get_layout", fake_get_layout)

    proc = adp.AsyncDocumentProcessor(
        translation_service=translator,  # type: ignore[arg-type]
        reconstructor=recon,  # type: ignore[arg-type]
        max_concurrent_requests=2,
        ocr_rate_capacity=100,
        ocr_rate_per_sec=1_000.0,
    )

    active = 0
    max_active = 0

    def on_progress(stage: str, _payload: dict) -> None:
        nonlocal active, max_active
        if stage == "validated":
            active += 1
            max_active = max(max_active, active)
        if stage == "reconstructed":
            active -= 1

    async def run_one(idx: int) -> None:
        req = adp.AsyncDocumentRequest(
            file_path=f"/tmp/in_{idx}.pdf",
            source_language="en",
            target_language="de",
        )
        await proc.process_document(
            req, on_progress=on_progress
        )  # type: ignore[arg-type]

    await asyncio.gather(*(run_one(i) for i in range(6)))
    assert max_active <= 2


@pytest.mark.asyncio
async def test_cleanup_methods_are_no_ops() -> None:
    translator = FakeTranslator()
    recon = DummyReconstructor()
    proc = adp.AsyncDocumentProcessor(
        translation_service=translator,  # type: ignore[arg-type]
        reconstructor=recon,  # type: ignore[arg-type]
    )

    # Test context manager
    async with proc as p:
        assert p is proc

    # Test explicit cleanup calls
    await proc.aclose()
    proc.close()
