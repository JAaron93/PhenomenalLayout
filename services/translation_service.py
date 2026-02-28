"""Translation service for Dolphin OCR Translate with Lingo.dev provider support."""

from __future__ import annotations

import asyncio
import copy
import inspect
import logging
import math
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Optional

import requests

try:
    # Prefer relative import when part of a package
    from .mcp_lingo_client import McpLingoClient, McpLingoConfig  # type: ignore
except (ModuleNotFoundError, ImportError):  # pragma: no cover - fallback
    # Fallback absolute import when running as a flat module
    from services.mcp_lingo_client import McpLingoClient, McpLingoConfig  # type: ignore

# Translation service configuration
TRANSLATION_DELAY: float = float(
    os.getenv("TRANSLATION_DELAY", "0.1")
)  # Delay between batch requests in seconds

# Configurable User-Agent header
USER_AGENT: str = os.getenv("DOLPHIN_USER_AGENT", "Dolphin-OCR-Translate/2.0")

logger: logging.Logger = logging.getLogger(__name__)


class BaseTranslator(ABC):
    """Abstract base class for translation providers."""

    @abstractmethod
    async def translate_text(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        """Translate a single text string."""
        pass

    @abstractmethod
    async def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        """Translate a batch of text strings."""
        pass


class LingoTranslator(BaseTranslator):
    """Lingo.dev translation implementation."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize Lingo translator with API key and session configuration.

        If api_key is not provided, read from the LINGO_API_KEY environment variable.
        Passing an empty string explicitly is treated as invalid.
        """
        if api_key is None:
            api_key = os.getenv("LINGO_API_KEY")
            if isinstance(api_key, str):
                api_key = api_key.strip()
        # Normalize any provided key as well
        if isinstance(api_key, str):
            api_key = api_key.strip()
        if not api_key:
            raise ValueError("LINGO_API_KEY is required")

        self.api_key: str = api_key
        self.base_url: str = "https://api.lingo.dev/v1/translate"
        self.session: requests.Session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            }
        )

    def close(self) -> None:
        """Close underlying HTTP session resources."""
        try:
            self.session.close()
        except Exception:
            logger.exception("Failed to close LingoTranslator session")

    async def translate_text(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        """Translate text using Lingo.dev API."""
        try:
            if not text.strip():
                return text

            payload: dict[str, str] = {
                "text": text,
                "source": source_lang.lower(),
                "target": target_lang.lower(),
            }

            response: requests.Response = await asyncio.to_thread(
                self.session.post, self.base_url, json=payload, timeout=30
            )

            if response.status_code == 200:
                result: dict[str, Any] = response.json()
                if "translation" in result:
                    return result["translation"]
                elif "text" in result:
                    return result["text"]
                else:
                    logger.warning(f"Unexpected Lingo response format: {result}")
                    return text
            else:
                logger.error(
                    f"Lingo HTTP error {response.status_code}: {response.text}"
                )
                return text

        except Exception as e:
            logger.error(f"Lingo translation error: {e}")
            return text

    async def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        """Translate batch of texts using Lingo.dev."""
        results: list[str] = []

        # Process texts individually for better error handling
        for text in texts:
            if not text.strip():
                results.append(text)
                continue

            translated: str = await self.translate_text(text, source_lang, target_lang)
            results.append(translated)

            # Configurable delay between batch requests to avoid rate limiting
            await asyncio.sleep(TRANSLATION_DELAY)

        return results


class MCPLingoTranslator(BaseTranslator):
    """Lingo.dev translation via MCP server (stdio)."""

    def __init__(self, config: McpLingoConfig) -> None:
        """Initialize MCP Lingo translator with an explicit configuration.

        This avoids mutating private attributes after construction and ensures
        the client is configured in a single place.
        """
        if not config or not getattr(config, "api_key", None):
            raise ValueError("Valid McpLingoConfig with api_key is required for MCP")
        self._client: McpLingoClient = McpLingoClient(config)
        self._started: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()

    async def _ensure_started(self) -> None:
        if self._started:
            return
        async with self._lock:
            if not self._started:
                await self._client.start()
                self._started = True

    async def translate_text(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        await self._ensure_started()
        try:
            return await self._client.translate_text(text, source_lang, target_lang)
        except Exception as e:
            logger.error(f"MCP Lingo translate_text error: {e}")
            return text

    async def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        await self._ensure_started()
        try:
            return await self._client.translate_batch(texts, source_lang, target_lang)
        except Exception as e:
            logger.error(f"MCP Lingo translate_batch error: {e}")
            return texts

    async def aclose(self) -> None:
        """Stop the underlying MCP session if it was started."""
        async with self._lock:
            if not self._started:
                return
            try:
                await self._client.stop()
            finally:
                self._started = False

    def close(self) -> None:
        """Best-effort synchronous cleanup.

        MCP shutdown is inherently async; this method triggers `aclose()`.
        """
        logger.warning(
            "MCPLingoTranslator.close() is best-effort; "
            "use aclose() for reliable cleanup"
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(self.aclose())
            except Exception:
                logger.exception(
                    "Failed to aclose MCPLingoTranslator from close()"
                )
            return

        try:
            loop.create_task(self.aclose())
        except Exception:
            logger.exception(
                "Failed to schedule MCPLingoTranslator.aclose() from close()"
            )


def _parse_positive_float_env(name: str, default: float) -> float:
    """Parse a positive float environment variable with validation and logging.

    Args:
        name: Environment variable name
        default: Default value to use if parsing fails

    Returns:
        Parsed float value or default if validation fails
    """
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid %s value '%s', using default %.1f", name, raw_value, default
        )
        return default

    if not math.isfinite(value) or value <= 0:
        logger.warning(
            "Invalid %s value %.1f (must be finite and positive), using default %.1f",
            name,
            value,
            default,
        )
        return default

    return value


class TranslationService:
    """Main translation service with Lingo.dev provider."""

    def __init__(self, terminology_map: Optional[dict[str, str]] = None) -> None:
        """Initialize translation service with optional terminology mapping."""
        # Mapping of provider name to translator instance
        self.providers: dict[str, BaseTranslator] = {}
        # Optional terminology mapping for preprocessing
        self.terminology_map: dict[str, str] = terminology_map or {}
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize Lingo.dev translation provider (REST or MCP)."""
        try:
            lingo_key: Optional[str] = os.getenv("LINGO_API_KEY")
            use_mcp: bool = os.getenv("LINGO_USE_MCP", "false").lower() == "true"
            # Startup diagnostics to make provider selection explicit in logs
            logger.info(
                "Translation provider config: LINGO_USE_MCP=%s, LINGO_API_KEY_present=%s",
                use_mcp,
                bool(lingo_key),
            )

            if lingo_key:
                if use_mcp:
                    # Read MCP config from environment at runtime
                    tool_name: Optional[str] = os.getenv("LINGO_MCP_TOOL_NAME") or None
                    startup_timeout: float = _parse_positive_float_env(
                        "LINGO_MCP_STARTUP_TIMEOUT", 20.0
                    )
                    call_timeout: float = _parse_positive_float_env(
                        "LINGO_MCP_CALL_TIMEOUT", 60.0
                    )

                    cfg: McpLingoConfig = McpLingoConfig(
                        api_key=lingo_key,
                        tool_name=tool_name,
                        startup_timeout_s=startup_timeout,
                        call_timeout_s=call_timeout,
                    )
                    # Pass through PATH and env
                    cfg.env = os.environ.copy()
                    # Construct translator with config to avoid mutating private client attributes
                    self.providers["lingo"] = MCPLingoTranslator(cfg)
                    logger.info(
                        "Using Lingo.dev via MCP server (stdio): provider=lingo"
                    )
                else:
                    self.providers["lingo"] = LingoTranslator(lingo_key)
                    logger.info("Using Lingo.dev REST API: provider=lingo")
            else:
                raise ValueError("LINGO_API_KEY not found in environment variables")
        except Exception as e:
            logger.error(f"Failed to initialize Lingo translator: {e}")
            raise

    def get_available_providers(self) -> list[str]:
        """Get list of available translation providers."""
        return list(self.providers.keys())

    def close(self) -> None:
        """Best-effort synchronous cleanup of provider resources."""
        for name, provider in list(self.providers.items()):
            close_fn = getattr(provider, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    logger.exception("Failed to close provider %s", name)

    async def aclose(self) -> None:
        """Best-effort async cleanup of provider resources."""
        for name, provider in list(self.providers.items()):
            aclose_fn = getattr(provider, "aclose", None)
            if callable(aclose_fn):
                try:
                    result = aclose_fn()
                    if inspect.isawaitable(result):
                        await result
                    continue
                except Exception:
                    logger.exception("Failed to aclose provider %s", name)

            close_fn = getattr(provider, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    logger.exception("Failed to close provider %s", name)

    async def translate_batch(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
    ) -> list[str]:
        """Translate a list of texts using Lingo.dev provider."""
        if provider == "auto":
            provider = self._select_best_provider()

        if provider not in self.providers:
            raise ValueError(f"Provider {provider} not available")

        translator: BaseTranslator = self.providers[provider]
        batch_texts: list[str] = texts.copy()

        # Apply optional terminology preprocessing
        if self.terminology_map:
            batch_texts = [self._apply_terminology(t) for t in batch_texts]

        try:
            translated: list[str] = await translator.translate_batch(
                batch_texts, source_lang, target_lang
            )
            # Strip non-translate tags after translation
            translated = [self._strip_non_translate_tags(t) for t in translated]
            return translated
        except Exception as e:
            logger.error(f"Batch translation failed with provider {provider}: {e}")
            return texts  # Fallback to original texts

    async def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
    ) -> str:
        """Translate a single text string using Lingo.dev provider."""
        if not text.strip():
            return text  # Nothing to translate

        # Apply optional terminology preprocessing
        if self.terminology_map:
            text = self._apply_terminology(text)

        if provider == "auto":
            provider = self._select_best_provider()

        if provider not in self.providers:
            raise ValueError(f"Provider {provider} not available")

        translator: BaseTranslator = self.providers[provider]
        try:
            translated: str = await translator.translate_text(
                text, source_lang, target_lang
            )
            return self._strip_non_translate_tags(translated)
        except Exception as e:
            logger.error(f"Translation failed with provider {provider}: {e}")
            return text

    async def translate_document(
        self,
        content: dict[str, Any],
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> dict[str, Any]:
        """Translate document content."""
        # Select provider
        if provider == "auto":
            provider = self._select_best_provider()

        if provider not in self.providers:
            raise ValueError(f"Provider {provider} not available")

        translator: BaseTranslator = self.providers[provider]

        # Extract text blocks for translation
        text_blocks: list[dict[str, Any]] = self._extract_text_blocks(content)
        total_blocks: int = len(text_blocks)

        if progress_callback:
            progress_callback(0)

        # Process in batches for efficiency
        batch_size: int = 20
        translated_blocks: list[dict[str, Any]] = []

        for i in range(0, total_blocks, batch_size):
            batch: list[dict[str, Any]] = text_blocks[i: i + batch_size]
            batch_texts: list[str] = [block["text"] for block in batch]

            # Apply terminology preprocessing if configured
            if self.terminology_map:
                batch_texts = [self._apply_terminology(t) for t in batch_texts]

            # Perform batch translation with the selected provider
            translated_texts: list[str] = await translator.translate_batch(
                batch_texts, source_lang, target_lang
            )
            # Strip tags
            translated_texts = [
                self._strip_non_translate_tags(t) for t in translated_texts
            ]

            # Merge translated texts back into their respective blocks
            for j, translated_text in enumerate(translated_texts):
                block: dict[str, Any] = batch[j].copy()
                block["text"] = translated_text
                translated_blocks.append(block)

            # Update progress
            if progress_callback:
                progress: int = min(100, int((i + len(batch)) / total_blocks * 100))
                progress_callback(progress)

        # Reconstruct document with translated content
        translated_content: dict[str, Any] = self._reconstruct_document(
            content, translated_blocks
        )

        if progress_callback:
            progress_callback(100)

        return translated_content

    def _select_best_provider(self) -> str:
        """Select the best available provider (always Lingo.dev)."""
        if "lingo" in self.providers:
            return "lingo"

        raise ValueError("No translation providers available")

    def _extract_text_blocks(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract text blocks from document content for translation."""
        text_blocks: list[dict[str, Any]] = []

        if "pages" in content:
            for page_num, page in enumerate(content["pages"]):
                if "text_elements" in page:
                    for element in page["text_elements"]:
                        if element.get("text", "").strip():
                            text_blocks.append(
                                {
                                    "text": element["text"],
                                    "page": page_num,
                                    "element_id": element.get("id"),
                                    "metadata": element,
                                }
                            )

        return text_blocks

    def _reconstruct_document(
        self, original_content: dict[str, Any], translated_blocks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Reconstruct document with translated text blocks."""
        # Use a deep copy to avoid mutating nested structures in the original
        translated_content: dict[str, Any] = copy.deepcopy(original_content)

        # Create a mapping of translated blocks by page and element
        block_map: dict[int, dict[Optional[str], str]] = {}
        for block in translated_blocks:
            page_num: int = block["page"]
            element_id: Optional[str] = block.get("element_id")
            if page_num not in block_map:
                block_map[page_num] = {}
            # Only index valid element IDs
            if element_id is not None:
                block_map[page_num][element_id] = block["text"]

        # Update the content with translated text
        if "pages" in translated_content:
            for page_num, page in enumerate(translated_content["pages"]):
                # Defensive check on page and expected key
                if page and page_num in block_map and "text_elements" in page:
                    for element in page["text_elements"]:
                        # Skip any null entries
                        if element:
                            element_id: Optional[str] = element.get("id")
                            if (
                                element_id is not None
                                and element_id in block_map[page_num]
                            ):
                                element["text"] = block_map[page_num][element_id]

        return translated_content

    def _strip_non_translate_tags(self, text: str) -> str:
        """Remove <span translate="no"> wrappers from translated text."""
        return re.sub(
            r"<span translate=\"no\">(.*?)</span>", r"\1", text, flags=re.IGNORECASE
        )

    def _apply_terminology(self, text: str) -> str:
        """Replace terms in text using self.terminology_map with word-boundary safety."""
        processed: str = text
        for source in self.terminology_map:
            # Wrap term in HTML span with translate="no" to preserve it
            pattern: str = rf"(?<!\w){re.escape(source)}(?!\w)"
            processed = re.sub(
                pattern, f'<span translate="no">{source}</span>', processed
            )
        return processed
