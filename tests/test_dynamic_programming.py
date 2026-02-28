"""Comprehensive test suite for dynamic programming implementations.

This module provides performance validation, benchmarking, and correctness
testing for all dynamic programming patterns implemented in the PhenomenalLayout
system.
"""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Performance testing configuration
PERFORMANCE_SAMPLE_COUNT = int(os.getenv("TEST_PERFORMANCE_SAMPLES", "5"))
PERFORMANCE_PERCENTILE = float(os.getenv("TEST_PERFORMANCE_PERCENTILE", "90"))
PERFORMANCE_MAX_RETRIES = int(os.getenv("TEST_PERFORMANCE_MAX_RETRIES", "3"))

try:
    import psutil
except ImportError:
    psutil = None

from core.dynamic_choice_engine import (
    DynamicConflictResolutionEngine,
)
from core.dynamic_language_engine import (
    DynamicLanguageDetector,
)
from core.dynamic_layout_engine import (
    DynamicLayoutEngine,
    OptimizedLayoutPreservationEngine,
    StrategyKey,
)
from core.dynamic_middleware import (
    DynamicProgrammingMonitor,
    SmartCachingMiddleware,
    performance_tracking,
    smart_cache,
)
from core.dynamic_programming import (
    CachePolicy,
    DynamicRegistry,
    PerformanceMetrics,
    SmartCache,
    memoize,
)
from core.dynamic_validation_engine import (
    DynamicValidationEngine,
    OptimizedFileValidator,
)
from dolphin_ocr.layout import FitAnalysis, StrategyType
from models.user_choice_models import (
    ChoiceConflict,
    ChoiceScope,
    ChoiceType,
    TranslationContext,
    UserChoice,
)


class TestDynamicProgrammingCore:
    """Test core dynamic programming patterns."""

    def test_smart_cache_lru_policy(self):
        """Test LRU cache policy."""
        cache = SmartCache(max_size=3, policy=CachePolicy.LRU)

        # Fill cache
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)

        assert cache.get("a") == 1
        assert cache.get("b") == 2
        assert cache.get("c") == 3

        # Add one more to trigger eviction
        cache.put("d", 4)

        # 'a' should be evicted (least recently used)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_smart_cache_ttl_expiration(self):
        """Test TTL cache expiration with deterministic time mock."""
        cache = SmartCache(max_size=10, ttl_seconds=0.1)

        # Mock time.time for deterministic TTL testing
        fake_time = 1000.0  # Start at a known time

        with patch("time.time", return_value=fake_time):
            cache.put("key", "value")
            assert cache.get("key") == "value"

        # Advance time past TTL threshold
        fake_time += 0.2  # More than ttl_seconds (0.1)

        with patch("time.time", return_value=fake_time):
            # Entry should be expired
            assert cache.get("key") is None

    def test_dynamic_registry_caching(self):
        """Test dynamic registry with caching."""
        registry = DynamicRegistry(cache_size=5)

        # Register a factory
        def create_string(value: str) -> str:
            return f"created_{value}"

        registry.register("string_factory", create_string)

        # Test caching
        result1 = registry.get("string_factory", "test")
        result2 = registry.get("string_factory", "test")

        assert result1 == "created_test"
        assert result2 == "created_test"

        # Check metrics
        metrics = registry.get_metrics("string_factory")
        assert metrics.total_calls >= 2
        assert metrics.cache_hits >= 1

    def test_performance_metrics_recording(self):
        """Test performance metrics collection."""
        metrics = PerformanceMetrics("test_operation")

        # Record some operations
        metrics.record_operation(10.0, cache_hit=False)
        metrics.record_operation(5.0, cache_hit=True)
        metrics.record_operation(15.0, cache_hit=False)

        assert metrics.total_calls == 3
        assert metrics.cache_hits == 1
        assert metrics.cache_misses == 2
        assert metrics.cache_hit_rate == pytest.approx(33.33, rel=1e-2)
        assert metrics.avg_duration_ms == 10.0

    def test_memoize_decorator(self):
        """Test memoization decorator."""
        call_count = 0

        @memoize(cache_size=5)
        def expensive_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * x

        # First calls should execute function
        result1 = expensive_function(5)
        result2 = expensive_function(10)
        assert result1 == 25
        assert result2 == 100
        assert call_count == 2

        # Cached calls should not execute function
        result3 = expensive_function(5)
        result4 = expensive_function(10)
        assert result3 == 25
        assert result4 == 100
        assert call_count == 2  # No additional calls

        # Check cache stats
        stats = expensive_function.cache_stats()
        assert stats["size"] >= 2


