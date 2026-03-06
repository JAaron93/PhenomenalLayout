"""Enhanced translation service for Dolphin OCR Translate.

Integrating parallel-processing capabilities into the existing translation workflow.

This module provides a drop-in replacement for the standard translation service
with significant performance improvements for large documents.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from services.parallel_translation_service import (
    BatchProgress,
    ParallelTranslationConfig,
    ParallelTranslationService,
)

from .translation_service import TranslationService

logger = logging.getLogger(__name__)


class EnhancedTranslationService(TranslationService):
    """Enhanced translation service with parallel processing capabilities."""

    def __init__(self, terminology_path: str | None = None):
        """Initialize enhanced translation service with parallel processing.

        Args:
            terminology_path: Optional path to a JSON file containing
                terminology mappings for translation preprocessing. If
                provided, terms in the file will be preserved during
                translation using HTML ``<span translate="no">`` tags.

        Notes:
            - Initializes parent TranslationService with terminology mapping
            - Sets up parallel_config from ParallelTranslationConfig.from_config()
            - Initializes performance_stats dictionary with tracking metrics
            - Sets _parallel_service to None for lazy initialization

        Raises:
            ValueError: If LINGO_API_KEY environment variable is not set or if
                    translation provider initialization fails.
            FileNotFoundError: If terminology_path is provided but file does not
                    exist or is not readable.
            ``json.JSONDecodeError``: If the terminology file contains invalid JSON.
        """
        super().__init__(terminology_path)

        # Parallel processing configuration
        self.parallel_config = ParallelTranslationConfig.from_config()
        self._parallel_service: ParallelTranslationService | None = None

        # Performance tracking
        self.performance_stats = {
            "total_requests": 0,
            "parallel_requests": 0,
            "sequential_requests": 0,
            "total_processing_time": 0.0,
            "average_request_time": 0.0,
        }

    def _should_use_parallel_processing(self, text_count: int) -> bool:
        """Determine if parallel processing should be used based on text count."""
        # Use parallel processing for batches larger than threshold
        # Minimum threshold of 5 ensures overhead of parallel processing is worthwhile
        parallel_threshold = max(5, self.parallel_config.batch_size // 10)
        return text_count >= parallel_threshold

    async def _get_parallel_service(self) -> ParallelTranslationService:
        """Get or create parallel translation service."""
        if self._parallel_service is None:
            api_key = self._get_lingo_api_key()
            self._parallel_service = ParallelTranslationService(
                api_key, self.parallel_config
            )

        return self._parallel_service

    def _get_lingo_api_key(self) -> str:
        """Extract Lingo API key from existing providers."""
        lingo_provider = self.providers.get("lingo")
        if not lingo_provider:
            raise ValueError("Lingo provider not initialized")

        return lingo_provider.api_key

    async def _translate_batch_parallel(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        """Translate texts using parallel processing."""
        parallel_service = await self._get_parallel_service()

        # Convert progress callback format
        def parallel_progress_callback(progress: BatchProgress) -> None:
            if progress_callback:
                progress_callback(progress.completed_tasks, progress.total_tasks)

        async with parallel_service:
            return await parallel_service.translate_batch_texts(
                texts, source_lang, target_lang, parallel_progress_callback
            )

    async def translate_document_enhanced(
        self,
        content: dict[str, Any],
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        progress_callback: Callable[[int], None] | None = None,
    ) -> dict[str, Any]:
        """Enhanced document translation with parallel processing."""
        start_time = time.time()

        # Extract text blocks to determine processing method
        text_blocks = self._extract_text_blocks_for_analysis(content)
        use_parallel = self._should_use_parallel_processing(len(text_blocks))

        if use_parallel:
            logger.info(
                "Using parallel processing for document with %d text blocks",
                len(text_blocks),
            )
            result = await self._translate_document_parallel(
                content, source_lang, target_lang, progress_callback
            )
            self.performance_stats["parallel_requests"] += 1
        else:
            logger.info(
                "Using sequential processing for document with %d text blocks",
                len(text_blocks),
            )
            result = await super().translate_document(
                content, source_lang, target_lang, provider, progress_callback
            )
            self.performance_stats["sequential_requests"] += 1

        # Update performance stats
        processing_time = time.time() - start_time
        self.performance_stats["total_requests"] += 1
        self.performance_stats["total_processing_time"] += processing_time
        self.performance_stats["average_request_time"] = (
            self.performance_stats["total_processing_time"]
            / self.performance_stats["total_requests"]
        )

        return result

    async def _translate_document_parallel(
        self,
        content: dict[str, Any],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[int], None] | None = None,
    ) -> dict[str, Any]:
        """Translate document using parallel processing."""
        parallel_service = await self._get_parallel_service()

        # Convert progress callback format
        def parallel_progress_callback(progress: BatchProgress) -> None:
            if progress_callback:
                # Convert to percentage for compatibility
                percentage = int(progress.progress_percentage)
                progress_callback(percentage)

        async with parallel_service:
            return await parallel_service.translate_large_document(
                content, source_lang, target_lang, parallel_progress_callback
            )

    def _extract_text_blocks_for_analysis(self, content: dict[str, Any]) -> list[str]:
        """Extract text blocks for analysis (without IDs)."""
        text_blocks = []

        # Extract from pages
        for page_data in content.get("pages", {}).values():
            if isinstance(page_data, dict):
                for block_text in page_data.values():
                    if isinstance(block_text, str) and block_text.strip():
                        text_blocks.append(block_text)

        # Extract from layouts if available
        for layout in content.get("layouts", []):
            if isinstance(layout, dict) and layout.get("text", "").strip():
                text_blocks.append(layout["text"])
            elif hasattr(layout, "text") and layout.text and layout.text.strip():
                text_blocks.append(layout.text)

        return text_blocks

    def get_performance_stats(self) -> dict[str, Any]:
        """Get performance statistics."""
        stats = self.performance_stats.copy()

        # Add efficiency metrics
        total_requests = stats["total_requests"]
        if total_requests > 0:
            stats["parallel_usage_percentage"] = (
                stats["parallel_requests"] / total_requests * 100
            )
            stats["sequential_usage_percentage"] = (
                stats["sequential_requests"] / total_requests * 100
            )
        else:
            stats["parallel_usage_percentage"] = 0.0
            stats["sequential_usage_percentage"] = 0.0

        return stats

    def reset_performance_stats(self) -> None:
        """Reset performance statistics."""
        self.performance_stats = {
            "total_requests": 0,
            "parallel_requests": 0,
            "sequential_requests": 0,
            "total_processing_time": 0.0,
            "average_request_time": 0.0,
        }

    async def close(self) -> None:
        """Close the enhanced translation service and cleanup resources."""
        if self._parallel_service:
            # ParallelTranslationService is designed to be used as an async context manager
            # and doesn't maintain persistent state that requires explicit cleanup.
            # Simply clear the reference to allow garbage collection.
            self._parallel_service = None


# Convenience function for easy integration
async def create_enhanced_translation_service(
    terminology_path: str | None = None,
) -> EnhancedTranslationService:
    """Create and initialize an enhanced translation service."""
    service = EnhancedTranslationService(terminology_path)
    return service
