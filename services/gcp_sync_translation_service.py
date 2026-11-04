"""GCP synchronous translation engine for the content tier (ADR 0004).

Exposes :class:`GcpSyncTranslator` (a user-bound engine) and
:class:`GcpSyncTranslationService` (a registry facade) which together replace
the retired Lingo.dev stack as the engine behind the non-book translation
endpoints (``/translate``, ``/philosophy/*``).

Design invariants (ADR 0004):

* **BYOK-only** — every remote call resolves the caller's own credentials via
  the injected :class:`~services.byok_credentials_manager.BYOKCredentialsManager`.
  No host-held API keys, no ambient environment credentials, no silent
  providers. Missing credentials raise
  :class:`GcpSyncCredentialsRequiredError` (fail-closed, ``GCP_CREDENTIALS_REQUIRED``).
* **Non-blocking I/O** — the synchronous ``google-cloud-translate`` calls
  execute inside :func:`asyncio.to_thread` workers so the event loop is never
  blocked (AGENTS deny row: Blocking Sync I/O in Async Paths).
* **Canonical retry routing** — transient GCP errors (429/500/503, gRPC 8/14)
  are retried exclusively through :func:`utils.gcp_helpers.retry_gcp_call`
  (truncated exponential backoff with jitter); no bespoke retry loops.
* **Deterministic client closure** — translation clients vended by the BYOK
  manager are constructed per call and ``close()``-d in ``finally`` blocks
  (AGENTS §2.10 zero resource leakage).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, BinaryIO

from google.cloud import translate_v3 as translate

from services.byok_credentials_manager import (
    BYOKCredentialsManager,
    CredentialNotFoundError,
)
from utils.gcp_helpers import retry_gcp_call

logger: logging.Logger = logging.getLogger(__name__)

#: GCP region for all sync-tier translate calls (aligned with regional glossaries).
GCP_SYNC_REGION: str = "us-central1"

#: Default chunk size for batch text translation (env: ``TRANSLATION_BATCH_SIZE``).
_DEFAULT_BATCH_SIZE: int = 50

#: Stable machine-readable statistics keys surfaced by engine and facade.
STATS_KEYS: tuple[str, ...] = (
    "total_calls",
    "translated_texts",
    "translated_documents",
    "errors",
)

_ONBOARDING_HINT: str = (
    "No personal Google Cloud credentials are configured for this session. "
    "Upload and validate your Service Account JSON key via "
    "POST /api/v1/byok/credentials, or review the onboarding guide at "
    "GET /api/v1/byok/onboarding-guide."
)

#: Precompiled post-translation marker cleanup pattern (static, module-level).
_NOTRANSLATE_SPAN_RE: re.Pattern[str] = re.compile(
    r"<span translate=\"no\">(.*?)</span>", re.IGNORECASE
)


class GcpSyncCredentialsRequiredError(RuntimeError):
    """Fail-closed error when a user lacks usable BYOK credentials.

    Raised instead of silently substituting a provider (ADR 0004 D3). The API
    layer maps this to HTTP 503 with the ``GCP_CREDENTIALS_REQUIRED`` code.

    Attributes:
        code: Stable machine-readable error code consumed by the API layer.
        user_id: Identifier whose credentials were missing or unusable.
    """

    code: str = "GCP_CREDENTIALS_REQUIRED"

    def __init__(self, user_id: str) -> None:
        """Initialize the error for an affected user.

        Args:
            user_id: Identifier whose credentials were missing or unusable.
        """
        super().__init__(
            f"No usable GCP credentials for user_id={user_id}. {_ONBOARDING_HINT}"
        )
        self.user_id: str = user_id


def _wrap_no_translate_terms(text: str, terminology_map: dict[str, str]) -> str:
    """Wrap preserved source terms in ``translate="no"`` spans.

    Word-boundary-safe parity port of the legacy
    ``services.translation_service.TranslationService._apply_terminology``:
    each mapped *key* (a source-language term to preserve) is wrapped, while
    inflected neighbors such as ``Geisterstadt`` remain untouched. Map values
    are ignored, matching the legacy behavior.

    Args:
        text: Raw source text before the remote call.
        terminology_map: Mapping of source terms to preserve (values unused).

    Returns:
        Text with no-translate span wrappers applied.
    """
    processed: str = text
    for source in terminology_map:
        pattern: str = rf"(?<!\w){re.escape(source)}(?!\w)"
        processed = re.sub(pattern, f'<span translate="no">{source}</span>', processed)
    return processed


def _strip_no_translate_spans(text: str) -> str:
    """Strip any ``translate="no"`` wrappers from a translated response.

    Word-boundary-safe parity port of the legacy
    ``services.translation_service.TranslationService._strip_non_translate_tags``.

    Args:
        text: Translated text as returned by the remote engine.

    Returns:
        Text with wrapper markup removed and preserved terms inlined.
    """
    return _NOTRANSLATE_SPAN_RE.sub(r"\1", text)


def _normalize_language_code(code: str) -> str:
    """Normalize a language code for the v3 API.

    Two-letter alpha codes are lower-cased (``"DE"`` → ``"de"``); script or
    region suffixed codes (e.g. ``"de-DE"``) are passed through unchanged with
    surrounding whitespace stripped.

    Args:
        code: User-facing language code such as ``"DE"`` or ``"en-US"``.

    Returns:
        Normalized language code.

    Raises:
        TypeError: If *code* is not a string.
        ValueError: If *code* is empty.
    """
    if not isinstance(code, str):
        raise TypeError("language code must be a string")
    stripped: str = code.strip()
    if not stripped:
        raise ValueError("language code must not be empty")
    if len(stripped) == 2 and stripped.isalpha():
        return stripped.lower()
    return stripped


def _resolve_batch_size() -> int:
    """Resolve the batch chunk size from the environment at call time.

    Reads ``TRANSLATION_BATCH_SIZE`` (default 50) with a floor of 1; invalid
    values fall back to the default with a warning.

    Returns:
        Effective batch size used to chunk batch requests.
    """
    raw: str = os.getenv("TRANSLATION_BATCH_SIZE", str(_DEFAULT_BATCH_SIZE))
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning(
            "Invalid TRANSLATION_BATCH_SIZE %r; using default %d",
            raw,
            _DEFAULT_BATCH_SIZE,
        )
        return _DEFAULT_BATCH_SIZE


def _chunked(items: list[str], size: int) -> list[list[str]]:
    """Split *items* into consecutive chunks of at most *size* elements.

    Args:
        items: Payload items to chunk.
        size: Maximum chunk size (must be >= 1).

    Returns:
        List of chunks preserving element order.
    """
    if size < 1:
        size = 1
    return [items[start : start + size] for start in range(0, len(items), size)]


@dataclass
class _GcpSyncStats:
    """Mutable statistics counters for one bound engine."""

    total_calls: int = 0
    translated_texts: int = 0
    translated_documents: int = 0
    errors: int = 0

    def snapshot(self) -> dict[str, int]:
        """Return a plain-dict snapshot keyed by :data:`STATS_KEYS`.

        Returns:
            Dict with all :data:`STATS_KEYS` counters.
        """
        return {
            "total_calls": self.total_calls,
            "translated_texts": self.translated_texts,
            "translated_documents": self.translated_documents,
            "errors": self.errors,
        }


class GcpSyncTranslator:
    """User-bound synchronous Google Cloud Translation engine (BYOK-only).

    One instance represents one user's content-tier engine. Translation
    requests resolve a fresh ``translate_v3.TranslationServiceClient`` from
    the injected :class:`~services.byok_credentials_manager.BYOKCredentialsManager`
    per invocation and always close it deterministically afterwards.

    Attributes:
        PROVIDER_NAME: Stable provider registry name reported to consumers.
        user_id: Identifier whose BYOK credentials all calls use.
        terminology_map: Source terms preserved (untranslated) in output.
    """

    PROVIDER_NAME: str = "gcp"

    def __init__(
        self,
        credentials_manager: BYOKCredentialsManager,
        user_id: str,
        *,
        terminology_map: dict[str, str] | None = None,
        retry_max_retries: int = 5,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 30.0,
    ) -> None:
        """Initialize the bound engine.

        Args:
            credentials_manager: BYOK vault vending per-user credentials.
                Mandatory — the engine never holds host credentials.
            user_id: Identifier whose credentials all remote calls use.
            terminology_map: Optional mapping of source terms to preserve.
            retry_max_retries: Max retry attempts after the initial failure.
            retry_base_delay: Base exponential backoff delay in seconds.
            retry_max_delay: Backoff ceiling in seconds.

        Raises:
            ValueError: If *credentials_manager* is ``None`` or *user_id*
                is blank — host-held credentials are structurally impossible.
        """
        if credentials_manager is None:
            raise ValueError(
                "GcpSyncTranslator requires a BYOKCredentialsManager — "
                "host-held credentials are not permitted (ADR 0004 D2)."
            )
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("GcpSyncTranslator requires a non-blank user_id.")
        if retry_max_retries < 0:
            raise ValueError("retry_max_retries must be >= 0")

        self._credentials_manager: BYOKCredentialsManager = credentials_manager
        self.user_id: str = user_id.strip()
        self.terminology_map: dict[str, str] = dict(terminology_map or {})
        self._retry_max_retries: int = retry_max_retries
        self._retry_base_delay: float = retry_base_delay
        self._retry_max_delay: float = retry_max_delay
        self._stats: _GcpSyncStats = _GcpSyncStats()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def translate_text(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        """Translate one string through the sync tier.

        Args:
            text: Source text (blank input short-circuits to ``""``).
            source_lang: Source language code (normalized 2-letter bodies).
            target_lang: Target language code.

        Returns:
            The translated string with terminology markers stripped.

        Raises:
            GcpSyncCredentialsRequiredError: If the user has no usable.
                BYOK credentials (fail-closed; never a silent substitute).
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        self._stats.total_calls += 1
        try:
            if not text.strip():
                return ""
            processed: str = _wrap_no_translate_terms(text, self.terminology_map)
            outputs: list[str] = await self._translate_contents_async(
                [processed], source_lang, target_lang
            )
            return _strip_no_translate_spans(outputs[0])
        except Exception:
            self._stats.errors += 1
            raise

    async def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str
    ) -> list[str]:
        """Translate a batch of strings preserving order and 1:1 mapping.

        Chunked by ``TRANSLATION_BATCH_SIZE`` (default 50); blank items are
        preserved locally and never sent to the API.

        Args:
            texts: Source strings (order preserved 1:1 in the result).
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            Translated strings aligned with the input order.

        Raises:
            GcpSyncCredentialsRequiredError: If the user has no usable
                BYOK credentials.
        """
        if texts is None:
            raise TypeError("texts must be a list of strings")
        self._stats.total_calls += 1
        try:
            if not texts:
                return []
            processed: list[str] = [
                (
                    _wrap_no_translate_terms(item, self.terminology_map)
                    if isinstance(item, str) and item.strip()
                    else ""
                )
                for item in texts
            ]
            active_indexes: list[int] = [
                index for index, item in enumerate(processed) if item.strip()
            ]
            if not active_indexes:
                return ["" for _ in texts]
            payload: list[str] = [processed[i] for i in active_indexes]
            outputs: list[str] = await self._translate_contents_async(
                payload, source_lang, target_lang
            )
            results: list[str] = ["" for _ in texts]
            for index, output in zip(active_indexes, outputs, strict=True):
                results[index] = _strip_no_translate_spans(output)
            self._stats.translated_texts += len(active_indexes)
            return results
        except Exception:
            self._stats.errors += 1
            raise

    async def translate_document(
        self,
        document: BinaryIO,
        mime_type: str,
        source_lang: str,
        target_lang: str,
    ) -> BinaryIO:
        """Translate one document via the sync preview tier (≤ sample pages).

        Honors AGENTS §2.1: synchronous ``translateDocument`` is the preview
        mechanism for 1–3 sample pages; books stay on the batch tier.

        Args:
            document: Seekable or non-seekable stream providing source bytes.
                Read exactly once by the engine inside its worker thread;
                the caller retains ownership of the stream.
            mime_type: Source and output MIME type (e.g. ``application/pdf``).
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            A :class:`io.BytesIO` with the translated document bytes.

        Raises:
            ValueError: If the document produces no bytes.
            GcpSyncCredentialsRequiredError: If the user has no usable
                BYOK credentials.
            RuntimeError: If the service returns no byte-stream output.
        """
        if not isinstance(mime_type, str) or not mime_type.strip():
            raise ValueError("mime_type is required")
        self._stats.total_calls += 1

        def worker() -> bytes:
            """Read the stream, call translateDocuments, close the client."""
            client, project_id = self._resolve_runtime()
            try:
                data: bytes = document.read()
                if not data:
                    raise ValueError("source document produced no bytes")
                request = translate.TranslateDocumentRequest(
                    parent=(f"projects/{project_id}/locations/{GCP_SYNC_REGION}"),
                    document_input_config=translate.DocumentInputConfig(
                        content=data, mime_type=mime_type
                    ),
                    source_language_code=_normalize_language_code(source_lang),
                    target_language_code=_normalize_language_code(target_lang),
                    document_output_config=translate.DocumentOutputConfig(
                        mime_type=mime_type
                    ),
                )
                response: Any = retry_gcp_call(
                    lambda: client.translate_document(request=request),
                    max_retries=self._retry_max_retries,
                    base_delay=self._retry_base_delay,
                    max_delay=self._retry_max_delay,
                )
                outputs: Any = getattr(
                    response.document_translation, "byte_stream_outputs", None
                )
                if not outputs:
                    raise RuntimeError(
                        "sync document translation produced no byte-stream " "output"
                    )
                first: Any = outputs[0]
                return first if isinstance(first, bytes) else bytes(first)
            finally:
                client.close()

        try:
            data: bytes = await asyncio.to_thread(worker)
        except Exception:
            self._stats.errors += 1
            raise
        self._stats.translated_documents += 1
        return io.BytesIO(data)

    def get_statistics(self) -> dict[str, Any]:
        """Return stable statistics for engine telemetry.

        Returns:
            Dict keyed by :data:`STATS_KEYS` (+ ``bound_user`` identity).
        """
        snapshot: dict[str, Any] = self._stats.snapshot()
        snapshot["bound_user"] = self.user_id
        return snapshot

    def close(self) -> None:
        """Release engine-owned resources (no-op; BYOK owns the clients)."""
        return None

    async def aclose(self) -> None:
        """Async lifecycle wrapper (no-op; BYOK owns the clients)."""
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_runtime(
        self,
    ) -> tuple[translate.TranslationServiceClient, str]:
        """Borrow a translation client and project id from the BYOK vault.

        Returns:
            Tuple of (translation client, GCP project id).

        Raises:
            GcpSyncCredentialsRequiredError: If the credentials vanished.
        """
        try:
            if not self._credentials_manager.has_credentials(self.user_id):
                raise GcpSyncCredentialsRequiredError(self.user_id)
            client: translate.TranslationServiceClient = (
                self._credentials_manager.get_translation_client(self.user_id)
            )
            project_id: str = self._credentials_manager.get_project_id(self.user_id)
        except CredentialNotFoundError as exc:
            raise GcpSyncCredentialsRequiredError(self.user_id) from exc
        return client, project_id

    def _translate_text_once(
        self,
        client: translate.TranslationServiceClient,
        project_id: str,
        contents: list[str],
        source_code: str,
        target_code: str,
    ) -> list[str]:
        """Issue one v3 ``translateText`` request and extract translations.

        Args:
            client: Authenticated translation client.
            project_id: Caller's GCP project id.
            contents: Pre-processed chunk contents.
            source_code: Normalized source language code.
            target_code: Normalized target language code.

        Returns:
            Translated strings aligned with *contents*.

        Raises:
            RuntimeError: If the response length does not match the chunk.
        """
        request = translate.TranslateTextRequest(
            parent=f"projects/{project_id}/locations/{GCP_SYNC_REGION}",
            contents=list(contents),
            mime_type="text/plain",
            source_language_code=source_code,
            target_language_code=target_code,
        )
        response: Any = client.translate_text(request=request)
        translations: list[str] = [
            str(item.translated_text) for item in response.translations
        ]
        if len(translations) != len(contents):
            raise RuntimeError(
                "v3 returned "
                f"{len(translations)} translations for {len(contents)} "
                "contents"
            )
        return translations

    async def _translate_contents_async(
        self,
        contents: list[str],
        source_lang: str,
        target_lang: str,
    ) -> list[str]:
        """Chunk *contents* and translate them off the event loop.

        A single client is borrowed for the whole invocation (deterministic
        closure in ``finally``); chunks are processed consecutively so total
        concurrency stays bounded (AGENTS NFR-3).

        Args:
            contents: Pre-processed strings to translate.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            Translated strings aligned with *contents*.
        """

        def worker() -> list[str]:
            """Run the chunked remote translation inside a worker thread."""
            client, project_id = self._resolve_runtime()
            batch_size: int = _resolve_batch_size()
            source_code: str = _normalize_language_code(source_lang)
            target_code: str = _normalize_language_code(target_lang)
            try:
                collected: list[str] = []
                for chunk in _chunked(contents, batch_size):
                    collected.extend(
                        retry_gcp_call(
                            self._translate_text_once,
                            client,
                            project_id,
                            chunk,
                            source_code,
                            target_code,
                            max_retries=self._retry_max_retries,
                            base_delay=self._retry_base_delay,
                            max_delay=self._retry_max_delay,
                        )
                    )
                return collected
            finally:
                client.close()

        return await asyncio.to_thread(worker)


