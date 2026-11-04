"""Philosophy-Enhanced Translation Service with Neologism Detection and User Choice Management."""

from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import functools
import json
import logging
import re
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from core.dynamic_choice_engine import OptimizedUserChoiceManager as UserChoiceManager
from models.neologism_models import DetectedNeologism, NeologismAnalysis
from models.user_choice_models import ChoiceType, UserChoice

from .gcp_sync_translation_service import GcpSyncCredentialsRequiredError
from .neologism_detector import NeologismDetector

logger = logging.getLogger(__name__)


class UnboundTranslationStub:
    """Statistics-only engine stub used when no user engine is bound.

    ADR 0004 D2/D3: the philosophy layer is never allowed an ambient
    credential engine. Without an explicitly injected user-bound
    ``GcpSyncTranslator`` (request path), the default engine serves the
    statistics/config surface only and fails closed on any translation
    attempt.
    """

    PROVIDER_NAME: str = "gcp"

    async def translate_text(
        self,
        text: str,  # noqa: ARG002  (fail-closed unbound engine protocol)
        source_lang: str,  # noqa: ARG002  (fail-closed unbound engine protocol)
        target_lang: str,  # noqa: ARG002  (fail-closed unbound engine protocol)
        provider: str | None = None,  # noqa: ARG002  (fail-closed engine protocol)
    ) -> str:
        """Fail closed — no ambient credentials exist (ADR 0004 D3)."""
        raise GcpSyncCredentialsRequiredError("<unbound>")

    async def translate_batch(
        self,
        texts: list[str],  # noqa: ARG002  (fail-closed unbound engine protocol)
        source_lang: str,  # noqa: ARG002  (fail-closed unbound engine protocol)
        target_lang: str,  # noqa: ARG002  (fail-closed unbound engine protocol)
        provider: str | None = None,  # noqa: ARG002  (fail-closed engine protocol)
    ) -> list[str]:
        """Fail closed — no ambient credentials exist (ADR 0004 D3)."""
        raise GcpSyncCredentialsRequiredError("<unbound>")

    async def translate_document(
        self,
        document: Any,  # noqa: ARG002  (fail-closed unbound engine protocol)
        mime_type: Any = None,  # noqa: ARG002  (fail-closed unbound engine protocol)
        source_lang: Any = None,  # noqa: ARG002  (fail-closed unbound engine protocol)
        target_lang: Any = None,  # noqa: ARG002  (fail-closed unbound engine protocol)
        provider: Any = None,  # noqa: ARG002  (fail-closed unbound engine protocol)
        _progress_callback: Callable[[int], None] | None = None,
    ) -> Any:
        """Fail closed — no ambient credentials exist (ADR 0004 D3)."""
        raise GcpSyncCredentialsRequiredError("<unbound>")

    def get_available_providers(self) -> list[str]:
        """Surface the GCP provider registry (config parity)."""
        return [self.PROVIDER_NAME]

    def get_statistics(self) -> dict[str, Any]:
        """Return an empty statistics snapshot (nothing translated)."""
        return {}