class TestDynamicLayoutEngine:
    """Test dynamic layout strategy engine."""

    def test_strategy_table_completeness(self):
        """Test that strategy table covers all possible combinations."""
        engine = DynamicLayoutEngine()

        # Should have 16 entries (2^4 combinations)
        assert len(engine.strategy_table) == 16

        # Test strategy distribution
        distribution = engine.get_strategy_distribution()
        assert StrategyType.NONE in distribution
        assert StrategyType.FONT_SCALE in distribution
        assert StrategyType.TEXT_WRAP in distribution
        assert StrategyType.HYBRID in distribution

    def test_o1_strategy_lookup_performance(self):
        """Test O(1) strategy lookup performance with percentile-based assertion."""
        engine = DynamicLayoutEngine()

        # Create test analysis
        analysis = FitAnalysis(
            length_ratio=1.5,
            one_line_width=100.0,
            max_lines=3,
            lines_needed=2,
            can_fit_without_changes=False,
            required_scale_for_single_line=0.8,
            can_scale_to_single_line=True,
            can_wrap_within_height=True,
        )

        # Configurable threshold for different CI environments
        threshold = float(os.getenv("TEST_O1_THRESHOLD_MS", "5.0"))

        def measure_performance_sample() -> list[float]:
            """Measure performance across multiple iterations and return per-iteration times."""
            iterations = 1000
            times_ms = []

            for _ in range(PERFORMANCE_SAMPLE_COUNT):
                start_time = time.perf_counter()

                for _ in range(iterations):
                    strategy = engine.determine_strategy_optimized(analysis)
                    assert strategy is not None

                duration = time.perf_counter() - start_time
                avg_time_ms = (duration / iterations) * 1000
                times_ms.append(avg_time_ms)

            return times_ms

        # Retry measurement if needed
        for attempt in range(PERFORMANCE_MAX_RETRIES):
            try:
                sample_times = measure_performance_sample()
                percentile_index = min(
                    len(sample_times) - 1,
                    int(len(sample_times) * PERFORMANCE_PERCENTILE / 100)
                )
                percentile_time = sorted(sample_times)[percentile_index]

                # Assert percentile performance
                assert percentile_time < threshold, (
                    f"P{PERFORMANCE_PERCENTILE} performance {percentile_time:.3f}ms "
                    f"exceeds threshold {threshold}ms (samples: {sample_times}, attempt {attempt + 1})"
                )
                break  # Success, exit retry loop

            except AssertionError as e:
                if attempt == PERFORMANCE_MAX_RETRIES - 1:
                    # Last attempt failed, re-raise
                    raise e
                # Retry on failure (except last attempt)
                continue

    def test_strategy_key_generation(self):
        """Test strategy key generation and uniqueness."""
        key1 = StrategyKey(True, False, True, False)
        key2 = StrategyKey(True, False, True, False)
        key3 = StrategyKey(False, True, False, True)

        assert key1 == key2
        assert key1 != key3
        assert hash(key1) == hash(key2)
        assert hash(key1) != hash(key3)

        # Test bit mask conversion
        assert key1.to_int() == key2.to_int()
        assert key1.to_int() != key3.to_int()

    def test_backward_compatibility(self):
        """Test backward compatibility wrapper."""
        optimized_engine = OptimizedLayoutPreservationEngine()

        # Test that all original methods are available
        assert hasattr(optimized_engine, "analyze_text_fit")
        assert hasattr(optimized_engine, "determine_layout_strategy")
        assert hasattr(optimized_engine, "calculate_quality_score")
        assert hasattr(optimized_engine, "apply_layout_adjustments")

        # Test strategy determination works
        analysis = FitAnalysis(
            length_ratio=1.0,
            one_line_width=50.0,
            max_lines=2,
            lines_needed=1,
            can_fit_without_changes=True,
            required_scale_for_single_line=1.0,
            can_scale_to_single_line=True,
            can_wrap_within_height=True,
        )

        strategy = optimized_engine.determine_layout_strategy(analysis)
        assert strategy.type == StrategyType.NONE


