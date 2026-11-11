"""Comprehensive test suite for dynamic programming implementations.

This module provides performance validation, benchmarking, and correctness
testing for all dynamic programming patterns implemented in the PhenomenalLayout
system.
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from core.dynamic_choice_engine import (
    DynamicConflictResolutionEngine,
)
from core.dynamic_language_engine import (
    DynamicLanguageDetector,
)
from core.dynamic_middleware import (
    DynamicProgrammingMonitor,
    SmartCachingMiddleware,
    performance_tracking,
    smart_cache,
)
from core.dynamic_programming import (
    CachePolicy,
    DecisionTreeNode,
    DynamicFactory,
    DynamicRegistry,
    PerformanceMetrics,
    SmartCache,
    StrategyPattern,
    StrategyRegistry,
    _normalize_value,
    clear_all_registries,
    get_registry,
    memoize,
    performance_monitor,
)
from core.dynamic_validation_engine import (
    DynamicValidationEngine,
    OptimizedFileValidator,
)
from models.user_choice_models import (
    ChoiceConflict,
    ChoiceScope,
    ChoiceType,
    TranslationContext,
    UserChoice,
)

# Performance testing configuration
PERFORMANCE_SAMPLE_COUNT = int(os.getenv("TEST_PERFORMANCE_SAMPLES", "5"))
PERFORMANCE_PERCENTILE = float(os.getenv("TEST_PERFORMANCE_PERCENTILE", "90"))
PERFORMANCE_MAX_RETRIES = int(os.getenv("TEST_PERFORMANCE_MAX_RETRIES", "3"))


class TestDynamicProgrammingCore:
    """Test core dynamic programming patterns."""

    def test_smart_cache_lru_policy(self):
        """Test LRU cache policy."""
        cache: SmartCache[str, int] = SmartCache(max_size=3, policy=CachePolicy.LRU)

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
        assert cache.get("a") is cache.MISS
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_smart_cache_ttl_expiration(self):
        """Test TTL cache expiration with deterministic time mock."""
        cache: SmartCache[str, str] = SmartCache(max_size=10, ttl_seconds=0.1)

        # Mock time.time for deterministic TTL testing
        fake_time = 1000.0  # Start at a known time

        with patch("time.time", return_value=fake_time):
            cache.put("key", "value")
            assert cache.get("key") == "value"

        # Advance time past TTL threshold
        fake_time += 0.2  # More than ttl_seconds (0.1)

        with patch("time.time", return_value=fake_time):
            # Entry should be expired
            assert cache.get("key") is cache.MISS

    def test_dynamic_registry_caching(self):
        """Test dynamic registry with caching."""
        registry: DynamicRegistry[str] = DynamicRegistry(cache_size=5)

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
        assert isinstance(metrics, PerformanceMetrics)
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

    def test_registry_cache_key_recomputation_optimization(self):
        """Test that DynamicRegistry calls _create_cache_key only once per get operation."""
        registry: DynamicRegistry[int] = DynamicRegistry(cache_size=5)

        def factory(x):
            return x

        registry.register("test", factory)

        with patch.object(
            registry, "_create_cache_key", side_effect=registry._create_cache_key
        ) as mock_key_gen:
            # First call: miss, should call _create_cache_key once
            registry.get("test", 1)
            assert mock_key_gen.call_count == 1

            # Second call: hit, should call _create_cache_key once
            mock_key_gen.reset_mock()
            registry.get("test", 1)
            assert mock_key_gen.call_count == 1

    def test_factory_cache_key_recomputation_optimization(self):
        """Test that DynamicFactory calls _create_cache_key only once per create operation."""
        from core.dynamic_programming import DynamicFactory

        factory: DynamicFactory[int] = DynamicFactory()

        def creator(x):
            return x

        factory.register("test", creator)

        with patch.object(
            factory, "_create_cache_key", side_effect=factory._create_cache_key
        ) as mock_key_gen:
            # First call: miss, should call _create_cache_key once
            factory.create("test", 1)
            assert mock_key_gen.call_count == 1

            # Second call: hit, should call _create_cache_key once
            mock_key_gen.reset_mock()
            factory.create("test", 1)
            assert mock_key_gen.call_count == 1


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
        assert language_duration < 5.0  # Less than 5 seconds for 30 texts


class TestNormalizeValue:
    """Tests for _normalize_value unhashable-value normalization branches."""

    def test_dict_with_sortable_keys_normalizes_deterministically(self) -> None:
        """Dict values normalize to sorted key-value tuples regardless of order."""
        value_a = {"b": 1, "a": [1, 2]}
        value_b = {"a": [1, 2], "b": 1}

        normalized = _normalize_value(value_a)

        assert normalized == _normalize_value(value_b)
        assert normalized == (("a", (1, 2)), ("b", 1))

    def test_dict_with_mixed_key_types_uses_fallback_sort(self) -> None:
        """Dicts whose keys cannot be co-sorted fall back to a stable sort."""
        normalized = _normalize_value({1: "int-key", "b": "str-key"})

        assert normalized == _normalize_value({"b": "str-key", 1: "int-key"})

    def test_empty_dict_normalizes_to_empty_tuple(self) -> None:
        """An empty dict normalizes without iterating any items."""
        assert _normalize_value({}) == ()

    def test_unhashable_object_with_attributes_normalizes_to_class_and_attrs(self) -> None:
        """Unhashable plain objects normalize via their sorted __dict__ items."""

        class _UnhashableWidget:
            __hash__ = None  # type: ignore[assignment]

            def __init__(self) -> None:
                self.b = 2
                self.a = [1]

        normalized = _normalize_value(_UnhashableWidget())

        assert normalized == ("_UnhashableWidget", (("a", (1,)), ("b", 2)))

    def test_unhashable_object_with_empty_dict_normalizes_to_class_name_only(
        self,
    ) -> None:
        """Unhashable objects without attributes still yield a stable identity."""

        class _UnhashableEmpty:
            __hash__ = None  # type: ignore[assignment]

        assert _normalize_value(_UnhashableEmpty()) == ("_UnhashableEmpty", ())

    def test_unhashable_value_without_dict_uses_repr(self) -> None:
        """Unhashable values with no __dict__ fall back to repr()."""
        payload = bytearray(b"abc")

        assert _normalize_value(payload) == "bytearray(b'abc')"
        assert _normalize_value(bytearray(b"abc")) == _normalize_value(payload)


class TestDynamicRegistryExtras:
    """Additional DynamicRegistry behavior tests for uncovered branches."""

    def test_get_with_keyword_arguments_normalizes_kwargs_into_cache_key(self) -> None:
        """Keyword arguments participate in cache keys and are normalized."""
        registry: DynamicRegistry[str] = DynamicRegistry(cache_size=5)
        calls: list[tuple[int, int]] = []

        def factory(left: int, right: int = 0) -> str:
            calls.append((left, right))
            return f"{left}-{right}"

        registry.register("pair", factory)

        assert registry.get("pair", 1, right=2) == "1-2"
        assert registry.get("pair", 1, right=2) == "1-2"  # served from cache
        assert registry.get("pair", 1) == "1-0"  # distinct kwargs -> new entry
        assert len(calls) == 2

    def test_get_unregistered_key_returns_none(self) -> None:
        """Requesting an unregistered key returns None instead of raising."""
        registry: DynamicRegistry[str] = DynamicRegistry()

        assert registry.get("missing-key") is None

    def test_get_with_cache_disabled_bypasses_cache(self) -> None:
        """cache_enabled=False skips both cache lookup and cache insertion."""
        registry: DynamicRegistry[str] = DynamicRegistry()
        calls: list[int] = []

        def factory(value: int) -> str:
            calls.append(value)
            return f"v{value}"

        registry.register("counter", factory)

        first = registry.get("counter", 7, cache_enabled=False)
        second = registry.get("counter", 7, cache_enabled=False)

        assert first == second == "v7"
        assert len(calls) == 2

    def test_factory_exception_is_recorded_and_reraised(self) -> None:
        """Factory failures record metrics before propagating the exception."""
        registry: DynamicRegistry[str] = DynamicRegistry()

        def broken() -> str:
            raise RuntimeError("factory failure")

        registry.register("broken", broken)

        with pytest.raises(RuntimeError, match=r"factory failure"):
            registry.get("broken")

        metrics = registry.get_metrics("broken")
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.cache_misses == 1

    def test_register_same_key_twice_keeps_single_metric_entry(self) -> None:
        """Re-registering a key replaces the factory without duplicating metrics."""
        registry: DynamicRegistry[str] = DynamicRegistry()
        registry.register("dup", lambda: "first")
        registry.register("dup", lambda: "second")

        assert registry.get("dup") == "second"

        all_metrics = registry.get_metrics()
        assert isinstance(all_metrics, dict)
        assert "dup" in all_metrics

    def test_clear_cache_forces_recreation(self) -> None:
        """clear_cache drops cached instances so factories re-run."""
        registry: DynamicRegistry[str] = DynamicRegistry()
        calls: list[int] = []

        def factory(value: int) -> str:
            calls.append(value)
            return f"v{value}"

        registry.register("reset", factory)

        registry.get("reset", 1)
        registry.clear_cache()
        registry.get("reset", 1)

        assert len(calls) == 2


class TestPerformanceMetricsImprovement:
    """Tests for PerformanceMetrics improvement and time-savings computations."""

    def test_cache_hit_rate_with_no_calls_is_zero(self) -> None:
        """An unused metrics object reports a 0% cache hit rate."""
        metrics = PerformanceMetrics("no_calls")

        assert metrics.cache_hit_rate == 0.0

    def test_performance_improvement_without_hits_is_zero(self) -> None:
        """Without cache hits there is no measurable caching benefit."""
        metrics = PerformanceMetrics("no_hits")
        metrics.record_operation(10.0, cache_hit=False)

        assert metrics.performance_improvement == 0.0

    def test_performance_improvement_with_zero_miss_duration_falls_back_to_ratio(
        self,
    ) -> None:
        """Zero-duration misses push the estimate through the ratio fallback."""
        metrics = PerformanceMetrics("zero_miss")
        metrics.record_operation(0.0, cache_hit=False)
        metrics.record_operation(5.0, cache_hit=True)

        assert metrics.performance_improvement == 0.0

    def test_performance_improvement_measured_from_durations(self) -> None:
        """Measured cached/uncached durations drive the improvement estimate."""
        metrics = PerformanceMetrics("measured")
        for _ in range(2):
            metrics.record_operation(10.0, cache_hit=False)
            metrics.record_operation(2.0, cache_hit=True)

        # avg uncached 10ms; 2 hits would have cost 20ms uncached vs 4ms cached
        # -> 16ms saved out of 24ms total -> ~66.7%.
        assert metrics.performance_improvement == pytest.approx(66.67, rel=1e-2)

    def test_performance_improvement_without_misses_uses_average_duration(self) -> None:
        """With no misses, avg_duration stands in for the uncached baseline."""
        metrics = PerformanceMetrics("hits_only")
        metrics.record_operation(4.0, cache_hit=True)

        # Baseline equals the cached duration, so measured savings are zero.
        assert metrics.performance_improvement == 0.0

    def test_time_savings_ratio_measured_and_clamped(self) -> None:
        """Measured savings ratio is derived from durations and clamped to [0, 1]."""
        metrics = PerformanceMetrics("ratio")
        metrics.record_operation(10.0, cache_hit=False)
        metrics.record_operation(2.0, cache_hit=True)
        assert metrics._compute_time_savings_ratio() == pytest.approx(0.8)

        inverted = PerformanceMetrics("ratio_inverted")
        inverted.record_operation(2.0, cache_hit=False)
        inverted.record_operation(10.0, cache_hit=True)
        assert inverted._compute_time_savings_ratio() == 0.0

    def test_time_savings_ratio_insufficient_data_uses_configured(self) -> None:
        """Without hit/miss data the configured savings ratio is used as-is."""
        metrics = PerformanceMetrics("configured")
        metrics.cache_time_savings_ratio = 0.7
        assert metrics._compute_time_savings_ratio() == 0.7

        only_hits = PerformanceMetrics("only_hits")
        only_hits.cache_time_savings_ratio = 0.6
        only_hits.record_operation(1.0, cache_hit=True)
        assert only_hits._compute_time_savings_ratio() == 0.6


class TestSmartCachePolicyBranches:
    """Tests for SmartCache LRU/LFU/FIFO auxiliary-structure branches."""

    def test_lfu_evicts_least_frequently_used(self) -> None:
        """LFU eviction removes the entry with the lowest access count."""
        cache: SmartCache[str, int] = SmartCache(max_size=2, policy=CachePolicy.LFU)

        cache.put("a", 1)
        cache.put("b", 2)
        assert cache.get("a") == 1  # raises a's frequency above b's
        cache.put("c", 3)  # triggers eviction of b

        assert cache.get("b") is cache.MISS
        assert cache.get("a") == 1
        assert cache.get("c") == 3

    def test_lfu_access_updates_heap_counts(self) -> None:
        """Repeated LFU accesses push updated counts and skip stale heap entries."""
        cache: SmartCache[str, int] = SmartCache(max_size=3, policy=CachePolicy.LFU)

        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.get("a")
        cache.get("a")
        cache.get("b")
        cache.put("d", 4)  # evicts c, whose heap entry has count 0

        assert cache.get("c") is cache.MISS
        assert cache.get("a") == 1
        assert cache.get("b") == 2
        assert cache.get("d") == 4

    def test_fifo_put_existing_key_moves_to_back(self) -> None:
        """FIFO re-insertion of an existing key moves it behind newer entries."""
        cache: SmartCache[str, int] = SmartCache(max_size=2, policy=CachePolicy.FIFO)

        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 10)  # a is re-ordered behind b
        cache.put("c", 3)  # evicts b, the oldest entry

        assert cache.get("b") is cache.MISS
        assert cache.get("a") == 10
        assert cache.get("c") == 3

    def test_ttl_expiration_removes_fifo_auxiliary_entry(self) -> None:
        """TTL expiry also removes the key from the FIFO auxiliary structure."""
        cache: SmartCache[str, int] = SmartCache(
            max_size=4, policy=CachePolicy.FIFO, ttl_seconds=0.05
        )

        with patch("time.time", return_value=1000.0):
            cache.put("k", 1)
        with patch("time.time", return_value=1100.0):
            assert cache.get("k") is cache.MISS
            assert cache.get("k") is cache.MISS

        assert cache.size() == 0

    def test_remove_key_for_missing_entry_is_silent(self) -> None:
        """_remove_key tolerates keys that were never stored."""
        cache: SmartCache[str, int] = SmartCache(max_size=2)

        cache._remove_key("never-stored")

        assert cache.size() == 0

    def test_evict_one_on_empty_cache_is_noop(self) -> None:
        """_evict_one on an empty cache performs no eviction."""
        cache: SmartCache[str, int] = SmartCache(max_size=2)

        cache._evict_one()

        assert cache.size() == 0

    def test_lru_get_resyncs_missing_access_order_entry(self) -> None:
        """LRU get re-registers cached keys missing from the access-order map."""
        cache: SmartCache[str, int] = SmartCache(max_size=4, policy=CachePolicy.LRU)
        cache.put("k", 5)
        # Simulate auxiliary-structure desync: value cached but LRU order lost.
        cache._access_order.clear()

        assert cache.get("k") == 5
        assert "k" in cache._access_order

    def test_lru_put_existing_key_moves_to_end(self) -> None:
        """LRU put of an existing key refreshes its recency position."""
        cache: SmartCache[str, int] = SmartCache(max_size=2, policy=CachePolicy.LRU)

        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 10)  # refresh a -> b becomes least recently used
        cache.put("c", 3)

        assert cache.get("b") is cache.MISS
        assert cache.get("a") == 10
        assert cache.get("c") == 3


class TestDecisionTreeNodeBehavior:
    """Tests for DecisionTreeNode evaluation and per-node caching."""

    def test_init_defaults_children_and_cache(self) -> None:
        """Nodes default to no children and no cache."""
        node: DecisionTreeNode[str] = DecisionTreeNode(
            condition=lambda _ctx: True, result="leaf"
        )

        assert node.children == []
        assert node.cache is None

    def test_evaluate_returns_direct_result_and_caches(self) -> None:
        """A node with a result returns it and stores it in the node cache."""
        cache: SmartCache[str, str] = SmartCache(max_size=4)
        node: DecisionTreeNode[str] = DecisionTreeNode(
            condition=lambda _ctx: True, result="direct", cache=cache
        )
        context = {"mode": "fast"}

        first = node.evaluate(context)
        second = node.evaluate(dict(context))

        assert first == "direct"
        assert second == "direct"  # served from the node cache
        assert cache.size() == 1

    def test_evaluate_condition_false_returns_none(self) -> None:
        """A false condition short-circuits to None."""
        node: DecisionTreeNode[str] = DecisionTreeNode(
            condition=lambda _ctx: False, result="x"
        )

        assert node.evaluate({"mode": "slow"}) is None

    def test_evaluate_falls_through_to_children(self) -> None:
        """Child results are evaluated and cached at the parent node."""
        child_match: DecisionTreeNode[str] = DecisionTreeNode(
            condition=lambda ctx: ctx.get("tier") == "pro", result="pro-result"
        )
        root_cache: SmartCache[str, str] = SmartCache(max_size=4)
        root: DecisionTreeNode[str] = DecisionTreeNode(
            condition=lambda _ctx: True, cache=root_cache
        )
        root.children.append(child_match)

        first = root.evaluate({"tier": "pro"})
        second = root.evaluate({"tier": "pro"})

        assert first == "pro-result"
        assert second == "pro-result"  # served from the root cache
        assert root_cache.size() == 1
        assert root.evaluate({"tier": "free"}) is None

    def test_evaluate_without_result_or_children_returns_none(self) -> None:
        """A result-less childless node evaluates to None."""
        node: DecisionTreeNode[str] = DecisionTreeNode(condition=lambda _ctx: True)

        assert node.evaluate({"anything": 1}) is None

    def test_context_key_uses_object_attributes(self) -> None:
        """Objects with __dict__ produce attribute-derived deterministic keys."""
        node: DecisionTreeNode[str] = DecisionTreeNode(
            condition=lambda _ctx: True, result="r"
        )

        class _Context:
            def __init__(self) -> None:
                self.b = 2
                self.a = 1

        key_one = node._create_context_key(_Context())
        key_two = node._create_context_key(_Context())

        assert key_one == key_two
        assert len(key_one) == 16

    def test_context_key_for_plain_value_uses_str(self) -> None:
        """Plain values without __dict__ hash via their string form."""
        node: DecisionTreeNode[str] = DecisionTreeNode(
            condition=lambda _ctx: True, result="r"
        )

        assert node._create_context_key("plain-value") == node._create_context_key(
            "plain-value"
        )


class TestStrategyRegistrySelection:
    """Tests for StrategyPattern default bodies and StrategyRegistry selection."""

    def test_registry_selects_by_priority_and_caches(self) -> None:
        """Selection honors priority order and caches repeated selections."""

        class _LowPriority(StrategyPattern[str]):
            def execute(self, _context: Any) -> str:
                return "low"

            def can_handle(self, _context: Any) -> bool:
                return True

            @property
            def priority(self) -> int:
                return 1

        class _HighPriority(StrategyPattern[str]):
            def execute(self, _context: Any) -> str:
                return "high"

            def can_handle(self, context: Any) -> bool:
                return context == "match"

            @property
            def priority(self) -> int:
                return 9

        registry: StrategyRegistry[str] = StrategyRegistry()
        registry.register(_LowPriority())
        registry.register(_HighPriority())
        assert len(registry) == 2

        selected = registry.select_strategy("match")
        assert isinstance(selected, _HighPriority)
        assert registry.select_strategy("match") is selected  # cached selection
        assert registry.execute("match") == "high"
        assert registry.get_metrics().total_calls >= 2

    def test_select_strategy_supports_plain_value_contexts(self) -> None:
        """String contexts are hashed via str() in the selection cache key."""

        class _Always(StrategyPattern[str]):
            def execute(self, _context: Any) -> str:
                return "always"

            def can_handle(self, _context: Any) -> bool:
                return True

            @property
            def priority(self) -> int:
                return 5

        registry: StrategyRegistry[str] = StrategyRegistry()
        registry.register(_Always())

        assert registry.select_strategy("raw-string-context") is not None

    def test_execute_without_matching_strategy_returns_none(self) -> None:
        """Neither selection nor execution finds a handler for unmatched input."""

        class _Never(StrategyPattern[str]):
            def execute(self, _context: Any) -> str:
                return "never"

            def can_handle(self, _context: Any) -> bool:
                return False

            @property
            def priority(self) -> int:
                return 5

        registry: StrategyRegistry[str] = StrategyRegistry()
        registry.register(_Never())

        assert registry.select_strategy("anything") is None
        assert registry.execute("anything") is None


class TestDecoratorExceptionHandling:
    """Tests for decorator error paths."""

    def test_performance_monitor_records_failures_and_reraises(self) -> None:
        """performance_monitor records failed operations before re-raising."""

        @performance_monitor("failing_operation")
        def explode() -> float:
            raise RuntimeError("monitored failure")

        with pytest.raises(RuntimeError, match=r"monitored failure"):
            explode()

        metrics = explode.get_metrics()
        assert metrics.total_calls == 1
        assert metrics.max_duration_ms >= 0.0


class TestDynamicFactoryBranches:
    """Tests for DynamicFactory unknown-type and cache-disabled branches."""

    def test_create_unknown_type_returns_none(self) -> None:
        """Creating an unregistered type returns None."""
        factory: DynamicFactory[str] = DynamicFactory()

        assert factory.create("no-such-type") is None

    def test_create_with_cache_disabled_calls_creator_each_time(self) -> None:
        """cache_enabled=False bypasses the factory cache entirely."""
        factory: DynamicFactory[str] = DynamicFactory()
        calls: list[int] = []

        def creator(value: int) -> str:
            calls.append(value)
            return f"made-{value}"

        factory.register("maker", creator)

        assert factory.create("maker", 3, cache_enabled=False) == "made-3"
        assert factory.create("maker", 3, cache_enabled=False) == "made-3"
        assert len(calls) == 2

        factory.clear_cache()
        assert factory.create("maker", 3) == "made-3"
        assert len(calls) == 3


class TestGlobalRegistryHelpers:
    """Tests for the module-level registry helpers."""

    def test_get_registry_reuses_instance_per_name(self) -> None:
        """Repeated lookups with the same name return the same registry."""
        try:
            first = get_registry("covgap-registry-a", cache_size=8)
            second = get_registry("covgap-registry-a")

            assert first is second
            assert first._cache.max_size == 8
        finally:
            clear_all_registries("covgap-registry-a")

    def test_clear_all_registries_with_name_removes_only_that_registry(self) -> None:
        """Named cleanup removes only the target registry instance."""
        try:
            keep = get_registry("covgap-registry-keep")
            drop = get_registry("covgap-registry-drop")

            clear_all_registries("covgap-registry-drop")

            assert get_registry("covgap-registry-drop") is not drop
            assert get_registry("covgap-registry-keep") is keep
        finally:
            clear_all_registries("covgap-registry-keep")
            clear_all_registries("covgap-registry-drop")

    def test_clear_all_registries_without_name_clears_everything(self) -> None:
        """Unnamed cleanup clears every cached global registry."""
        get_registry("covgap-registry-sweep")

        clear_all_registries()

        fresh = get_registry("covgap-registry-sweep")
        assert fresh._cache.max_size == 256
        clear_all_registries("covgap-registry-sweep")