@functools.cache
def _get_shared_executor(max_workers: int = 1) -> concurrent.futures.ThreadPoolExecutor:
    """Get a shared ThreadPoolExecutor with configurable max workers.

    Note: Different max_workers values create separate cached executors.
    Use consistent max_workers for true singleton behavior.

    Args:
        max_workers: Maximum number of worker threads (default: 1)

    Returns:
        ThreadPoolExecutor: Shared executor instance
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    atexit.register(_shutdown_executor, executor)
    return executor


def _shutdown_executor(executor: concurrent.futures.ThreadPoolExecutor) -> None:
    """Shutdown the shared executor."""
    executor.shutdown(wait=True)


def _run_coro_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine synchronously with or without a running event loop.

    Note: When running the coroutine on a different thread, this creates a
    fresh event loop and will not propagate contextvars/task-local state.
    Callers must ensure that this behavior is acceptable for their use case.

    Args:
        coro: The coroutine to run synchronously

    Returns:
        The result of the coroutine
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, can use asyncio.run directly
        return asyncio.run(coro)

    # There's a running loop, run the coroutine in a separate thread
    # using the shared executor to avoid creating a new one each time
    shared_executor = _get_shared_executor()
    fut = shared_executor.submit(asyncio.run, coro)
    return fut.result()


@dataclass
class PhilosophyTranslationProgress:
    """Progress tracking for philosophy-enhanced translation."""

    total_chunks: int = 0
    processed_chunks: int = 0
    total_neologisms: int = 0
    processed_neologisms: int = 0
    choices_applied: int = 0
    translation_progress: int = 0

    # Additional fields expected by tests
    text_processing_progress: int = 0
    neologism_detection_progress: int = 0
    user_choice_application_progress: int = 0

    @property
    def overall_progress(self) -> float:
        """Calculate overall progress percentage."""
        # If explicit progress fields are used, compute a simple weighted average regardless of total_chunks
        if (
            self.text_processing_progress
            or self.neologism_detection_progress
            or self.user_choice_application_progress
            or self.translation_progress
        ):
            components = [
                float(self.text_processing_progress),
                float(self.neologism_detection_progress),
                float(self.user_choice_application_progress),
                float(self.translation_progress),
            ]
            return sum(components) / len(components)

        if self.total_chunks == 0:
            return 0.0

        # Legacy computation path
        detection_weight = 0.3
        choice_weight = 0.2
        translation_weight = 0.5

        detection_progress = self.processed_chunks / max(1, self.total_chunks)
        choice_progress = (
            (self.processed_neologisms / max(1, self.total_neologisms))
            if self.total_neologisms > 0
            else 1.0
        )
        translation_progress = self.translation_progress / 100.0

        return (
            detection_progress * detection_weight
            + choice_progress * choice_weight
            + translation_progress * translation_weight
        ) * 100.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_chunks": self.total_chunks,
            "processed_chunks": self.processed_chunks,
            "total_neologisms": self.total_neologisms,
            "processed_neologisms": self.processed_neologisms,
            "choices_applied": self.choices_applied,
            "translation_progress": self.translation_progress,
            "overall_progress": self.overall_progress,
        }


@dataclass
class PreservationData:
    """Simple data structure for preservation markers and applied choices."""

    preservation_markers: dict[str, str]  # Maps placeholders to original terms
    applied_choices: list[UserChoice]


@dataclass
class NeologismPreservationResult:
    """Result of neologism preservation during translation."""

    original_text: str
    translated_text: str
    neologism_analysis: NeologismAnalysis | None
    neologisms_preserved: list[DetectedNeologism]
    user_choices_applied: list[UserChoice]
    preservation_markers: dict[str, str]  # Maps placeholders to original terms

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "original_text": self.original_text,
            "translated_text": self.translated_text,
            "neologism_analysis": (
                self.neologism_analysis.to_dict() if self.neologism_analysis else None
            ),
            "neologisms_preserved": [n.to_dict() for n in self.neologisms_preserved],
            "user_choices_applied": [c.to_dict() for c in self.user_choices_applied],
            "preservation_markers": self.preservation_markers,
        }


class PhilosophyEnhancedTranslationService:
    """Philosophy-Enhanced Translation Service with integrated neologism detection and user choice management.

    This service wraps a user-bound ``GcpSyncTranslator`` BYOK engine
    (ADR 0004: GCP-only, no ambient credentials) and adds:
    - Automatic neologism detection during translation
    - User choice application for handling detected neologisms
    - Preservation of philosophical terms according to user preferences
    - Enhanced progress tracking for philosophy-aware translation
    """

    def __init__(
        self,
        translation_service: Any | None = None,
        neologism_detector: NeologismDetector | None = None,
        user_choice_manager: UserChoiceManager | None = None,
        terminology_path: str | None = None,
        preserve_neologisms_by_default: bool = True,
        neologism_confidence_threshold: float = 0.5,
        chunk_size: int = 2000,
    ):
        """Initialize the philosophy-enhanced translation service.

        Args:
            translation_service: User-bound translation engine
                (``GcpSyncTranslator``). Defaults to
                :class:`UnboundTranslationStub`, which fails closed on
                translation attempts (ADR 0004 D2/D3) — real translation
                requires a request-path bound engine.
            neologism_detector: Neologism detection service
            user_choice_manager: User choice management service
            terminology_path: Path to terminology file
            preserve_neologisms_by_default: Whether to preserve unhandled neologisms
            neologism_confidence_threshold: Minimum confidence for neologism detection
            chunk_size: Size of text chunks for processing
        """
        # Track whether dependencies were explicitly injected (affects error propagation)
        self._injected_translation_service = translation_service is not None

        # Initialize base translation service (no ambient engine — fail closed)
        self.translation_service: Any = (
            translation_service
            if translation_service is not None
            else UnboundTranslationStub()
        )

        # Initialize neologism detection
        self.neologism_detector = neologism_detector or NeologismDetector(
            terminology_path=terminology_path,
            philosophical_threshold=neologism_confidence_threshold,
        )

        # Initialize user choice management
        self.user_choice_manager = user_choice_manager or UserChoiceManager()

        # Configuration
        self.preserve_neologisms_by_default = preserve_neologisms_by_default
        self.neologism_confidence_threshold = neologism_confidence_threshold
        self.chunk_size = chunk_size

        # Marker configuration expected by tests
        self.preserve_marker_prefix = "NEOLOGISM_PRESERVE_"
        self.preserve_marker_suffix = "_PRESERVE_END"

        # Statistics tracking
        self.stats = {
            "total_translations": 0,
            "neologisms_detected": 0,
            "choices_applied": 0,
            "neologisms_preserved": 0,
            "neologisms_translated": 0,
            "processing_time": 0.0,
        }

        logger.info("PhilosophyEnhancedTranslationService initialized")

    def _load_terminology(self, terminology_path: str) -> dict[str, str]:
        """Load terminology mapping from file."""
        try:
            with open(terminology_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load terminology from {terminology_path}: {e}")
            return {}

    async def translate_text_with_neologism_handling_async(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        session_id: str | None = None,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ) -> NeologismPreservationResult:
        """Async version: Translate text with integrated neologism detection and user choice handling.

        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            provider: Translation provider to use
            session_id: User session ID for choice context
            progress_callback: Optional progress callback

        Returns:
            NeologismPreservationResult with translation results and neologism analysis
        """
        start_time = time.time()

        # Initialize progress tracking
        progress = PhilosophyTranslationProgress()

        # Short-circuit empty text to preserve exact value
        if text == "":
            return NeologismPreservationResult(
                original_text=text,
                translated_text=text,
                neologism_analysis=None,
                neologisms_preserved=[],
                user_choices_applied=[],
                preservation_markers={},
            )

        try:
            # Step 1: Detect neologisms in the text
            logger.info(f"Detecting neologisms in text (length: {len(text)})")
            try:
                neologism_analysis = await self._detect_neologisms_async(
                    text, progress, progress_callback
                )
            except Exception as det_err:
                logger.error(f"Neologism detection failed: {det_err}")
                neologism_analysis = NeologismAnalysis(
                    text_id="fallback",
                    analysis_timestamp=str(time.time()),
                    total_tokens=len(text.split()),
                    analyzed_chunks=1,
                    detected_neologisms=[],
                    total_detections=0,
                )

            # Step 2: Apply user choices to detected neologisms
            logger.info(
                f"Applying user choices to {len(neologism_analysis.detected_neologisms)} neologisms"
            )
            pres = await self._apply_user_choices_async(
                text, neologism_analysis, session_id, progress, progress_callback
            )

            # Step 3: Translate the modified text
            logger.info(
                f"Translating modified text with {len(pres.preservation_markers)} preserved terms"
            )
            # Use the already modified text from _apply_user_choices_async
            translated_text = await self._translate_with_preservation_async(
                pres.modified_text,
                source_lang,
                target_lang,
                provider,
                progress,
                progress_callback,
            )
            # Let downstream handle identical translations naturally
            # If this is truly needed, document the specific downstream requirement
            # Step 4: Restore preserved neologisms
            logger.info("Restoring preserved neologisms in translated text")
            preservation_data = PreservationData(
                preservation_markers=pres.preservation_markers,
                applied_choices=pres.applied_choices,
            )
            final_translation = await self._restore_preserved_neologisms_async(
                translated_text,
                preservation_data,
            )

            # Update statistics
            self.stats["total_translations"] += 1
            self.stats["neologisms_detected"] += len(
                neologism_analysis.detected_neologisms
            )
            self.stats["choices_applied"] += len(pres.applied_choices)
            self.stats["processing_time"] += time.time() - start_time

            # Final progress update
            progress.translation_progress = 100
            if progress_callback:
                progress_callback(progress)

            return NeologismPreservationResult(
                original_text=text,
                translated_text=final_translation,
                neologism_analysis=neologism_analysis,
                neologisms_preserved=pres.preserved_neologisms,
                user_choices_applied=pres.applied_choices,
                preservation_markers=pres.preservation_markers,
            )

        except GcpSyncCredentialsRequiredError:
            # Fail closed (ADR 0004 D3): an unbound/invalid credential
            # engine must never degrade to the source-text fallback — the
            # caller surfaces the typed error (HTTP 503 / job failure).
            raise
        except Exception as e:
            logger.error(f"Error in philosophy-enhanced translation: {e}")
            # If a translation_service was injected explicitly, propagate the error
            if self._injected_translation_service:
                raise
            # Otherwise, fallback to regular translation (handle sync/async translator)
            try:
                # Tests may inject a MagicMock translator whose translate_text
                # returns a non-awaitable; keep the sync fallback reachable.
                maybe_coro: Any = self.translation_service.translate_text(
                    text, source_lang, target_lang, provider
                )
                if asyncio.iscoroutine(maybe_coro):
                    fallback_translation = await maybe_coro
                else:
                    fallback_translation = maybe_coro
            except Exception:
                fallback_translation = text

            return NeologismPreservationResult(
                original_text=text,
                translated_text=fallback_translation,
                neologism_analysis=None,
                neologisms_preserved=[],
                user_choices_applied=[],
                preservation_markers={},
            )

    def translate_text_with_neologism_handling(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        session_id: str | None = None,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ) -> NeologismPreservationResult:
        """Synchronous wrapper: Translate text with integrated neologism detection and user choice handling.

        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            provider: Translation provider to use
            session_id: User session ID for choice context
            progress_callback: Optional progress callback

        Returns:
            NeologismPreservationResult with translation results and neologism analysis
        """
        return _run_coro_sync(
            self.translate_text_with_neologism_handling_async(
                text,
                source_lang,
                target_lang,
                provider,
                session_id,
                progress_callback,
            )
        )

    def translate_batch_with_neologism_handling(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        session_id: str | None = None,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ) -> list[NeologismPreservationResult]:
        """Synchronous batch translation."""
        return _run_coro_sync(
            self._translate_batch_with_neologism_handling_async(
                texts,
                source_lang,
                target_lang,
                provider,
                session_id,
                progress_callback,
            )
        )

    async def translate_batch_with_neologism_handling_async(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        session_id: str | None = None,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ) -> list[NeologismPreservationResult]:
        """Asynchronous batch translation."""
        return await self._translate_batch_with_neologism_handling_async(
            texts, source_lang, target_lang, provider, session_id, progress_callback
        )

    async def _translate_batch_with_neologism_handling_async(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        session_id: str | None = None,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ) -> list[NeologismPreservationResult]:
        """Translate a batch of texts with neologism handling.

        Args:
            texts: List of texts to translate
            source_lang: Source language code
            target_lang: Target language code
            provider: Translation provider to use
            session_id: User session ID for choice context
            progress_callback: Optional progress callback

        Returns:
            List of translation results
        """
        results: list[NeologismPreservationResult] = []

        # Initialize progress tracking
        progress = PhilosophyTranslationProgress()
        progress.total_chunks = len(texts)

        # Step 1: Detect and preserve per-text
        analyses: list[NeologismAnalysis | None] = []
        modified_texts: list[str] = []
        markers_list: list[dict[str, str]] = []
        preserved_list: list[list[DetectedNeologism]] = []

        for i, text in enumerate(texts):
            try:
                progress.processed_chunks = i
                if progress_callback:
                    progress_callback(progress)

                analysis = await self._detect_neologisms_async(
                    text, progress, progress_callback
                )
                pres = await self._apply_user_choices_async(
                    text, analysis, session_id, progress, progress_callback
                )
                # Use the already modified text from _apply_user_choices_async
                analyses.append(analysis)
                markers_list.append(pres.preservation_markers)
                preserved_list.append(pres.preserved_neologisms)
                modified_texts.append(pres.modified_text)
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Error in batch pre-processing for item {i}: {e}")
                analyses.append(None)
                markers_list.append({})
                preserved_list.append([])
                modified_texts.append(text)

        # Step 2: Perform batch translation (supports sync/async providers)
        try:
            # Tests may inject a MagicMock translator; keep the sync fallback
            # reachable via Any.
            maybe_coro: Any = self.translation_service.translate_batch(
                modified_texts, source_lang, target_lang, provider
            )
            if asyncio.iscoroutine(maybe_coro):
                translated_texts = await maybe_coro
            else:
                translated_texts = maybe_coro
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Batch translation failed: {e}")
            translated_texts = modified_texts

        # Step 3: Restore markers and build results
        for i, translated in enumerate(translated_texts):
            preservation_data = PreservationData(
                preservation_markers=markers_list[i], applied_choices=[]
            )
            restored = await self._restore_preserved_neologisms_async(
                translated,
                preservation_data,
            )
            results.append(
                NeologismPreservationResult(
                    original_text=texts[i],
                    translated_text=restored,
                    neologism_analysis=analyses[i],
                    neologisms_preserved=preserved_list[i],
                    user_choices_applied=[],
                    preservation_markers=markers_list[i],
                )
            )

        # Final progress update
        progress.processed_chunks = len(texts)
        if progress_callback:
            progress_callback(progress)

        return results

    async def _detect_neologisms_async(
        self,
        text: str,
        progress: PhilosophyTranslationProgress,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ) -> NeologismAnalysis:
        """Detect neologisms in text asynchronously."""
        # Run neologism detection in a thread to avoid blocking
        analysis = await asyncio.to_thread(
            self.neologism_detector.analyze_text, text, chunk_size=self.chunk_size
        )

        # Filter by confidence threshold
        high_confidence_neologisms = [
            n
            for n in analysis.detected_neologisms
            if n.confidence >= self.neologism_confidence_threshold
        ]

        # Update analysis with filtered neologisms
        analysis.detected_neologisms = high_confidence_neologisms
        analysis.total_detections = len(high_confidence_neologisms)

        # Update progress
        progress.total_neologisms = len(high_confidence_neologisms)
        if progress_callback:
            progress_callback(progress)

        return analysis

    async def _apply_user_choices_async(
        self,
        text: str,
        analysis: NeologismAnalysis,
        session_id: str | None,
        progress: PhilosophyTranslationProgress,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ):
        """Apply user choices to detected neologisms."""
        preservation_markers: dict[str, str] = {}
        applied_choices: list[UserChoice] = []
        preserved_neologisms: list[DetectedNeologism] = []
        modified_text = text

        # Process each detected neologism
        for i, neologism in enumerate(analysis.detected_neologisms):
            # Update progress
            progress.processed_neologisms = i + 1
            if progress_callback:
                progress_callback(progress)

            # Get user choice for this neologism
            user_choice = await asyncio.to_thread(
                self.user_choice_manager.get_choice_for_neologism, neologism, session_id
            )

            if user_choice:
                # Apply existing choice
                modified_text, marker = self._apply_choice_to_text(
                    modified_text, neologism, user_choice
                )
                if marker:
                    preservation_markers[marker] = neologism.term
                applied_choices.append(user_choice)
                preserved_neologisms.append(neologism)
                progress.choices_applied += 1

            elif self.preserve_neologisms_by_default:
                # Default preservation behavior
                marker = self._create_preservation_marker(neologism.term)
                modified_text = self._replace_term_with_marker(
                    modified_text, neologism, marker
                )
                preservation_markers[marker] = neologism.term
                preserved_neologisms.append(neologism)
                self.stats["neologisms_preserved"] += 1

        return SimpleNamespace(
            modified_text=modified_text,
            preserved_neologisms=preserved_neologisms,
            applied_choices=applied_choices,
            preservation_markers=preservation_markers,
        )

    def _apply_choice_to_text(
        self, text: str, neologism: DetectedNeologism, choice: UserChoice
    ) -> tuple[str, str | None]:
        """Apply a user choice to text."""
        if choice.choice_type == ChoiceType.PRESERVE:
            # Preserve the term as-is with a marker
            marker = self._create_preservation_marker(neologism.term)
            modified_text = self._replace_term_with_marker(text, neologism, marker)
            return modified_text, marker

        elif choice.choice_type == ChoiceType.TRANSLATE:
            # Let the term be translated normally
            return text, None

        elif choice.choice_type == ChoiceType.CUSTOM_TRANSLATION:
            # Replace with custom translation
            if choice.translation_result:
                marker = self._create_preservation_marker(choice.translation_result)
                modified_text = self._replace_term_with_marker(text, neologism, marker)
                return modified_text, marker
            else:
                return text, None

        else:
            # Default behavior (ChoiceType has no CONTEXT_DEPENDENT member;
            # evaluating that reference previously crashed on SKIP choices)
            return text, None

    def _create_preservation_marker(self, term: str) -> str:
        """Create a unique preservation marker for a term."""
        import hashlib

        hash_obj = hashlib.sha256(term.encode())
        # Use explicit prefix/suffix format expected by tests
        return f"{self.preserve_marker_prefix}{hash_obj.hexdigest()[:1]}{self.preserve_marker_suffix}"

    def _replace_term_with_marker(
        self, text: str, neologism: DetectedNeologism, marker: str
    ) -> str:
        """Replace a neologism term with a preservation marker."""
        # Use word boundaries to avoid partial matches
        pattern = rf"\b{re.escape(neologism.term)}\b"
        return re.sub(pattern, marker, text, flags=re.IGNORECASE)

    def _preserve_neologisms_in_text(
        self, text: str, neologisms: list[DetectedNeologism]
    ) -> tuple[str, dict[str, str]]:
        """Preserve neologisms in text by replacing them with markers.

        Args:
            text: Original text
            neologisms: List of neologisms to preserve

        Returns:
            Tuple of (preserved_text, markers_dict)
        """
        preserved_text = text
        markers = {}

        # Sort neologisms by position (reverse order to avoid position shifts)
        sorted_neologisms = sorted(neologisms, key=lambda n: n.start_pos, reverse=True)

        for neologism in sorted_neologisms:
            marker = self._create_preservation_marker(neologism.term)
            preserved_text = self._replace_term_with_marker(
                preserved_text, neologism, marker
            )
            markers[marker] = neologism.term

        return preserved_text, markers

    def _restore_neologisms_in_text(self, text: str, markers: dict[str, str]) -> str:
        """Restore neologisms in text by replacing markers with original terms.

        Args:
            text: Text with preservation markers
            markers: Dictionary mapping markers to original terms

        Returns:
            Text with markers replaced by original terms
        """
        restored_text = text

        for marker, original_term in markers.items():
            restored_text = restored_text.replace(marker, original_term)

        return restored_text

    async def _translate_with_preservation_async(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        provider: str,
        progress: PhilosophyTranslationProgress,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ) -> str:
        """Translate text with preserved markers."""
        # Use the existing translation service (supports sync/async).
        # Tests may inject a MagicMock translator; keep the sync fallback
        # reachable via Any.
        maybe_coro: Any = self.translation_service.translate_text(
            text, source_lang, target_lang, provider
        )
        if asyncio.iscoroutine(maybe_coro):
            translated_text = await maybe_coro
        else:
            translated_text = maybe_coro

        # Update progress
        progress.translation_progress = 100
        if progress_callback:
            progress_callback(progress)

        return translated_text

    async def _restore_preserved_neologisms_async(
        self,
        translated_text: str,
        preservation_data: PreservationData,
    ) -> str:
        """Restore preserved neologisms in translated text."""
        restored_text = translated_text

        # Replace markers with original terms or custom translations
        for marker, original_term in preservation_data.preservation_markers.items():
            # Find the corresponding choice to see if we should use custom translation
            custom_translation = None
            for choice in preservation_data.applied_choices:
                if choice.neologism_term == original_term and choice.translation_result:
                    custom_translation = choice.translation_result
                    break

            # Use custom translation if available, otherwise use original term
            replacement = custom_translation if custom_translation else original_term
            restored_text = restored_text.replace(marker, replacement)

        return restored_text

    async def translate_document_with_neologism_handling(
        self,
        content: dict[str, Any],
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        session_id: str | None = None,
        progress_callback: (
            Callable[[PhilosophyTranslationProgress], None] | None
        ) = None,
    ) -> dict[str, Any]:
        """Translate document content with neologism handling.

        Args:
            content: Document content from document processor
            source_lang: Source language code
            target_lang: Target language code
            provider: Translation provider to use
            session_id: User session ID for choice context
            progress_callback: Optional progress callback

        Returns:
            Translated document content with neologism metadata
        """
        start_time = time.time()

        # Initialize progress tracking
        progress = PhilosophyTranslationProgress()

        try:
            # Extract text blocks for translation
            text_blocks = self._extract_text_blocks(content)
            progress.total_chunks = len(text_blocks)

            # Process each text block
            translated_blocks = []
            neologism_analyses = []

            for i, block in enumerate(text_blocks):
                # Update progress
                progress.processed_chunks = i
                if progress_callback:
                    progress_callback(progress)

                # Translate block with neologism handling
                if block.get("text", "").strip():
                    # Use async helpers to avoid blocking event loop
                    analysis = await self._detect_neologisms_async(
                        block["text"], progress, progress_callback
                    )
                    pres = await self._apply_user_choices_async(
                        block["text"], analysis, session_id, progress, progress_callback
                    )
                    # Use the already modified text from _apply_user_choices_async
                    translated_text = await self._translate_with_preservation_async(
                        pres.modified_text,
                        source_lang,
                        target_lang,
                        provider,
                        progress,
                        progress_callback,
                    )
                    preservation_data = PreservationData(
                        preservation_markers=pres.preservation_markers,
                        applied_choices=pres.applied_choices,
                    )
                    restored_text = await self._restore_preserved_neologisms_async(
                        translated_text,
                        preservation_data,
                    )

                    # Update block with translation
                    translated_block = block.copy()
                    translated_block["text"] = restored_text
                    if analysis:
                        translated_block["neologism_analysis"] = analysis.to_dict()
                    translated_blocks.append(translated_block)

                    # Collect neologism analysis
                    if analysis:
                        neologism_analyses.append(analysis.to_dict())
                else:
                    # Keep empty blocks as-is
                    translated_blocks.append(block)

            # Reconstruct document content
            translated_content = self._reconstruct_content(content, translated_blocks)

            # Final progress update
            progress.processed_chunks = len(text_blocks)
            progress.translation_progress = 100
            if progress_callback:
                progress_callback(progress)

            return {
                "translated_content": translated_content,
                "original_content": content,
                # Provide both singular and plural keys for compatibility
                "neologism_analysis": (
                    neologism_analyses[0] if neologism_analyses else None
                ),
                "neologism_analyses": neologism_analyses,
                "session_id": session_id,
                "processing_metadata": {
                    "provider_used": provider,
                    "source_language": source_lang,
                    "target_language": target_lang,
                    "processing_time": time.time() - start_time,
                    "total_blocks": len(text_blocks),
                    "total_neologism_analyses": len(neologism_analyses),
                },
            }

        except Exception as e:
            logger.error(f"Error in document translation with neologism handling: {e}")

            # Fallback to regular document translation
            # Fallback (support sync/async)
            def _doc_progress(percent: int) -> None:
                """Adapt document progress (int percent) to philosophy progress."""
                progress.translation_progress = percent
                if progress_callback is not None:
                    progress_callback(progress)

            # Tests may inject a MagicMock translator whose translate_document
            # returns a non-awaitable; keep the sync fallback reachable.
            maybe_coro: Any = self.translation_service.translate_document(
                content, source_lang, target_lang, provider, _doc_progress
            )
            if asyncio.iscoroutine(maybe_coro):
                fallback_result = await maybe_coro
            else:
                fallback_result = maybe_coro

            return {
                "translated_content": fallback_result,
                "original_content": content,
                "error": str(e),
                "fallback_used": True,
                "translation_metadata": {
                    "provider_used": provider,
                    "source_language": source_lang,
                    "target_language": target_lang,
                    "processing_time": time.time() - start_time,
                },
            }

    def _extract_text_blocks(self, content: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract text blocks from document content."""
        text_blocks = []

        if "pages" in content:
            for page_num, page in enumerate(content["pages"]):
                if "text_blocks" in page:
                    for block_num, block in enumerate(page["text_blocks"]):
                        text_blocks.append(
                            {
                                "page": page_num,
                                "block": block_num,
                                "text": block.get("text", ""),
                                "formatting": block.get("formatting", {}),
                                "position": block.get("position", {}),
                            }
                        )

        return text_blocks

    def _reconstruct_content(
        self, original_content: dict[str, Any], translated_blocks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Reconstruct document content with translations."""
        content = original_content.copy()

        # Create lookup for translated blocks
        block_lookup = {}
        for block in translated_blocks:
            key = (block["page"], block["block"])
            block_lookup[key] = block

        # Update content with translations
        if "pages" in content:
            for page_num, page in enumerate(content["pages"]):
                if "text_blocks" in page:
                    for block_num, block in enumerate(page["text_blocks"]):
                        key = (page_num, block_num)
                        if key in block_lookup:
                            translated_block = block_lookup[key]
                            block["text"] = translated_block["text"]
                            # Add neologism analysis if available
                            if "neologism_analysis" in translated_block:
                                block["neologism_analysis"] = translated_block[
                                    "neologism_analysis"
                                ]

        return content

    def _select_best_provider(self) -> str:
        """Select the best available provider (GCP sync tier, ADR 0004)."""
        try:
            # Use get_available_providers to get a list of valid providers
            available_providers = self.get_available_providers()
            # Prefer the single GCP provider, then the first available
            if "gcp" in available_providers:
                return "gcp"
            if available_providers:
                first: Any = available_providers[0]
                return str(first) if first is not None else "gcp"
            return "gcp"
        except Exception:
            return "gcp"

    def get_available_providers(self) -> list[str]:
        """Get list of available translation providers."""
        try:
            # Tests may inject MagicMocks whose attribute access is not a
            # list; keep the coercion branch reachable via Any.
            prov: Any = self.translation_service.get_available_providers()
            if not isinstance(prov, list):
                return ["gcp"]
            return prov
        except Exception:
            return ["gcp"]

    def get_statistics(self) -> dict[str, Any]:
        """Get service statistics."""
        try:
            ts_stats = self.translation_service.get_statistics()
        except Exception:
            ts_stats = {}
        detector_stats = self.neologism_detector.get_statistics()
        choice_stats = self.user_choice_manager.get_statistics()

        return {
            "philosophy_enhanced_stats": self.stats,
            "translation_service_stats": ts_stats,
            "neologism_detector_stats": detector_stats,
            "user_choice_manager_stats": choice_stats,
            "configuration": {
                "preserve_neologisms_by_default": self.preserve_neologisms_by_default,
                "neologism_confidence_threshold": self.neologism_confidence_threshold,
                "chunk_size": self.chunk_size,
            },
        }

    def update_configuration(self, **kwargs) -> None:
        """Update service configuration."""
        if "preserve_neologisms_by_default" in kwargs:
            self.preserve_neologisms_by_default = kwargs[
                "preserve_neologisms_by_default"
            ]

        if "neologism_confidence_threshold" in kwargs:
            self.neologism_confidence_threshold = kwargs[
                "neologism_confidence_threshold"
            ]

        if "chunk_size" in kwargs:
            self.chunk_size = kwargs["chunk_size"]

        logger.info("Philosophy-enhanced translation service configuration updated")

    # Convenience functions for easy integration


def create_philosophy_enhanced_translation_service(
    terminology_path: str | None = None,
    db_path: str = "database/user_choices.db",
    **kwargs,
) -> PhilosophyEnhancedTranslationService:
    """Create a philosophy-enhanced translation service with default components."""
    return PhilosophyEnhancedTranslationService(
        terminology_path=terminology_path,
        user_choice_manager=UserChoiceManager(db_path=db_path),
        **kwargs,
    )


async def translate_with_philosophy_awareness(
    text: str,
    source_lang: str,
    target_lang: str,
    provider: str = "auto",
    session_id: str | None = None,
    terminology_path: str | None = None,
    service: PhilosophyEnhancedTranslationService | None = None,
) -> dict[str, Any]:
    """Quick function to translate text with philosophy awareness.

    Args:
        text: Text to translate
        source_lang: Source language code
        target_lang: Target language code
        provider: Translation provider to use
        session_id: Optional session identifier
        terminology_path: Optional path to terminology file
            (used only when service is None)
        service: Optional pre-created service instance for reuse

    Returns:
        Translation result as dictionary
    """
    # Use provided service or create new one
    if service is None:
        service = create_philosophy_enhanced_translation_service(terminology_path)

    result = await service.translate_text_with_neologism_handling_async(
        text, source_lang, target_lang, provider, session_id
    )
    # Convert to dict for backward compatibility. User-bound GCP engines
    # (ADR 0004) may return plain result dicts — pass those through intact.
    if isinstance(result, dict):
        return result
    return result.to_dict()