class TestDynamicLanguageEngine:
    """Test dynamic language detection engine."""

    def test_pattern_compilation(self):
        """Test language pattern compilation."""
        detector = DynamicLanguageDetector()

        # Check that patterns are compiled
        assert len(detector.compiled_patterns) > 0
        assert "German" in detector.compiled_patterns
        assert "English" in detector.compiled_patterns

        # Test compiled pattern structure
        german_pattern = detector.compiled_patterns["German"]
        assert german_pattern.language == "German"
        # German should have both word and character patterns
        assert german_pattern.words_regex is not None
        assert german_pattern.chars_regex is not None

        # English might have words but no chars (depending on language patterns)
        english_pattern = detector.compiled_patterns["English"]
        assert english_pattern.language == "English"
        # Test that at least one pattern type exists per language
        assert (
            english_pattern.words_regex is not None
            or english_pattern.chars_regex is not None
        )

    def test_detection_caching(self):
        """Test language detection caching."""
        detector = DynamicLanguageDetector()

        test_text = "Der deutsche Text ist hier zu finden."

        # Clear caches before test to ensure clean state
        detector.clear_caches()

        # Get initial cache metrics from the memoized wrapper
        wrapper_metrics = detector.detect_language_optimized.metrics()
        initial_hits = wrapper_metrics.cache_hits
        initial_misses = wrapper_metrics.cache_misses

        # First detection - should be a cache miss
        result1 = detector.detect_language_optimized(test_text)
        after_first_hits = wrapper_metrics.cache_hits
        after_first_misses = wrapper_metrics.cache_misses

        # Second detection - should be a cache hit
        result2 = detector.detect_language_optimized(test_text)
        after_second_hits = wrapper_metrics.cache_hits
        after_second_misses = wrapper_metrics.cache_misses

        # Assert results are equal
        assert result1 == result2

        # Assert cache behavior deterministically via wrapper metrics
        assert (
            after_first_misses == initial_misses + 1
        ), "First call should be cache miss"
        assert after_first_hits == initial_hits, "First call should not increase hits"
        assert after_second_hits == initial_hits + 1, "Second call should be cache hit"
        assert (
            after_second_misses == initial_misses + 1
        ), "Second call should not increase misses"

    def test_batch_detection_performance(self):
        """Test batch detection performance."""
        detector = DynamicLanguageDetector()

        test_texts = [
            "The quick brown fox jumps over the lazy dog.",
            "Der schnelle braune Fuchs springt über den faulen Hund.",
            "El rápido zorro marrón salta sobre el perro perezoso.",
            "Le renard brun rapide saute par-dessus le chien paresseux.",
        ]

        # Test batch detection
        start_time = time.perf_counter()
        results = detector.detect_languages_batch(test_texts)
        duration = time.perf_counter() - start_time

        assert len(results) == len(test_texts)

        # Should detect multiple languages
        unique_languages = set(results)
        assert len(unique_languages) > 1

        # Performance should be reasonable
        avg_time_per_text = (duration / len(test_texts)) * 1000
        assert avg_time_per_text < 100  # Less than 100ms per text

    def test_confidence_analysis(self):
        """Test confidence analysis features."""
        detector = DynamicLanguageDetector()

        german_text = "Das ist ein deutscher Text mit vielen deutschen Wörtern."
        analysis = detector.analyze_detection_confidence(german_text)

        assert "detected_language" in analysis
        assert "confidence" in analysis
        assert "confidence_gap" in analysis
        assert "all_scores" in analysis
        assert "detection_quality" in analysis

        # Should have high confidence for clear German text
        assert analysis["confidence"] > 0.5

    def test_configurable_min_length(self):
        """Test configurable minimum text length functionality."""
        from core.dynamic_language_engine import DEFAULT_MIN_TEXT_LENGTH

        # Test default minimum length
        detector_default = DynamicLanguageDetector()
        assert detector_default.min_text_length == DEFAULT_MIN_TEXT_LENGTH

        # Test custom minimum length
        custom_min = 3
        detector_custom = DynamicLanguageDetector(min_text_length=custom_min)
        assert detector_custom.min_text_length == custom_min

        # Test short text rejection with default
        short_text = "Hi"  # 2 characters
        result = detector_default.detect_language_optimized(short_text)
        assert result == "Unknown"

        # Test short text acceptance with custom minimum
        result = detector_custom.detect_language_optimized(short_text)
        assert isinstance(result, str)  # Should not be rejected for length

        # Test method-level overrides
        result = detector_default.detect_language_optimized(short_text, min_length=1)
        assert isinstance(result, str)  # Should not be rejected

        lang, conf = detector_default.detect_language_with_confidence(
            short_text, min_length=1
        )
        assert isinstance(lang, str) and isinstance(conf, float)

        scores = detector_default.get_language_scores(short_text, min_length=1)
        assert isinstance(scores, dict)

        # Test validation helper
        assert detector_custom._is_text_valid_for_detection("Hey") is True
        assert detector_custom._is_text_valid_for_detection("Hi") is False


