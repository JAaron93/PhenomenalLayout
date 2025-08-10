"""
Performance optimization examples for philosophy-enhanced translation system.

This script demonstrates various optimization techniques for handling large
documents (2,000+ pages) efficiently while maintaining the philosophy-enhanced
capabilities.
"""

import asyncio
import gc
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import psutil

from services.philosophy_enhanced_document_processor import (
    create_philosophy_enhanced_document_processor,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for optimization analysis."""

    memory_usage_mb: float
    cpu_percent: float
    processing_time: float
    pages_per_second: float
    neologisms_per_second: float
    total_pages: int
    total_neologisms: int
    peak_memory_mb: float


class PerformanceOptimizer:
    """Performance optimization utilities for large document processing."""

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        # MB
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory = self.initial_memory

    def get_current_metrics(self) -> Dict[str, float]:
        """Get current system performance metrics."""
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        cpu_percent = self.process.cpu_percent()

        # Update peak memory
        self.peak_memory = max(self.peak_memory, memory_mb)

        return {
            "memory_mb": memory_mb,
            "cpu_percent": cpu_percent,
            "peak_memory_mb": self.peak_memory,
        }

    def log_performance_status(self, stage: str, additional_info: Optional[str] = None):
        """Log current performance status."""
        metrics = self.get_current_metrics()
        info_str = f" - {additional_info}" if additional_info else ""
        logger.info(
            f"[{stage}] Memory: {metrics['memory_mb']:.1f}MB, "
            f"CPU: {metrics['cpu_percent']:.1f}%{info_str}"
        )

    def force_garbage_collection(self):
        """Force garbage collection to free memory."""
        logger.info("Forcing garbage collection...")
        collected = gc.collect()
        logger.info(f"Garbage collection freed {collected} objects")
        self.log_performance_status("Post-GC")


class LargeDocumentProcessor:
    """Optimized processor for handling large documents efficiently."""

    def __init__(
        self,
        max_concurrent_pages: int = 10,
        chunk_size: int = 50,
        memory_limit_mb: int = 2048,
        enable_memory_management: bool = True,
    ):
        """
        Initialize large document processor with optimization settings.

        Args:
            max_concurrent_pages: Maximum pages to process concurrently
            chunk_size: Size of page chunks for batch processing
            memory_limit_mb: Memory limit in MB before triggering cleanup
            enable_memory_management: Whether to enable automatic memory
                                    management
        """
        self.max_concurrent_pages = max_concurrent_pages
        self.chunk_size = chunk_size
        self.memory_limit_mb = memory_limit_mb
        self.enable_memory_management = enable_memory_management

        # Create optimized processor
        self.processor = create_philosophy_enhanced_document_processor(
            max_concurrent_pages=max_concurrent_pages, enable_batch_processing=True
        )

        # Performance tracking
        self.performance_optimizer = PerformanceOptimizer()

        logger.info("Large document processor initialized with:")
        logger.info(f"  Max concurrent pages: {max_concurrent_pages}")
        logger.info(f"  Chunk size: {chunk_size}")
        logger.info(f"  Memory limit: {memory_limit_mb}MB")

    async def process_large_document_streaming(
        self,
        file_path: str,
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
        user_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Process large document with streaming approach for memory efficiency.

        Yields progress updates and partial results to avoid memory buildup.
        """
        start_time = time.time()
        self.performance_optimizer.log_performance_status(
            "Starting", "Document extraction"
        )

        try:
            # Initialize variables at the start to ensure they're always
            # defined
            processed_pages = 0
            total_neologisms = 0

            # Extract document content
            content = await asyncio.to_thread(self.processor.extract_content, file_path)

            # Calculate total pages
            total_pages = len(content.get("pages", []))
            logger.info(
                f"Processing {total_pages} pages in chunks of {self.chunk_size}"
            )

            # Process in chunks to manage memory
            for chunk_start in range(0, total_pages, self.chunk_size):
                chunk_end = min(chunk_start + self.chunk_size, total_pages)
                chunk_pages = content["pages"][chunk_start:chunk_end]

                self.performance_optimizer.log_performance_status(
                    f"Chunk {chunk_start}-{chunk_end}",
                    f"Pages {chunk_start + 1}-{chunk_end} of {total_pages}",
                )

                # Process chunk
                chunk_result = await self._process_page_chunk(
                    chunk_pages, source_lang, target_lang, provider, user_id
                )

                processed_pages += len(chunk_pages)
                total_neologisms += chunk_result["neologisms_detected"]

                # Yield progress update
                yield {
                    "type": "progress",
                    "processed_pages": processed_pages,
                    "total_pages": total_pages,
                    "progress_percent": (processed_pages / total_pages) * 100,
                    "neologisms_detected": total_neologisms,
                    "chunk_result": chunk_result,
                }

                # Memory management
                if self.enable_memory_management:
                    await self._manage_memory_usage()

                # Allow other tasks to run
                await asyncio.sleep(0.1)

            # Final result
            processing_time = time.time() - start_time
            final_metrics = self._calculate_final_metrics(
                total_pages, total_neologisms, processing_time
            )

            yield {
                "type": "complete",
                "total_pages": total_pages,
                "total_neologisms": total_neologisms,
                "processing_time": processing_time,
                "performance_metrics": final_metrics,
            }

        except Exception as e:
            logger.error(f"Error in large document processing: {e}")
            yield {
                "type": "error",
                "error": str(e),
                "processed_pages": processed_pages,
                "total_neologisms": total_neologisms,
            }

    async def _process_page_chunk(
        self,
        chunk_pages: List[Dict[str, Any]],
        source_lang: str,
        target_lang: str,
        provider: str,
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        """Process a chunk of pages concurrently."""
        # Extract texts from pages
        page_texts = []
        for page in chunk_pages:
            page_text = ""
            for block in page.get("text_blocks", []):
                page_text += block.get("text", "") + " "
            page_texts.append(page_text.strip())

        # Remove empty texts
        non_empty_texts = [text for text in page_texts if text]

        if not non_empty_texts:
            return {
                "translated_texts": [],
                "neologisms_detected": 0,
                "processing_time": 0.0,
            }

        # Process texts with philosophy enhancement
        start_time = time.time()

        # Use batch processing for efficiency
        service = self.processor.philosophy_translation_service
        results = service.translate_batch_with_neologism_handling(
            texts=non_empty_texts,
            source_lang=source_lang,
            target_lang=target_lang,
            provider=provider,
            session_id=f"large_doc_session_{user_id or 'anonymous'}",
        )

        processing_time = time.time() - start_time

        # Count neologisms
        total_neologisms = sum(
            result.neologism_analysis.total_neologisms for result in results
        )

        return {
            "translated_texts": [result.translated_text for result in results],
            "neologisms_detected": total_neologisms,
            "processing_time": processing_time,
            "results": results,
        }

    async def _manage_memory_usage(self):
        """Manage memory usage during processing."""
        metrics = self.performance_optimizer.get_current_metrics()

        if metrics["memory_mb"] > self.memory_limit_mb:
            logger.warning(
                f"Memory usage ({metrics['memory_mb']:.1f}MB) exceeds limit "
                f"({self.memory_limit_mb}MB)"
            )
            self.performance_optimizer.force_garbage_collection()

            # Brief pause to allow memory cleanup
            await asyncio.sleep(0.5)

    def _calculate_final_metrics(
        self, total_pages: int, total_neologisms: int, processing_time: float
    ) -> PerformanceMetrics:
        """Calculate final performance metrics."""
        current_metrics = self.performance_optimizer.get_current_metrics()

        pages_per_second = 0
        if processing_time > 0:
            pages_per_second = total_pages / processing_time

        neologisms_per_second = 0
        if processing_time > 0:
            neologisms_per_second = total_neologisms / processing_time

        return PerformanceMetrics(
            memory_usage_mb=current_metrics["memory_mb"],
            cpu_percent=current_metrics["cpu_percent"],
            processing_time=processing_time,
            pages_per_second=pages_per_second,
            neologisms_per_second=neologisms_per_second,
            total_pages=total_pages,
            total_neologisms=total_neologisms,
            peak_memory_mb=current_metrics["peak_memory_mb"],
        )


class ParallelProcessingOptimizer:
    """Optimizer for parallel processing of multiple documents."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def process_multiple_documents_parallel(
        self,
        document_paths: List[str],
        source_lang: str,
        target_lang: str,
        provider: str = "auto",
    ) -> List[Dict[str, Any]]:
        """Process multiple documents in parallel."""
        logger.info(
            f"Processing {len(document_paths)} documents in parallel "
            f"with {self.max_workers} workers"
        )

        # Create tasks for each document
        tasks = []
        for doc_path in document_paths:
            processor = LargeDocumentProcessor(
                max_concurrent_pages=5,  # Reduce per-document concurrency
                chunk_size=25,  # Smaller chunks for parallel
                memory_limit_mb=1024,  # Lower memory limit per worker
            )

            task = self._process_single_document_async(
                processor, doc_path, source_lang, target_lang, provider
            )
            tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error processing document {document_paths[i]}: {result}")
                processed_results.append(
                    {
                        "document_path": document_paths[i],
                        "status": "error",
                        "error": str(result),
                    }
                )
            else:
                processed_results.append(
                    {
                        "document_path": document_paths[i],
                        "status": "success",
                        "result": result,
                    }
                )

        return processed_results

    async def _process_single_document_async(
        self,
        processor: LargeDocumentProcessor,
        doc_path: str,
        source_lang: str,
        target_lang: str,
        provider: str,
    ) -> Dict[str, Any]:
        """Process a single document asynchronously."""
        results = []

        async for chunk_result in processor.process_large_document_streaming(
            doc_path, source_lang, target_lang, provider
        ):
            results.append(chunk_result)

        return {"document_path": doc_path, "chunks": results}


class PerformanceExamples:
    """Examples demonstrating performance optimization techniques."""

    def __init__(self):
        self.optimizer = PerformanceOptimizer()

    async def example_1_large_document_streaming(self):
        """Example 1: Processing large document with streaming approach."""
        print("\n" + "=" * 80)
        print("EXAMPLE 1: Large Document Processing with Streaming")
        print("=" * 80)

        # Create a large sample document
        # Simulate 100 pages
        large_content = self._create_large_sample_document(pages=100)
        temp_doc_path = Path("temp_large_doc.txt")
        temp_doc_path.write_text(large_content)

        try:
            processor = LargeDocumentProcessor(
                max_concurrent_pages=8,
                chunk_size=20,
                memory_limit_mb=1024,
                enable_memory_management=True,
            )

            print("Processing large document with streaming approach...")
            self.optimizer.log_performance_status("Starting")

            async for result in processor.process_large_document_streaming(
                str(temp_doc_path), "en", "de", "auto", "performance_user"
            ):
                if result["type"] == "progress":
                    processed = result["processed_pages"]
                    total = result["total_pages"]
                    percent = result["progress_percent"]
                    print(f"Progress: {percent:.1f}% ({processed}/{total} pages)")
                elif result["type"] == "complete":
                    print("Processing complete!")
                    print(f"Total pages: {result['total_pages']}")
                    print(f"Total neologisms: {result['total_neologisms']}")
                    print(f"Processing time: {result['processing_time']:.2f}s")
                    metrics = result["performance_metrics"]
                    print(f"Pages per second: {metrics.pages_per_second:.2f}")
                    print(f"Peak memory: {metrics.peak_memory_mb:.1f}MB")
                elif result["type"] == "error":
                    print(f"Error: {result['error']}")
                    break

        finally:
            if temp_doc_path.exists():
                temp_doc_path.unlink()

    async def example_2_parallel_document_processing(self):
        """Example 2: Parallel processing of multiple documents."""
        print("\n" + "=" * 80)
        print("EXAMPLE 2: Parallel Processing of Multiple Documents")
        print("=" * 80)

        # Create multiple sample documents
        doc_paths = []
        for i in range(3):
            content = self._create_sample_document(pages=20, doc_id=i)
            doc_path = Path(f"temp_doc_{i}.txt")
            doc_path.write_text(content)
            doc_paths.append(str(doc_path))

        try:
            parallel_processor = ParallelProcessingOptimizer(max_workers=3)

            print(f"Processing {len(doc_paths)} documents in parallel...")
            self.optimizer.log_performance_status("Starting parallel processing")

            start_time = time.time()
            processor = parallel_processor
            results = await processor.process_multiple_documents_parallel(
                doc_paths, "en", "de", "auto"
            )
            processing_time = time.time() - start_time

            print(f"Parallel processing completed in {processing_time:.2f}s")

            # Report results
            successful = sum(1 for r in results if r["status"] == "success")
            failed = sum(1 for r in results if r["status"] == "error")

            print(f"Results: {successful} successful, {failed} failed")

            for result in results:
                if result["status"] == "success":
                    doc_name = Path(result["document_path"]).name
                    chunks = result["result"]["chunks"]
                    complete_chunks = [c for c in chunks if c["type"] == "complete"]
                    final_chunk = complete_chunks[0]
                    print(
                        f"  {doc_name}: {final_chunk['total_pages']} pages, "
                        f"{final_chunk['total_neologisms']} neologisms"
                    )
                else:
                    doc_name = Path(result["document_path"]).name
                    print(f"  {doc_name}: ERROR - {result['error']}")

        finally:
            # Clean up temporary files
            for doc_path in doc_paths:
                if Path(doc_path).exists():
                    Path(doc_path).unlink()

    async def example_3_memory_optimization(self):
        """Example 3: Memory optimization techniques."""
        print("\n" + "=" * 80)
        print("EXAMPLE 3: Memory Optimization Techniques")
        print("=" * 80)

        # Create memory-intensive document
        large_content = self._create_large_sample_document(pages=200)
        temp_doc_path = Path("temp_memory_test_doc.txt")
        temp_doc_path.write_text(large_content)

        try:
            # Test with different memory settings
            memory_limits = [512, 1024, 2048]  # MB

            for memory_limit in memory_limits:
                print(f"\nTesting with {memory_limit}MB memory limit...")

                processor = LargeDocumentProcessor(
                    max_concurrent_pages=4,
                    chunk_size=10,
                    memory_limit_mb=memory_limit,
                    enable_memory_management=True,
                )

                start_time = time.time()
                peak_memory = 0

                async for result in processor.process_large_document_streaming(
                    str(temp_doc_path),
                    "en",
                    "de",
                    "auto",
                    f"memory_test_{memory_limit}",
                ):
                    if result["type"] == "progress":
                        optimizer = processor.performance_optimizer
                        metrics_data = optimizer.get_current_metrics()
                        current_memory = metrics_data["memory_mb"]
                        peak_memory = max(peak_memory, current_memory)
                    elif result["type"] == "complete":
                        processing_time = time.time() - start_time
                        print(f"  Completed in {processing_time:.2f}s")
                        print(f"  Peak memory: {peak_memory:.1f}MB")
                        metrics = result["performance_metrics"]
                        pages_per_sec = metrics.pages_per_second
                        print(f"  Pages per second: {pages_per_sec:.2f}")
                        break

                # Force cleanup between tests
                gc.collect()
                await asyncio.sleep(1)

        finally:
            if temp_doc_path.exists():
                temp_doc_path.unlink()

    def _create_large_sample_document(self, pages: int) -> str:
        """Create a large sample document for testing."""
        philosophical_concepts = [
            "Dasein",
            "Sein-zum-Tode",
            "Zuhandenheit",
            "Angst",
            "Zeitlichkeit",
            "Vorhanden",
            "Geworfenheit",
            "Entwurf",
            "Verfallenheit",
            "Sorge",
            "Authentizität",
            "Uneigentlichkeit",
            "Mitsein",
            "Mitwelt",
            "Umwelt",
        ]

        content = ""
        for page in range(pages):
            content += f"\n\nPage {page + 1}: Philosophical Analysis\n"
            content += "=" * 50 + "\n"

            for concept in philosophical_concepts:
                content += f"The concept of {concept} is fundamental to "
                content += f"understanding existential philosophy. {concept} "
                content += "reveals the structure of human existence and its "
                content += f"relationship to Being itself. Through {concept}, "
                content += "we can understand the temporal nature of human "
                content += "existence and its authentic possibilities.\n\n"

        return content

    def _create_sample_document(self, pages: int, doc_id: int) -> str:
        """Create a sample document for testing."""
        concepts = ["Dasein", "Angst", "Zuhandenheit", "Sein-zum-Tode"]

        content = f"Document {doc_id}: Philosophical Study\n"
        content += "=" * 40 + "\n\n"

        for page in range(pages):
            concept = concepts[page % len(concepts)]
            content += f"Page {page + 1}: Analysis of {concept}\n"
            content += f"The philosophical concept of {concept} is central to "
            content += f"understanding human existence. {concept} reveals "
            content += "fundamental aspects of our being-in-the-world.\n\n"

        return content


async def main():
    """Main function to run performance optimization examples."""
    print("Philosophy-Enhanced Translation System - Performance Optimization Examples")
    print("=" * 80)

    examples = PerformanceExamples()

    # Example 1: Large document streaming
    await examples.example_1_large_document_streaming()

    # Example 2: Parallel processing
    await examples.example_2_parallel_document_processing()

    # Example 3: Memory optimization
    await examples.example_3_memory_optimization()

    print("\n" + "=" * 80)
    print("Performance optimization examples completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
