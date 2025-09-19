#!/usr/bin/env python3
"""Debug script to understand cache behavior."""

from core.dynamic_language_engine import DynamicLanguageDetector


def debug_cache_behavior():
    """Debug cache behavior to understand the test failure."""
    detector = DynamicLanguageDetector()
    test_text = "Der deutsche Text ist hier zu finden."

    # Clear cache
    detector.result_cache.clear()
    print(f"Cache cleared. Size: {detector.result_cache.size()}")

    # Check initial metrics
    print(f"Initial hits: {detector.metrics.cache_hits}")
    print(f"Initial misses: {detector.metrics.cache_misses}")

    # First call
    print("\n=== First Call ===")
    result1 = detector.detect_language_optimized(test_text)
    print(f"Result: {result1}")
    print(f"Cache size after first call: {detector.result_cache.size()}")
    print(f"Hits: {detector.metrics.cache_hits}")
    print(f"Misses: {detector.metrics.cache_misses}")

    # Debug cache content
    print("\n=== Cache Debug ===")
    from core.dynamic_language_engine import TextFingerprint

    fingerprint = TextFingerprint.create(test_text)
    cache_key = fingerprint.to_cache_key()
    print(f"Cache key: {cache_key}")
    cached_result = detector.result_cache.get(cache_key)
    print(f"Cached result: {cached_result}")
    print(f"Cached result type: {type(cached_result)}")
    print(f"Cached result truthiness: {bool(cached_result)}")
    print(f"Is None: {cached_result is None}")

    # Second call
    print("\n=== Second Call ===")
    result2 = detector.detect_language_optimized(test_text)
    print(f"Result: {result2}")
    print(f"Cache size after second call: {detector.result_cache.size()}")
    print(f"Hits: {detector.metrics.cache_hits}")
    print(f"Misses: {detector.metrics.cache_misses}")

    print(f"\nResults equal: {result1 == result2}")

    # Check cache stats
    cache_stats = detector.result_cache.stats()
    print(f"Cache stats: {cache_stats}")


if __name__ == "__main__":
    debug_cache_behavior()