class TestDynamicValidationEngine:
    """Test dynamic validation pipeline engine."""

    def test_dependency_graph_construction(self):
        """Test validation dependency graph construction."""
        engine = DynamicValidationEngine()

        # Check execution order respects dependencies
        execution_order = engine.graph.get_execution_order()

        assert "extension" in execution_order
        extension_index = execution_order.index("extension")

        # Validators that depend on extension should come after it
        dependent_validators = ["file_size", "pdf_header"]
        for validator in dependent_validators:
            if validator in execution_order:
                validator_index = execution_order.index(validator)
                assert validator_index > extension_index

    def test_validation_caching(self):
        """Test validation result caching."""
        engine = DynamicValidationEngine()

        # Create a temporary PDF file for testing
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            # Write minimal PDF header
            tmp_file.write(b"%PDF-1.4\n")
            tmp_file.write(b"1 0 obj\n<< /Type /Catalog >>\nendobj\n")
            tmp_file.write(b"%%EOF\n")
            tmp_file.flush()

            file_path = tmp_file.name

        try:
            # Clear caches to ensure deterministic state
            engine.clear_caches()

            # Use memoization wrapper metrics
            # for deterministic cache assertions
            wrapper_metrics = engine.validate_optimized.metrics()
            initial_hits = wrapper_metrics.cache_hits
            initial_misses = wrapper_metrics.cache_misses

            # First validation - should be a cache miss
            results1 = engine.validate_optimized(file_path)
            after_first_hits = wrapper_metrics.cache_hits
            after_first_misses = wrapper_metrics.cache_misses

            # Second validation - should be a cache hit
            results2 = engine.validate_optimized(file_path)
            after_second_hits = wrapper_metrics.cache_hits
            after_second_misses = wrapper_metrics.cache_misses

            # Results should be structurally equal in length
            assert len(results1) == len(results2)

            # Deterministic cache behavior assertions
            assert (
                after_first_misses == initial_misses + 1
            ), "First call should be cache miss"
            assert (
                after_first_hits == initial_hits
            ), "First call should not increase hits"
            assert (
                after_second_hits == initial_hits + 1
            ), "Second call should be cache hit"
            assert (
                after_second_misses == initial_misses + 1
            ), "Second call should not increase misses"

        finally:
            Path(file_path).unlink()

    def test_parallel_execution_levels(self):
        """Test parallel execution level calculation."""
        engine = DynamicValidationEngine()

        analysis = engine.analyze_dependency_impact()

        assert "execution_levels" in analysis
        assert "parallelization_opportunities" in analysis
        assert "max_parallel_validators" in analysis

        # Should identify some parallelization opportunities
        levels = analysis["execution_levels"]
        assert len(levels) > 0
        assert analysis["max_parallel_validators"] > 0

    def test_backward_compatibility(self):
        """Test backward compatibility wrapper."""
        validator = OptimizedFileValidator()

        # Test that original interface works
        result = validator.validate_file("test.pdf", 1024)

        assert "valid" in result
        assert isinstance(result["valid"], bool)

        if not result["valid"]:
            assert "error" in result


