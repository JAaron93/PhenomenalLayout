"""
Tests for PhenomenalLayout parallel translation service functionality.

This module tests the parallel translation capabilities including
rate limiting, error handling, and performance improvements.
"""

import asyncio
import os
import time
from unittest.mock import AsyncMock, patch

import pytest

from services.parallel_translation_service import (
    BatchProgress,
    ParallelLingoTranslator,
    ParallelTranslationConfig,
    ParallelTranslationService,
    RateLimiter,
    TranslationTask,
)


class TestRateLimiter:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limiter_basic(self):
        """Test basic rate limiting functionality."""
        limiter = RateLimiter(max_requests_per_second=2.0, burst_allowance=1)

        # Should allow immediate requests up to burst
        start_time = time.time()
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()  # This should cause a delay

        elapsed = time.time() - start_time
        # Should take at least 0.5 seconds for the third request
        assert elapsed >= 0.45  # Allow 10% tolerance for timing variations

    @pytest.mark.asyncio
    async def test_rate_limiter_concurrent(self):
        """Test rate limiter with concurrent requests."""
        limiter = RateLimiter(max_requests_per_second=5.0)

        async def make_request():
            await limiter.acquire()
            return time.time()

        # Make 10 concurrent requests
        tasks = [make_request() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # Verify requests were spread over time
        total_time = max(results) - min(results)
        # 10 requests at 5/sec should take ~1.8 seconds (9 intervals of 0.2s each)
        assert total_time >= 1.6  # Allow some tolerance for timing variations


class TestParallelTranslationConfig:
    """Test configuration management."""

    def test_config_from_environment(self):
        """Test configuration creation from environment variables."""
        with patch.dict(
            os.environ,
            {
                "MAX_CONCURRENT_REQUESTS": "15",
                "MAX_REQUESTS_PER_SECOND": "10.0",
                "TRANSLATION_BATCH_SIZE": "100",
            },
        ):
            config = ParallelTranslationConfig.from_config()
            assert config.max_concurrent_requests == 15
            assert config.max_requests_per_second == 10.0
            assert config.batch_size == 100

    def test_config_defaults(self):
        """Test default configuration values."""
        config = ParallelTranslationConfig()
        assert config.max_concurrent_requests == 10
        assert config.max_requests_per_second == 5.0
        assert config.batch_size == 50
        assert config.max_retries == 3


class TestBatchProgress:
    """Test progress tracking functionality."""

    def test_progress_calculation(self):
        """Test progress percentage calculation."""
        progress = BatchProgress(total_tasks=100)
        assert progress.progress_percentage == 0.0

        progress.completed_tasks = 50
        assert progress.progress_percentage == 50.0

        progress.completed_tasks = 100
        assert progress.progress_percentage == 100.0

    def test_time_estimation(self):
        """Test time estimation functionality."""
        progress = BatchProgress(total_tasks=100)
        progress.start_time = time.time() - 10  # 10 seconds ago
        progress.completed_tasks = 50

        # Should estimate roughly 10 more seconds
        remaining = progress.estimated_remaining_time
        assert 8 <= remaining <= 12


class TestParallelLingoTranslator:
    """Test parallel Lingo translator functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create a test configuration."""
        return ParallelTranslationConfig(
            max_concurrent_requests=5,
            max_requests_per_second=10.0,
            max_retries=2,
            request_timeout=5.0,
        )

    @pytest.fixture
    def translator(self, mock_config):
        """Create a translator instance for testing."""
        return ParallelLingoTranslator("test_api_key", mock_config)

    @pytest.mark.asyncio
    async def test_translator_initialization(self, translator):
        """Test translator initialization."""
        assert translator.api_key == "test_api_key"
        assert translator.base_url == "https://api.lingo.dev/v1/translate"
        assert translator._session is None

    @pytest.mark.asyncio
    async def test_session_management(self, translator):
        """Test HTTP session management."""
        async with translator:
            session = await translator._ensure_session()
            assert session is not None
            assert not session.closed

        # Session should be closed after context exit
        assert session.closed

    @pytest.mark.asyncio
    async def test_translation_success(self, translator):
        """Test successful translation."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"translation": "Hello World"}

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_response

            async with translator:
                task = TranslationTask(
                    text="Hallo Welt",
                    source_lang="de",
                    target_lang="en",
                    task_id="test_1",
                )

                result = await translator._translate_single_with_retry(task)

                assert result.success is True
                assert result.translated_text == "Hello World"
                assert result.task_id == "test_1"

    @pytest.mark.asyncio
    async def test_translation_retry_on_rate_limit(self, translator):
        """Test retry behavior on rate limiting."""
        # First response: rate limited
        mock_response_429 = AsyncMock()
        mock_response_429.status = 429
        mock_response_429.headers = {"Retry-After": "1"}

        # Second response: success
        mock_response_200 = AsyncMock()
        mock_response_200.status = 200
        mock_response_200.json.return_value = {"translation": "Success"}

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.side_effect = [
                mock_response_429,
                mock_response_200,
            ]

            async with translator:
                task = TranslationTask(
                    text="Test",
                    source_lang="de",
                    target_lang="en",
                    task_id="test_retry",
                )

                start_time = time.time()
                result = await translator._translate_single_with_retry(task)
                elapsed = time.time() - start_time

                assert result.success is True
                assert result.translated_text == "Success"
                assert result.retry_count == 1
                assert elapsed >= 1.0  # Should have waited for retry

    @pytest.mark.asyncio
    async def test_translation_failure_after_retries(self, translator):
        """Test failure after exhausting retries."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Internal Server Error"

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_response

            async with translator:
                task = TranslationTask(
                    text="Test", source_lang="de", target_lang="en", task_id="test_fail"
                )

                result = await translator._translate_single_with_retry(task)

                assert result.success is False
                assert result.translated_text == "Test"  # Should return original
                assert result.retry_count == translator.config.max_retries
                assert "HTTP 500" in result.error

    @pytest.mark.asyncio
    async def test_batch_translation(self, translator):
        """Test batch translation functionality."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"translation": "Translated"}

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_response

            async with translator:
                tasks = [
                    TranslationTask(f"Text {i}", "de", "en", f"task_{i}")
                    for i in range(5)
                ]

                progress_updates = []

                def progress_callback(progress):
                    progress_updates.append(progress.completed_tasks)

                results = await translator.translate_batch_parallel(
                    tasks, progress_callback
                )

                assert len(results) == 5
                assert all(r.success for r in results)
                assert all(r.translated_text == "Translated" for r in results)

                # Verify progress updates
                assert len(progress_updates) > 0
                assert (
                    progress_updates[-1] == 5
                )  # Final update should show all completed


class TestParallelTranslationService:
    """Test high-level parallel translation service."""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing."""
        config = ParallelTranslationConfig(max_concurrent_requests=3)
        return ParallelTranslationService("test_api_key", config)

    @pytest.mark.asyncio
    async def test_service_context_management(self, service):
        """Test service context management."""
        async with service:
            assert service._translator is not None

        # Verify translator exists but its session is properly closed
        assert service._translator is not None
        # Verify the session is closed if it was created
        if hasattr(service._translator, "_session") and service._translator._session:
            assert service._translator._session.closed

    @pytest.mark.asyncio
    async def test_batch_text_translation(self, service):
        """Test batch text translation."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"translation": "Translated"}

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value = mock_response

            async with service:
                texts = ["Text 1", "Text 2", "Text 3"]
                results = await service.translate_batch_texts(texts, "de", "en")

                assert len(results) == 3
                assert all(r == "Translated" for r in results)


@pytest.mark.slow
async def test_basic_functionality():
    """Basic functionality test that can be run directly.

    Note: This test duplicates coverage from TestRateLimiter.test_rate_limiter_basic
    but is kept for standalone execution. Marked as slow to exclude from default runs.
    """
    print("Testing rate limiter...")
    limiter = RateLimiter(2.0)

    start = time.time()
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = time.time() - start

    print(f"Rate limiter test completed in {elapsed:.2f}s")
    assert elapsed >= 0.4


if __name__ == "__main__":
    # Run basic tests
    asyncio.run(test_basic_functionality())


async def test_rate_limiter():
    """Test rate limiter functionality."""
    print("Testing rate limiter...")
    limiter = RateLimiter(2.0)

    start = time.time()
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = time.time() - start

    print(f"Rate limiter test completed in {elapsed:.2f}s")
    assert elapsed >= 0.4


if __name__ == "__main__":
    # Run basic tests
    asyncio.run(test_rate_limiter())
    print("Basic tests passed!")
