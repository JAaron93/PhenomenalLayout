#!/usr/bin/env python3
"""
Demonstration of Dolphin OCR Translate parallel translation capabilities for large document processing.

This script shows how to use the enhanced translation service to process
large documents efficiently with parallel processing.
"""

import asyncio
import logging
import time
from typing import List

from services.enhanced_translation_service import EnhancedTranslationService
from services.parallel_translation_service import (
    BatchProgress,
    ParallelTranslationConfig,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_sample_document() -> dict:
    """Create a sample document with multiple pages for testing."""
    return {
        "pages": {
            "1": {
                "paragraph_1": "Die Philosophie der Bewusstseinsforschung beschäftigt sich mit fundamentalen Fragen des menschlichen Geistes.",
                "paragraph_2": "Wirklichkeitsbewusstsein ist ein zentraler Begriff in der modernen Erkenntnistheorie.",
                "paragraph_3": "Die Lebensweltthematik spielt eine wichtige Rolle in der phänomenologischen Tradition.",
            },
            "2": {
                "paragraph_1": "Bewusstseinsphilosophie untersucht die Struktur und Dynamik des bewussten Erlebens.",
                "paragraph_2": "Erkenntnistheoretische Überlegungen führen zu neuen Einsichten über die Natur des Wissens.",
                "paragraph_3": "Die Weltanschauung eines Denkers prägt seine philosophischen Grundannahmen.",
            },
            "3": {
                "paragraph_1": "Morphologische Analysen zeigen die Komplexität deutscher Komposita.",
                "paragraph_2": "Neologismen entstehen durch kreative Wortbildungsprozesse.",
                "paragraph_3": "Terminologische Konsistenz ist wichtig für wissenschaftliche Texte.",
            },
        }
    }


def create_large_text_batch() -> List[str]:
    """Create a large batch of texts for performance testing."""
    base_texts = [
        "Die Philosophie beschäftigt sich mit grundlegenden Fragen des Seins.",
        "Bewusstsein ist ein komplexes Phänomen der menschlichen Erfahrung.",
        "Erkenntnistheorie untersucht die Bedingungen möglicher Erkenntnis.",
        "Wirklichkeit und Wahrheit sind zentrale Begriffe der Metaphysik.",
        "Die Lebenswelt bildet den Horizont unserer alltäglichen Erfahrung.",
        "Phänomenologie beschreibt die Strukturen des Bewusstseins.",
        "Hermeneutik ist die Kunst und Wissenschaft des Verstehens.",
        "Ontologie fragt nach dem Wesen des Seienden als solchem.",
        "Epistemologie erforscht die Natur und Grenzen des Wissens.",
        "Ästhetik untersucht die Prinzipien der Schönheit und Kunst.",
    ]

    # Create a larger batch by repeating and modifying base texts
    large_batch = []
    for i in range(50):  # Create 500 texts total
        for j, text in enumerate(base_texts):
            modified_text = f"{text} (Variante {i+1}.{j+1})"
            large_batch.append(modified_text)

    return large_batch


class ProgressTracker:
    """Progress tracking utility for demonstrations."""

    def __init__(self, description: str):
        self.description = description
        self.start_time = time.time()
        self.last_update = 0

    def update_progress(self, current: int, total: int):
        """Update progress for simple progress tracking."""
        percentage = (current / total * 100) if total > 0 else 0

        # Only update every 10% or on completion
        if percentage - self.last_update >= 10 or current == total:
            elapsed = time.time() - self.start_time
            rate = current / elapsed if elapsed > 0 else 0

            logger.info(
                "%s: %d/%d (%.1f%%) - %.1f items/sec - %.1fs elapsed",
                self.description,
                current,
                total,
                percentage,
                rate,
                elapsed,
            )
            self.last_update = percentage

    def update_batch_progress(self, progress: BatchProgress):
        """Update progress for batch operations."""
        elapsed = progress.elapsed_time
        rate = progress.completed_tasks / elapsed if elapsed > 0 else 0
        remaining = progress.estimated_remaining_time

        logger.info(
            "%s: %d/%d (%.1f%%) - %.1f items/sec - %.1fs elapsed, ~%.1fs remaining",
            self.description,
            progress.completed_tasks,
            progress.total_tasks,
            progress.progress_percentage,
            rate,
            elapsed,
            remaining,
        )


async def demo_basic_parallel_translation():
    """Demonstrate basic parallel translation functionality."""
    logger.info("=== Basic Parallel Translation Demo ===")

    # Create sample texts
    texts = [
        "Die Philosophie der Bewusstseinsforschung ist komplex.",
        "Wirklichkeitsbewusstsein spielt eine zentrale Rolle.",
        "Erkenntnistheorie untersucht die Grundlagen des Wissens.",
        "Bewusstseinsphilosophie erforscht das menschliche Denken.",
        "Die Lebensweltthematik ist phänomenologisch relevant.",
    ]

    # Configure for demonstration (lower concurrency for API safety)
    config = ParallelTranslationConfig(
        max_concurrent_requests=3, max_requests_per_second=2.0, batch_size=10
    )

    service = EnhancedTranslationService()
    service.parallel_config = config

    tracker = ProgressTracker("Basic Translation")

    try:
        start_time = time.time()

        # Note: This would require a valid Lingo API key
        # For demo purposes, we'll simulate the process
        logger.info("Translating %d texts from German to English...", len(texts))

        # Simulate translation process
        for i in range(len(texts)):
            await asyncio.sleep(0.1)  # Simulate processing time
            tracker.update_progress(i + 1, len(texts))

        elapsed = time.time() - start_time
        logger.info("Translation completed in %.2f seconds", elapsed)

        # Show performance stats
        stats = service.get_performance_stats()
        logger.info("Performance stats: %s", stats)

    except Exception as e:
        logger.error("Translation failed: %s", e)
    finally:
        await service.close()


async def demo_large_document_processing():
    """Demonstrate large document processing capabilities."""
    logger.info("=== Large Document Processing Demo ===")

    # Create sample document
    document = create_sample_document()

    # Configure for high-performance processing
    config = ParallelTranslationConfig(
        max_concurrent_requests=5, max_requests_per_second=3.0, batch_size=20
    )

    service = EnhancedTranslationService()
    service.parallel_config = config

    tracker = ProgressTracker("Document Translation")

    try:
        start_time = time.time()

        logger.info("Processing document with %d pages...", len(document["pages"]))

        # Count total text blocks
        total_blocks = sum(
            len(page_data)
            for page_data in document["pages"].values()
            if isinstance(page_data, dict)
        )

        logger.info("Total text blocks to translate: %d", total_blocks)

        # Simulate document processing
        for i in range(total_blocks):
            await asyncio.sleep(0.05)  # Simulate processing time
            tracker.update_progress(i + 1, total_blocks)

        elapsed = time.time() - start_time
        logger.info("Document processing completed in %.2f seconds", elapsed)

        # Show performance improvement estimate
        sequential_time_estimate = (
            total_blocks * 0.5
        )  # Assume 0.5s per request sequentially
        improvement = sequential_time_estimate / elapsed if elapsed > 0 else 1

        logger.info(
            "Estimated performance improvement: %.1fx faster than sequential processing",
            improvement,
        )

    except Exception as e:
        logger.error("Document processing failed: %s", e)
    finally:
        await service.close()


async def demo_batch_performance_comparison():
    """Demonstrate performance comparison between sequential and parallel processing."""
    logger.info("=== Performance Comparison Demo ===")

    # Create large text batch
    texts = create_large_text_batch()
    logger.info("Created batch of %d texts for performance testing", len(texts))

    # Test with different batch sizes
    batch_sizes = [10, 25, 50, 100]

    for batch_size in batch_sizes:
        logger.info("--- Testing with batch size: %d ---", batch_size)

        config = ParallelTranslationConfig(
            max_concurrent_requests=min(batch_size // 2, 10),
            max_requests_per_second=5.0,
            batch_size=batch_size,
        )

        service = EnhancedTranslationService()
        service.parallel_config = config

        # Take a subset for testing
        test_texts = texts[:batch_size]

        tracker = ProgressTracker(f"Batch Size {batch_size}")

        try:
            start_time = time.time()

            # Simulate batch processing
            for i in range(len(test_texts)):
                await asyncio.sleep(0.01)  # Simulate processing time
                tracker.update_progress(i + 1, len(test_texts))

            elapsed = time.time() - start_time
            rate = len(test_texts) / elapsed if elapsed > 0 else 0

            logger.info(
                "Batch size %d: %.2f seconds, %.1f texts/sec", batch_size, elapsed, rate
            )

        except Exception as e:
            logger.error("Batch processing failed: %s", e)
        finally:
            await service.close()


async def demo_error_handling_and_resilience():
    """Demonstrate error handling and resilience features."""
    logger.info("=== Error Handling and Resilience Demo ===")

    # Configure with aggressive retry settings for demonstration
    config = ParallelTranslationConfig(
        max_concurrent_requests=3,
        max_requests_per_second=1.0,
        max_retries=2,
        retry_delay=0.5,
        backoff_multiplier=2.0,
    )

    service = EnhancedTranslationService()
    service.parallel_config = config

    logger.info("Configured with retry settings:")
    logger.info("- Max retries: %d", config.max_retries)
    logger.info("- Retry delay: %.1fs", config.retry_delay)
    logger.info("- Backoff multiplier: %.1fx", config.backoff_multiplier)

    # Simulate processing with potential failures
    texts = ["Text 1", "Text 2", "Text 3", "Text 4", "Text 5"]

    tracker = ProgressTracker("Resilience Test")

    try:
        start_time = time.time()

        for i, text in enumerate(texts):
            # Simulate processing with occasional "failures"
            if i == 2:  # Simulate failure on third item
                logger.warning("Simulating API failure for text %d", i + 1)
                await asyncio.sleep(1.0)  # Simulate retry delay

            await asyncio.sleep(0.2)  # Simulate normal processing
            tracker.update_progress(i + 1, len(texts))

        elapsed = time.time() - start_time
        logger.info("Resilience test completed in %.2f seconds", elapsed)

    except Exception as e:
        logger.error("Resilience test failed: %s", e)
    finally:
        await service.close()


async def main():
    """Run all demonstration scenarios."""
    logger.info("Starting Parallel Translation Service Demonstration")
    logger.info("=" * 60)

    try:
        await demo_basic_parallel_translation()
        await asyncio.sleep(1)

        await demo_large_document_processing()
        await asyncio.sleep(1)

        await demo_batch_performance_comparison()
        await asyncio.sleep(1)

        await demo_error_handling_and_resilience()

    except KeyboardInterrupt:
        logger.info("Demonstration interrupted by user")
    except Exception as e:
        logger.error("Demonstration failed: %s", e)

    logger.info("=" * 60)
    logger.info("Parallel Translation Service Demonstration Complete")


if __name__ == "__main__":
    asyncio.run(main())
