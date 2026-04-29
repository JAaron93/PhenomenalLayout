"""Asynchronous document processing orchestrator.

Implements an async pipeline that coordinates:
- Direct submission of document bytes/pages to OCR (IO-bound) with basic
- rate limiting
- Layout-aware translation via asyncio batching
- PDF reconstruction (CPU-bound)

This module complements the synchronous processor by providing a drop-in
async alternative for higher throughput and responsive servers.
"""

import asyncio
import inspect
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

import httpx

from dolphin_ocr.layout import BoundingBox, FontInfo
from services import dolphin_client
from services.layout_aware_translation_service import (
    LayoutAwareTranslationService,
    TextBlock,
)
from services.ocr_utils import parse_ocr_result
from services.pdf_document_reconstructor import (
    PDFDocumentReconstructor,
    TranslatedElement,
    TranslatedLayout,
    TranslatedPage,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AsyncProcessingOptions:
    """Options for async processing pipeline."""

    dpi: int = 300
    output_path: str | None = None


@dataclass(frozen=True)
class AsyncDocumentRequest:
    """Request parameters for async processing.

    Attributes:
        file_path: Input PDF path on disk.
        source_language: Source language code.
        target_language: Target language code.
        options: Pipeline options such as DPI and output path.
    """

    file_path: str
    source_language: str
    target_language: str
    options: AsyncProcessingOptions = field(
        default_factory=AsyncProcessingOptions
    )


class _TokenBucket:
    """Integer-based token bucket without busy-waiting.

    Uses integer "micro-tokens" to avoid floating drift and computes the
    exact sleep required when the bucket is empty.
    """

    _SCALE = 1_000_000  # micro-tokens per token

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity_tokens = max(1, int(capacity))
        # convert to micro-token units
        self.capacity_micro = self.capacity_tokens * self._SCALE
        self.tokens_micro = self.capacity_micro
        # refill rate in micro-tokens/second (at least 1 to progress)
        rate = max(0.0, float(refill_rate))
        self.refill_per_sec_micro = max(1, int(rate * self._SCALE))
        self._last = time.perf_counter()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while self.tokens_micro < self._SCALE:
                now = time.perf_counter()
                elapsed = now - self._last
                add = int(elapsed * self.refill_per_sec_micro)
                if add:
                    self.tokens_micro = min(
                        self.capacity_micro, self.tokens_micro + add
                    )
                    self._last = now
                    if self.tokens_micro >= self._SCALE:
                        break
                # compute precise sleep time for at least one token
                deficit = self._SCALE - self.tokens_micro
                wait = deficit / float(self.refill_per_sec_micro)
                await asyncio.sleep(wait)
                self._last = time.perf_counter()
            # consume one token
            self.tokens_micro -= self._SCALE


class LayoutServiceError(Exception):
    """Base class for errors related to the layout service."""
    pass


class LayoutServiceTransientError(LayoutServiceError):
    """Transient errors that might succeed on retry.

    Includes network issues, 5xx, etc.
    """
    pass


class LayoutServiceFatalError(LayoutServiceError):
    """Fatal errors that should not be retried.

    Includes 4xx, invalid file, etc.
    """
    pass


class AsyncDocumentProcessor:
    """Async orchestrator for document processing with basic concurrency.

    Concurrency model:
    - IO-bound OCR/translation: asyncio tasks with batching and limits
    - Request concurrency: semaphore to cap concurrent requests
    - Provider rate-limiting: token bucket for OCR calls
    """

    def __init__(
        self,
        *,
        translation_service: LayoutAwareTranslationService,
        reconstructor: PDFDocumentReconstructor,
        max_concurrent_requests: int = 4,
        translation_batch_size: int = 100,
        translation_concurrency: int = 4,
        ocr_rate_capacity: int = 2,
        ocr_rate_per_sec: float = 1.0,
        ocr_max_retries: int = 3,
    ) -> None:
        """Initialize the async processor.

        Parameters mirror the synchronous processor but add concurrency and
        rate-limiting controls suitable for async execution.
        """
        self._translator = translation_service
        self._reconstructor = reconstructor

        # Validate concurrency and rate parameters early for clearer errors
        validated_req_max = int(max_concurrent_requests)
        validated_trans_conc = int(translation_concurrency)
        validated_batch_size = int(translation_batch_size)
        validated_ocr_capacity = int(ocr_rate_capacity)
        validated_ocr_rate = float(ocr_rate_per_sec)
        validated_ocr_retries = int(ocr_max_retries)

        if validated_req_max <= 0:
            raise ValueError("max_concurrent_requests must be >= 1")
        if validated_trans_conc <= 0:
            raise ValueError("translation_concurrency must be >= 1")
        if validated_batch_size <= 0:
            raise ValueError("translation_batch_size must be >= 1")
        if validated_ocr_capacity <= 0:
            raise ValueError("ocr_rate_capacity must be >= 1")
        if validated_ocr_rate <= 0:
            raise ValueError("ocr_rate_per_sec must be > 0")
        if validated_ocr_retries <= 0:
            raise ValueError("ocr_max_retries must be >= 1")

        self._req_sema = asyncio.Semaphore(validated_req_max)
        self._tg_limit = validated_trans_conc
        self._batch_size = validated_batch_size
        self._ocr_bucket = _TokenBucket(
            validated_ocr_capacity,
            validated_ocr_rate,
        )
        self._ocr_max_retries = validated_ocr_retries

    async def process_document(
        self,
        request: AsyncDocumentRequest,
        *,
        on_progress: Callable[[str, dict], object] | None = None,
    ) -> TranslatedLayout:
        """Run the full async pipeline and return a TranslatedLayout."""

        async def _report(stage: str, payload: dict) -> None:
            if not on_progress:
                return
            try:
                result = on_progress(stage, payload)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                # Progress callbacks must never crash the pipeline
                logger.warning(
                    "Progress callback error for stage %s with payload %s: %s",
                    stage,
                    {k: type(v).__name__ for k, v in payload.items()},
                    e
                )
                return

        async with self._req_sema:
            await _report("validated", {"path": request.file_path})

            # 1) OCR (rate-limited, direct PDF submission with retry)
            max_retries = self._ocr_max_retries
            ocr_result = None
            for attempt in range(max_retries):
                await self._ocr_bucket.acquire()
                try:
                    ocr_result = await dolphin_client.get_layout(
                        request.file_path
                    )
                    break
                except FileNotFoundError as e:
                    logger.error(
                        "OCR failed: PDF file not found at %s: %s",
                        request.file_path,
                        e,
                    )
                    raise LayoutServiceFatalError(
                        f"PDF not found: {request.file_path}"
                    ) from e
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    is_transient = status == 429 or 500 <= status < 600
                    msg = (
                        f"OCR service returned status {status} for "
                        f"{request.file_path}: {e.response.text}"
                    )
                    if is_transient and attempt < max_retries - 1:
                        logger.warning(
                            "%s. Retrying (%d/%d)...",
                            msg,
                            attempt + 1,
                            max_retries,
                        )
                        await asyncio.sleep(
                            (2**attempt) + random.uniform(0, 1)
                        )
                        continue
                    logger.error(msg)
                    if is_transient:
                        raise LayoutServiceTransientError(msg) from e
                    raise LayoutServiceFatalError(msg) from e
                except (httpx.RequestError, TimeoutError) as e:
                    msg = (
                        f"OCR service network error for {request.file_path}: "
                        f"{type(e).__name__}: {e}"
                    )
                    if attempt < max_retries - 1:
                        logger.warning(
                            "%s. Retrying (%d/%d)...",
                            msg,
                            attempt + 1,
                            max_retries,
                        )
                        await asyncio.sleep(
                            (2**attempt) + random.uniform(0, 1)
                        )
                        continue
                    logger.error(msg)
                    raise LayoutServiceTransientError(msg) from e
                except ValueError as e:
                    msg = (
                        f"OCR service returned invalid response for "
                        f"{request.file_path}: {e}"
                    )
                    logger.error(msg)
                    raise LayoutServiceFatalError(msg) from e
                except Exception as e:
                    logger.error(
                        "Unexpected OCR failure for %s: %s",
                        request.file_path,
                        e,
                    )
                    raise LayoutServiceFatalError(
                        f"Unexpected OCR failure: {e}"
                    ) from e

            # defensive: should be unreachable; protects against refactors
            assert ocr_result is not None

            await _report("ocr", {"pages": len(ocr_result.get("pages", []))})

            # 3) Build TextBlocks
            blocks_per_page = parse_ocr_result(ocr_result)

            # 4) Translation with batching + concurrency
            all_blocks: list[TextBlock] = []
            for blocks in blocks_per_page:
                all_blocks.extend(blocks)

            translations: list = [None] * len(all_blocks)

            async def _translate_batch(
                start_index: int, batch: list[TextBlock]
            ) -> None:
                result = await asyncio.to_thread(
                    self._translator.translate_document_batch,
                    text_blocks=batch,
                    source_lang=request.source_language,
                    target_lang=request.target_language,
                )
                for idx, value in enumerate(result):
                    translations[start_index + idx] = value

            async def _bounded_worker(
                start_index: int,
                batch: list[TextBlock],
                sema: asyncio.Semaphore,
            ) -> None:
                async with sema:
                    await _translate_batch(start_index, batch)

            sema = asyncio.Semaphore(self._tg_limit)
            async with asyncio.TaskGroup() as tg:  # Python 3.11+
                for i in range(0, len(all_blocks), self._batch_size):
                    batch = all_blocks[i:i + self._batch_size]
                    tg.create_task(_bounded_worker(i, batch, sema))

            await _report("translated", {"count": len(all_blocks)})

            # 5) Map back to pages and build TranslatedLayout
            pages: list[TranslatedPage] = []
            ti = 0
            for page_blocks in blocks_per_page:
                elems: list[TranslatedElement] = []
                for _ in page_blocks:
                    t = translations[ti]
                    if t is None:
                        raise RuntimeError(
                            f"Translation at index {ti} is None"
                        )
                    elems.append(
                        TranslatedElement(
                            original_text=t.source_text,
                            translated_text=t.raw_translation,
                            adjusted_text=t.adjusted_text,
                            bbox=BoundingBox(
                                t.adjusted_bbox.x,
                                t.adjusted_bbox.y,
                                t.adjusted_bbox.width,
                                t.adjusted_bbox.height,
                            ),
                            font_info=FontInfo(
                                family=t.adjusted_font.family,
                                size=t.adjusted_font.size,
                                weight=t.adjusted_font.weight,
                                style=t.adjusted_font.style,
                                color=t.adjusted_font.color,
                            ),
                            layout_strategy=t.strategy.type.value,
                            confidence=t.translation_confidence,
                        )
                    )
                    ti += 1
                pages.append(
                    TranslatedPage(
                        page_number=len(pages) + 1,
                        translated_elements=elems,
                    )
                )

            layout = TranslatedLayout(pages=pages)

            # 6) Reconstruct (run blocking task off the loop)
            output_path = request.options.output_path or _default_output_path(
                request.file_path
            )
            await asyncio.to_thread(
                self._reconstructor.reconstruct_pdf_document,
                translated_layout=layout,
                original_file_path=request.file_path,
                output_path=output_path,
            )

            await _report("reconstructed", {"output_path": output_path})

            return layout

    async def aclose(self) -> None:
        """No-op: this processor holds no owned resources."""
        pass

    def close(self) -> None:
        """No-op: this processor holds no owned resources."""
        pass

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        pass

    def __del__(self) -> None:
        """Safe no-op destructor."""
        pass

    # -------------------------- Helpers --------------------------


def _default_output_path(input_path: str) -> str:
    """Return default output path for a translated PDF next to input."""
    p = Path(input_path)
    if not p.suffix:
        raise ValueError(
            "Input path must be a file with an extension: " f"{input_path}"
        )
    return str(p.with_name(f"{p.stem}.translated.pdf"))
