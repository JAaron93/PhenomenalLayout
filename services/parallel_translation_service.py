"""Parallel translation service for Dolphin OCR Translate document processing.

This module implements parallelized translation with bounded concurrency,
robust error handling, and order preservation:
- Bounded concurrency: An asyncio.Semaphore limits in-flight requests while a
  token-bucket RateLimiter smooths request bursts and enforces per-second caps.
- Error handling: Each task retries with exponential backoff for transient
  failures (timeouts, 5xx, 429), surfaces structured errors, and never raises
  unhandled exceptions from the batch API.
- Order preservation: Caller-facing helpers map results back to the original
  input order using stable indices stored in task metadata.

All logging is done via a module-level logger and avoids emitting raw text
payloads or full response bodies to minimize sensitive data exposure.
"""

import asyncio
import email.utils
import inspect
import logging
import os
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import ClientSession, ClientTimeout

# Import will be done locally to avoid circular imports

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Get version from pyproject.toml or fallback to default."""
    try:
        # Try to get version from pyproject.toml
        import toml

        project_root = Path(__file__).parent.parent
        pyproject_path = project_root / "pyproject.toml"

        if pyproject_path.exists():
            with open(pyproject_path, encoding="utf-8") as f:
                pyproject_data = toml.load(f)
                version = (
                    pyproject_data.get("tool", {}).get("poetry", {}).get("version")
                )
                if version:
                    return version
    except (ImportError, Exception):
        pass

    try:
        # Fallback to pkg_resources
        import pkg_resources

        return pkg_resources.get_distribution("PhenomenalLayout").version
    except (ImportError, Exception):
        pass

    # Final fallback to environment variable or default
    return os.getenv("APP_VERSION", "2.0.0")


# Module-level constants
USER_AGENT = f"PhenomenalLayout-Parallel/{_get_version()}"

# Maximum allowed Retry-After delay to prevent pathologically long sleeps
MAX_RETRY_AFTER_SECONDS = 60.0


@dataclass
class ParallelTranslationConfig:
    """Configuration for parallel translation operations."""

    # Concurrency settings
    max_concurrent_requests: int = 10
    max_requests_per_second: float = 5.0
    batch_size: int = 50

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0
    backoff_multiplier: float = 2.0

    # Timeout settings
    request_timeout: float = 30.0
    total_timeout: float = 300.0

    # Rate limiting
    rate_limit_window: float = 1.0
    burst_allowance: int = 2

    @classmethod
    def from_config(cls) -> "ParallelTranslationConfig":
        """Create configuration from environment/config settings."""
        import os

        return cls(
            max_concurrent_requests=int(os.getenv("MAX_CONCURRENT_REQUESTS", "10")),
            max_requests_per_second=float(os.getenv("MAX_REQUESTS_PER_SECOND", "5.0")),
            batch_size=int(os.getenv("TRANSLATION_BATCH_SIZE", "50")),
            max_retries=int(os.getenv("TRANSLATION_MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("TRANSLATION_RETRY_DELAY", "1.0")),
            backoff_multiplier=float(
                os.getenv("TRANSLATION_BACKOFF_MULTIPLIER", "2.0")
            ),
            request_timeout=float(os.getenv("TRANSLATION_REQUEST_TIMEOUT", "30.0")),
            total_timeout=float(os.getenv("TRANSLATION_TOTAL_TIMEOUT", "300.0")),
            rate_limit_window=float(os.getenv("TRANSLATION_RATE_LIMIT_WINDOW", "1.0")),
            burst_allowance=int(os.getenv("TRANSLATION_BURST_ALLOWANCE", "2")),
        )


@dataclass
class TranslationTask:
    """Individual translation task."""

    text: str
    source_lang: str
    target_lang: str
    task_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TranslationResult:
    """Result of a translation task."""

    task_id: str
    original_text: str
    translated_text: str
    success: bool
    error: str | None = None
    retry_count: int = 0
    processing_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchProgress:
    """Progress tracking for batch operations."""

    total_tasks: int
    completed_tasks: int = 0
    failed_tasks: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total_tasks == 0:
            return 100.0
        return (self.completed_tasks / self.total_tasks) * 100.0

    @property
    def elapsed_time(self) -> float:
        """Calculate elapsed time in seconds."""
        return time.time() - self.start_time

    @property
    def estimated_remaining_time(self) -> float:
        """Estimate remaining time in seconds."""
        if self.completed_tasks == 0 or self.elapsed_time < 0.001:
            return 0.0

        rate = self.completed_tasks / self.elapsed_time
        remaining_tasks = self.total_tasks - self.completed_tasks
        return remaining_tasks / rate if rate > 0 else 0.0


class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, max_requests_per_second: float, burst_allowance: int = 2):
        """Initialize rate limiter with token bucket parameters."""
        self.max_requests_per_second = max_requests_per_second
        self.burst_allowance = burst_allowance
        # Start with burst tokens only; refill up to max + burst
        self.tokens = float(burst_allowance)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update

            # Add tokens based on elapsed time
            self.tokens = min(
                self.max_requests_per_second + self.burst_allowance,
                self.tokens + elapsed * self.max_requests_per_second,
            )
            self.last_update = now

            # Wait if no tokens available
            if self.tokens < 1:
                wait_time = max(
                    0.0, (1 - self.tokens) / max(1e-9, self.max_requests_per_second)
                )
                await asyncio.sleep(wait_time)
                # After waiting, consume one token
                self.last_update = time.time()
                self.tokens = max(
                    0.0, self.tokens + (wait_time * self.max_requests_per_second) - 1
                )
            else:
                self.tokens -= 1


class ParallelLingoTranslator:
    """High-performance parallel translator using Lingo API."""

    def __init__(
        self,
        api_key: str,
        config: ParallelTranslationConfig | None = None,
        base_url: str | None = None,
    ):
        """Initialize parallel translator with API configuration and rate limiting."""
        if not api_key:
            raise ValueError("LINGO_API_KEY is required")

        self.api_key = api_key
        self.base_url = base_url or "https://api.lingo.dev/v1/translate"
        self.config = config or ParallelTranslationConfig.from_config()

        # Rate limiting
        self.rate_limiter = RateLimiter(
            self.config.max_requests_per_second, self.config.burst_allowance
        )

        # Concurrency control
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

        # Session will be created when needed
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "ParallelLingoTranslator":
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    def _parse_retry_after(self, header_val: str | None) -> float:
        """Parse Retry-After header value and return seconds to wait.

        Handles both numeric seconds and RFC 7231 HTTP-date formats.
        Returns a float >= 1.0, capped at MAX_RETRY_AFTER_SECONDS to prevent
        pathologically long sleeps from unreasonable server responses.

        Args:
            header_val: The Retry-After header value (can be numeric seconds or HTTP date)

        Returns:
            float: Seconds to wait, guaranteed to be >= 1.0 and <= MAX_RETRY_AFTER_SECONDS
        """
        if not header_val:
            return 1.0

        # Try parsing as numeric seconds first
        try:
            retry_seconds = float(header_val)
            # Cap at maximum to prevent excessively long sleeps
            return max(1.0, min(retry_seconds, MAX_RETRY_AFTER_SECONDS))
        except (ValueError, TypeError):
            pass

        # Try parsing as HTTP date
        try:
            # Parse RFC 7231 HTTP-date format
            parsed_date = email.utils.parsedate_to_datetime(header_val)
            if parsed_date.tzinfo is None:
                # Assume UTC if no timezone specified
                parsed_date = parsed_date.replace(tzinfo=UTC)

            # Calculate seconds from now
            now = datetime.now(UTC)
            seconds_diff = (parsed_date - now).total_seconds()

            # Ensure minimum of 1.0 seconds, cap at maximum
            return max(1.0, min(seconds_diff, MAX_RETRY_AFTER_SECONDS))
        except (ValueError, TypeError):
            # Any parsing error falls back to 1.0 seconds
            return 1.0

    async def _ensure_session(self) -> ClientSession:
        """Ensure aiohttp session is created."""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(
                total=self.config.total_timeout, sock_read=self.config.request_timeout
            )

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            }

            self._session = ClientSession(
                timeout=timeout,
                headers=headers,
                connector=aiohttp.TCPConnector(
                    limit=self.config.max_concurrent_requests * 2,
                    limit_per_host=self.config.max_concurrent_requests,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                ),
            )

        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _translate_single_with_retry(
        self, task: TranslationTask
    ) -> TranslationResult:
        """Translate a single text with retry logic."""
        start_time = time.time()
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                # Rate limiting
                await self.rate_limiter.acquire()

                # Concurrency control
                async with self.semaphore:
                    session = await self._ensure_session()

                    payload = {
                        "text": task.text,
                        "source": task.source_lang.lower(),
                        "target": task.target_lang.lower(),
                    }

                    async with session.post(self.base_url, json=payload) as response:
                        if response.status == 200:
                            result = await response.json()
                            translated_text = self._extract_translation(result)

                            return TranslationResult(
                                task_id=task.task_id,
                                original_text=task.text,
                                translated_text=translated_text,
                                success=True,
                                retry_count=attempt,
                                processing_time=time.time() - start_time,
                                metadata=task.metadata,
                            )

                        if response.status == 429:  # Rate limited
                            header_val = response.headers.get("Retry-After")
                            retry_after = self._parse_retry_after(header_val)
                            await asyncio.sleep(retry_after)
                            last_error = (
                                f"Rate limited (429), retry after {retry_after}s"
                            )
                            continue

                        # Handle other HTTP errors. Avoid logging or storing full response bodies.
                        _ = await response.text()
                        last_error = f"HTTP {response.status}"

                        # Don't retry on client errors (4xx except 429)
                        if 400 <= response.status < 500 and response.status != 429:
                            break

            except TimeoutError:
                last_error = "Request timeout"
            except aiohttp.ClientError as e:
                last_error = f"Client error: {e}"
            except Exception as e:  # pylint: disable=broad-except
                last_error = f"Unexpected error: {e}"

            # Wait before retry (exponential backoff, respect server retry-after)
            if attempt < self.config.max_retries:
                delay = self.config.retry_delay * (
                    self.config.backoff_multiplier**attempt
                )
                # For 429 errors, use the maximum of server retry-after and exponential backoff
                if response.status == 429 and "retry_after" in locals():
                    delay = max(retry_after, delay)
                await asyncio.sleep(delay)

        # All retries failed
        return TranslationResult(
            task_id=task.task_id,
            original_text=task.text,
            translated_text=task.text,  # Return original on failure
            success=False,
            error=last_error,
            retry_count=self.config.max_retries,
            processing_time=time.time() - start_time,
            metadata=task.metadata,
        )

    def _extract_translation(self, response_data: dict[str, Any]) -> str:
        """Extract translation from API response."""
        if "translation" in response_data:
            return response_data["translation"]
        if "text" in response_data:
            return response_data["text"]

        # Avoid logging full response bodies. Log only high-level structure.
        logger.warning(
            "Unexpected Lingo response format: keys=%s", list(response_data.keys())
        )
        raise ValueError("Invalid response format")

    async def translate_batch_parallel(
        self,
        tasks: list[TranslationTask],
        progress_callback: Callable[[BatchProgress], None] | None = None,
    ) -> list[TranslationResult]:
        """Translate multiple tasks in parallel with bounded concurrency.

        - Concurrency is bounded by an asyncio.Semaphore; per-second throughput
          is smoothed by a token-bucket RateLimiter.
        - Each task retries on transient errors with exponential backoff. The
          function never raises; exceptions are converted into failed
          TranslationResult instances.
        - Ordering: The returned list preserves the 1:1 mapping to input tasks
          via their metadata indices, enabling callers to reconstruct original
          order deterministically.
        """
        if not tasks:
            return []

        # Initialize progress tracking
        progress = BatchProgress(total_tasks=len(tasks))

        if progress_callback:
            progress_callback(progress)

        # Create semaphore for progress updates
        progress_lock = asyncio.Lock()

        async def translate_with_progress(task: TranslationTask) -> TranslationResult:
            """Translate task and update progress."""
            result = await self._translate_single_with_retry(task)

            async with progress_lock:
                if result.success:
                    progress.completed_tasks += 1
                else:
                    progress.failed_tasks += 1

                if progress_callback:
                    progress_callback(progress)

            return result

        # Execute all tasks concurrently
        results = await asyncio.gather(
            *[translate_with_progress(task) for task in tasks], return_exceptions=True
        )

        # Handle any exceptions that weren't caught
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Unhandled exception for task %s: %s", tasks[i].task_id, result
                )
                final_results.append(
                    TranslationResult(
                        task_id=tasks[i].task_id,
                        original_text=tasks[i].text,
                        translated_text=tasks[i].text,
                        success=False,
                        error=str(result),
                        processing_time=0.0,
                        metadata=tasks[i].metadata,
                    )
                )
            else:
                final_results.append(result)

        return final_results

    async def translate_texts_parallel(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[BatchProgress], None] | None = None,
    ) -> list[str]:
        """Translate a list of texts in parallel (simplified interface)."""
        if not texts:
            return []

        # Create tasks
        tasks = [
            TranslationTask(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                task_id=f"task_{i}",
                metadata={"index": i},
            )
            for i, text in enumerate(texts)
        ]

        # Execute parallel translation
        results = await self.translate_batch_parallel(tasks, progress_callback)

        # Extract translated texts in original order
        translated_texts = [""] * len(texts)
        for result in results:
            index = result.metadata.get("index")
            if index is not None and 0 <= index < len(texts):
                translated_texts[index] = result.translated_text
            else:
                logger.warning(
                    "Invalid or missing index in result metadata: %s", result.task_id
                )
        return translated_texts

    async def translate_document_parallel(
        self,
        content: dict[str, Any],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[BatchProgress], None] | None = None,
    ) -> dict[str, Any]:
        """Translate document content in parallel."""
        # Extract text blocks for translation
        text_blocks = self._extract_text_blocks(content)

        if not text_blocks:
            return content

        # Create translation tasks
        tasks = []
        for i, (block_id, text) in enumerate(text_blocks):
            if text.strip():  # Only translate non-empty texts
                tasks.append(
                    TranslationTask(
                        text=text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        task_id=block_id,
                        metadata={"block_id": block_id, "index": i},
                    )
                )

        # Execute parallel translation
        results = await self.translate_batch_parallel(tasks, progress_callback)

        # Apply translations back to content
        translated_content = self._apply_translations_to_content(content, results)

        return translated_content

    def _extract_text_blocks(self, content: dict[str, Any]) -> list[tuple[str, str]]:
        """Extract text blocks from document content for translation."""
        text_blocks = []

        # Extract from pages
        for page_num, page_data in content.get("pages", {}).items():
            if isinstance(page_data, dict):
                for block_id, block_text in page_data.items():
                    if isinstance(block_text, str) and block_text.strip():
                        text_blocks.append((f"page_{page_num}_{block_id}", block_text))

        # Extract from layouts if available
        for i, layout in enumerate(content.get("layouts", [])):
            # First check if layout is dict-like (MutableMapping)
            if isinstance(layout, MutableMapping):
                text_val = layout.get("text")
                if isinstance(text_val, str) and text_val.strip():
                    text_blocks.append((f"layout_{i}", text_val))
                    continue  # Skip object handling for this layout

            # Fall through to object handling (unchanged)
            text_attr = getattr(layout, "text", None)
            if isinstance(text_attr, str) and text_attr.strip():
                text_blocks.append((f"layout_{i}", text_attr))

        return text_blocks

    def _apply_translations_to_content(
        self, content: dict[str, Any], results: list[TranslationResult]
    ) -> dict[str, Any]:
        """Apply translation results back to document content."""
        import copy

        # Create translation mapping
        translations = {result.task_id: result.translated_text for result in results}

        # Apply to content structure
        translated_content = copy.deepcopy(content)

        # Apply to pages
        if "pages" in translated_content:
            for page_num, page_data in translated_content["pages"].items():
                if isinstance(page_data, dict):
                    for block_id, _block_text in page_data.items():
                        translation_key = f"page_{page_num}_{block_id}"
                        if translation_key in translations:
                            page_data[block_id] = translations[translation_key]

        # Apply to layouts
        if "layouts" in translated_content:
            for i, layout in enumerate(translated_content["layouts"]):
                translation_key = f"layout_{i}"
                if translation_key in translations:
                    # Cache translation value to avoid repeated lookups
                    translated_text = translations[translation_key]

                    if isinstance(layout, MutableMapping) and "text" in layout:
                        layout["text"] = translated_text
                    elif hasattr(layout, "text"):
                        # Check if the 'text' attribute is writable to avoid read-only properties
                        try:
                            # Use inspect to check if it's a settable attribute
                            text_attr = inspect.getattr_static(
                                layout.__class__, "text", None
                            )
                            if (
                                text_attr is None
                                or not isinstance(text_attr, property)
                                or text_attr.fset is not None
                            ):
                                layout.text = translated_text
                            else:
                                logger.warning(
                                    "Layout %s 'text' attribute is read-only, cannot apply translation",
                                    i,
                                )
                        except (AttributeError, TypeError) as e:
                            logger.warning(
                                "Layout %s 'text' attribute assignment failed: %s",
                                i,
                                str(e),
                            )
                    else:
                        logger.warning(
                            "Layout %s has no 'text' attribute/key to apply translation",
                            i,
                        )

        return translated_content


class ParallelTranslationService:
    """High-level service for parallel document translation."""

    def __init__(
        self, api_key: str, config: ParallelTranslationConfig | None = None
    ):
        """Initialize parallel translation service with API key and configuration."""
        self.api_key = api_key
        self.config = config or ParallelTranslationConfig.from_config()
        self._translator: ParallelLingoTranslator | None = None

    async def __aenter__(self) -> "ParallelTranslationService":
        """Async context manager entry."""
        self._translator = ParallelLingoTranslator(self.api_key, self.config)
        await self._translator.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._translator:
            await self._translator.__aexit__(exc_type, exc_val, exc_tb)

    async def translate_large_document(
        self,
        content: dict[str, Any],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[BatchProgress], None] | None = None,
    ) -> dict[str, Any]:
        """Translate large document with optimal parallel processing."""
        if not self._translator:
            raise RuntimeError("Service not initialized. Use async context manager.")

        return await self._translator.translate_document_parallel(
            content, source_lang, target_lang, progress_callback
        )

    async def translate_batch_texts(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[BatchProgress], None] | None = None,
    ) -> list[str]:
        """Translate batch of texts with parallel processing."""
        if not self._translator:
            raise RuntimeError("Service not initialized. Use async context manager.")

        return await self._translator.translate_texts_parallel(
            texts, source_lang, target_lang, progress_callback
        )