class GcpSyncTranslationService:
    """Registry facade consumed by ``core.translation_handler`` (ADR 0004).

    Surface parity with the retired ``TranslationService``: consumers bind a
    user via :meth:`translator_for_user` and get a
    :class:`GcpSyncTranslator` whose calls use that user's BYOK credentials.
    The facade itself owns **no** credentials and never translates.

    Attributes:
        providers: Snapshot of bound engines keyed by ``user_id``.
    """

    def __init__(self, credentials_manager: BYOKCredentialsManager) -> None:
        """Initialize the facade over a BYOK vault.

        Args:
            credentials_manager: BYOK vault the engines borrow clients from.

        Raises:
            ValueError: If *credentials_manager* is ``None``.
        """
        if credentials_manager is None:
            raise ValueError(
                "GcpSyncTranslationService requires a "
                "BYOKCredentialsManager (ADR 0004 D2)."
            )
        self._credentials_manager: BYOKCredentialsManager = credentials_manager
        self._translators: dict[str, GcpSyncTranslator] = {}
        self._lock: threading.Lock = threading.Lock()

    def translator_for_user(
        self,
        user_id: str,
        *,
        terminology_map: dict[str, str] | None = None,
    ) -> GcpSyncTranslator:
        """Return (and cache) the engine bound to *user_id*'s credentials.

        A cached engine is reused when its terminology map matches;
        a changed map triggers a rebuild.

        Args:
            user_id: Identifier whose credentials the engine must use.
            terminology_map: Optional explicit terminology map override.

        Returns:
            The bound :class:`GcpSyncTranslator`.

        Raises:
            ValueError: If *user_id* is blank.
        """
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id is required to bind a GCP engine")
        with self._lock:
            existing: GcpSyncTranslator | None = self._translators.get(user_id)
            if existing is not None and (
                existing.terminology_map == dict(terminology_map or {})
            ):
                return existing
            translator = GcpSyncTranslator(
                self._credentials_manager,
                user_id,
                terminology_map=terminology_map,
            )
            self._translators[user_id] = translator
            return translator

    @property
    def providers(self) -> dict[str, GcpSyncTranslator]:
        """Return bound engines keyed by ``user_id`` (snapshot copy).

        Unlike the legacy name-keyed registry, engines are session-scoped:
        each entry's remote calls strictly use that user's BYOK credentials.
        """
        with self._lock:
            return dict(self._translators)

    def get_available_providers(self) -> list[str]:
        """Return available provider names (surface parity).

        Returns:
            ``["gcp"]`` — the sync tier provider, key-stable for the
            philosophy config endpoint.
        """
        return [GcpSyncTranslator.PROVIDER_NAME]

    def get_statistics(self) -> dict[str, Any]:
        """Aggregate engine statistics for the config/status endpoints.

        Returns:
            Dict containing every :data:`STATS_KEYS` counter (summed across
            bound engines) plus ``bound_engines``.
        """
        with self._lock:
            engines: list[GcpSyncTranslator] = list(self._translators.values())
        totals: dict[str, Any] = dict.fromkeys(STATS_KEYS, 0)
        for engine in engines:
            for key, value in engine.get_statistics().items():
                if key in totals and isinstance(value, int):
                    totals[key] += value
        totals["bound_engines"] = len(engines)
        return totals

    def update_configuration(self, **kwargs: Any) -> None:
        """Philosophy-layer configuration passthrough (surface parity).

        The engine owns no policy configuration of its own; kwargs accepted
        for legacy call parity are dispatched to the philosophy service by
        ``core.translation_handler``. Explicit no-op.

        Args:
            **kwargs: Ignored legacy passthrough arguments.
        """
        return None

    def close(self) -> None:
        """Release facade resources (no-op; BYOK owns client lifecycles)."""
        return None

    async def aclose(self) -> None:
        """Async lifecycle wrapper (no-op; BYOK owns client lifecycles)."""
        return None