class TestDynamicChoiceEngine:
    """Test dynamic choice resolution engine."""

    def test_conflict_key_generation(self):
        """Test conflict key generation and hashing."""
        from core.dynamic_choice_engine import ConflictKey, ConflictType

        key1 = ConflictKey(
            conflict_type=ConflictType.TRANSLATION_MISMATCH,
            severity_range=(0.5, 0.8),
            context_similarity=0.7,
            confidence_gap=0.3,
            temporal_distance_hours=2.0,
        )

        key2 = ConflictKey(
            conflict_type=ConflictType.TRANSLATION_MISMATCH,
            severity_range=(0.5, 0.8),
            context_similarity=0.7,
            confidence_gap=0.3,
            temporal_distance_hours=2.0,
        )

        assert key1.to_hash() == key2.to_hash()

    def test_resolution_strategy_application(self):
        """Test resolution strategy application."""
        engine = DynamicConflictResolutionEngine()

        # Create mock choices
        context_a = TranslationContext(
            sentence_context="Test context",
            semantic_field="philosophy",
            source_language="German",
            target_language="English",
        )

        choice_a = UserChoice(
            choice_id="choice_a",
            neologism_term="Dasein",
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            context=context_a,
            choice_scope=ChoiceScope.CONTEXTUAL,
            confidence_level=0.8,
            created_at="2023-01-01T10:00:00",
        )

        choice_b = UserChoice(
            choice_id="choice_b",
            neologism_term="Dasein",
            choice_type=ChoiceType.TRANSLATE,
            translation_result="existence",
            context=context_a,
            choice_scope=ChoiceScope.CONTEXTUAL,
            confidence_level=0.6,
            created_at="2023-01-01T11:00:00",
        )

        conflict = ChoiceConflict(
            conflict_id="test_conflict",
            neologism_term="Dasein",
            choice_a=choice_a,
            choice_b=choice_b,
            context_similarity=0.9,
        )

        # Test resolution
        resolved_choice_id = engine.resolve_conflict_optimized(conflict)

        assert resolved_choice_id in [choice_a.choice_id, choice_b.choice_id]

    def test_batch_resolution_performance(self):
        """Test batch conflict resolution performance."""
        engine = DynamicConflictResolutionEngine()

        # Create multiple mock conflicts
        conflicts = []
        for i in range(10):
            context = TranslationContext(
                sentence_context=f"Context {i}",
                semantic_field="test",
                source_language="German",
                target_language="English",
            )

            choice_a = UserChoice(
                choice_id=f"choice_a_{i}",
                neologism_term=f"term_{i}",
                choice_type=ChoiceType.TRANSLATE,
                translation_result=f"translation_a_{i}",
                context=context,
                choice_scope=ChoiceScope.CONTEXTUAL,
                confidence_level=0.8,
                created_at="2023-01-01T10:00:00",
            )

            choice_b = UserChoice(
                choice_id=f"choice_b_{i}",
                neologism_term=f"term_{i}",
                choice_type=ChoiceType.TRANSLATE,
                translation_result=f"translation_b_{i}",
                context=context,
                choice_scope=ChoiceScope.CONTEXTUAL,
                confidence_level=0.6,
                created_at="2023-01-01T11:00:00",
            )

            conflict = ChoiceConflict(
                conflict_id=f"conflict_{i}",
                neologism_term=f"term_{i}",
                choice_a=choice_a,
                choice_b=choice_b,
                context_similarity=0.5,
            )

            conflicts.append(conflict)

        # Test batch resolution
        start_time = time.perf_counter()
        results = engine.resolve_conflicts_batch(conflicts)
        duration = time.perf_counter() - start_time

        assert len(results) == len(conflicts)

        # Should complete in reasonable time
        avg_time_per_conflict = (duration / len(conflicts)) * 1000
        assert avg_time_per_conflict < 50  # Less than 50ms per conflict


class TestDynamicMiddleware:
    """Test performance monitoring and caching middleware."""

    def test_performance_monitor(self):
        """Test performance monitoring."""
        monitor = DynamicProgrammingMonitor()

        # Record some operations
        monitor.record_operation("test_op", 10.0, cache_hit=False)
        monitor.record_operation("test_op", 5.0, cache_hit=True)
        monitor.record_operation("test_op", 15.0, cache_hit=False, error=True)

        # Get summary
        summary = monitor.get_performance_summary()

        assert "test_op" in summary
        test_metrics = summary["test_op"]

        assert test_metrics["total_requests"] == 3
        assert test_metrics["cache_hit_rate"] == pytest.approx(33.33, rel=1e-2)
        assert test_metrics["error_rate"] == pytest.approx(33.33, rel=1e-2)

    def test_caching_middleware(self):
        """Test smart caching middleware."""
        middleware = SmartCachingMiddleware()

        call_count = 0

        def test_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # Test cached calls
        result1 = middleware.cached_call("test_cache", test_function, 5)
        result2 = middleware.cached_call("test_cache", test_function, 5)
        result3 = middleware.cached_call("test_cache", test_function, 10)

        assert result1 == 10
        assert result2 == 10
        assert result3 == 20
        assert call_count == 2  # Only 2 actual function calls

        # Check cache statistics
        stats = middleware.get_cache_statistics()
        assert "test_cache" in stats

    def test_decorator_integration(self):
        """Test decorator integration."""
        call_count = 0

        @performance_tracking("decorated_function")
        @smart_cache("decorator_cache", size=5)
        def decorated_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x**2

        # Test function works with decorators
        result1 = decorated_function(3)
        result2 = decorated_function(3)  # Should be cached
        result3 = decorated_function(4)

        assert result1 == 9
        assert result2 == 9
        assert result3 == 16
        assert call_count == 2  # Only 2 actual calls due to caching


class TestIntegrationPerformance:
    """Integration tests for performance improvements."""

    def test_end_to_end_performance_improvement(self):
        """Test end-to-end performance improvement."""
        # This would typically compare against baseline measurements
        # For now, we'll test that operations complete within reasonable time

        # Layout engine
        layout_engine = DynamicLayoutEngine()
        analysis = FitAnalysis(
            length_ratio=1.2,
            one_line_width=80.0,
            max_lines=2,
            lines_needed=2,
            can_fit_without_changes=False,
            required_scale_for_single_line=0.9,
            can_scale_to_single_line=True,
            can_wrap_within_height=True,
        )

        start_time = time.perf_counter()
        for _ in range(100):
            strategy = layout_engine.determine_strategy_optimized(analysis)
            assert strategy is not None
        layout_duration = time.perf_counter() - start_time

        # Language detection
        language_detector = DynamicLanguageDetector()
        test_texts = [
            "This is English text.",
            "Das ist deutscher Text.",
            "Esto es texto en español.",
        ] * 10

        start_time = time.perf_counter()
        for text in test_texts:
            language = language_detector.detect_language_optimized(text)
            assert language != "Unknown"
        language_duration = time.perf_counter() - start_time

        # All operations should complete quickly
        assert layout_duration < 1.0  # Less than 1 second for 100 operations
        assert language_duration < 5.0  # Less than 5 seconds for 30 texts

    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    def test_memory_efficiency(self):
        """Test memory efficiency of caching systems."""

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create multiple engines with caching
        engines = []
        for i in range(10):
            engine = DynamicLayoutEngine()
            engines.append(engine)

            # Perform some operations to populate caches
            analysis = FitAnalysis(
                length_ratio=1.0 + i * 0.1,
                one_line_width=50.0 + i * 10,
                max_lines=2,
                lines_needed=1,
                can_fit_without_changes=i % 2 == 0,
                required_scale_for_single_line=1.0,
                can_scale_to_single_line=True,
                can_wrap_within_height=True,
            )

            for _ in range(10):
                engine.determine_strategy_optimized(analysis)

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 50MB)
        assert memory_increase < 50 * 1024 * 1024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
