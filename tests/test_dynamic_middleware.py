"""Tests for performance middleware (core/dynamic_middleware.py)."""

from __future__ import annotations

import pytest

from core.dynamic_middleware import (
    DynamicProgrammingMonitor,
    MiddlewareMetrics,
    SmartCachingMiddleware,
    generate_performance_report,
    get_global_cache_middleware,
    get_global_monitor,
    hybrid_optimization,
    performance_tracking,
    reset_all_metrics,
    smart_cache,
)
from core.dynamic_programming import CachePolicy


class TestMiddlewareMetrics:
    def test_empty_metrics(self) -> None:
        metrics = MiddlewareMetrics()
        assert metrics.cache_hit_rate == 0.0
        assert metrics.avg_duration_ms == 0.0
        assert metrics.error_rate == 0.0

    def test_record_request_tracks_hits_misses_and_errors(self) -> None:
        metrics = MiddlewareMetrics()
        metrics.record_request(10.0, cache_hit=True)
        metrics.record_request(30.0, cache_hit=False, error=True)
        assert metrics.total_requests == 2
        assert metrics.cache_hits == 1
        assert metrics.cache_misses == 1
        assert metrics.error_count == 1
        assert metrics.cache_hit_rate == pytest.approx(50.0)
        assert metrics.avg_duration_ms == pytest.approx(20.0)
        assert metrics.error_rate == pytest.approx(50.0)
        assert metrics.min_duration_ms == pytest.approx(10.0)
        assert metrics.max_duration_ms == pytest.approx(30.0)


class TestDynamicProgrammingMonitorInit:
    def test_explicit_factor(self) -> None:
        monitor = DynamicProgrammingMonitor(cache_time_savings_factor=0.7)
        assert monitor.cache_time_savings_factor == pytest.approx(0.7)

    def test_factor_from_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CACHE_TIME_SAVINGS_FACTOR", "0.8")
        monitor = DynamicProgrammingMonitor()
        assert monitor.cache_time_savings_factor == pytest.approx(0.8)

    def test_non_numeric_environment_value_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CACHE_TIME_SAVINGS_FACTOR", "not-a-float")
        with pytest.raises(ValueError, match=r"Invalid CACHE_TIME_SAVINGS_FACTOR"):
            DynamicProgrammingMonitor()

    def test_non_positive_environment_value_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CACHE_TIME_SAVINGS_FACTOR", "0")
        with pytest.raises(ValueError, match="greater than 0"):
            DynamicProgrammingMonitor()

    def test_non_positive_explicit_factor_rejected(self) -> None:
        with pytest.raises(ValueError, match="greater than 0"):
            DynamicProgrammingMonitor(cache_time_savings_factor=-1.0)


class TestDynamicProgrammingMonitor:
    def test_record_operation_and_summary(self) -> None:
        monitor = DynamicProgrammingMonitor(cache_time_savings_factor=0.9)
        monitor.record_operation("op", 10.0, cache_hit=True, pattern_type="cache")
        monitor.record_operation("op", 20.0, cache_hit=False)
        summary = monitor.get_performance_summary()
        op_summary = summary["op"]
        assert op_summary["total_requests"] == 2
        assert op_summary["cache_hit_rate"] == pytest.approx(50.0)
        assert op_summary["avg_duration_ms"] == pytest.approx(15.0)
        assert op_summary["error_rate"] == 0.0
        assert summary["pattern_usage"] == {"cache": 1}
        assert summary["total_operations"] == 2
        assert summary["overall_cache_hit_rate"] == pytest.approx(50.0)

    def test_summary_for_empty_monitor(self) -> None:
        summary = DynamicProgrammingMonitor().get_performance_summary()
        assert summary["total_operations"] == 0
        assert summary["overall_cache_hit_rate"] == 0.0
        assert summary["pattern_usage"] == {}

    def test_improvement_zero_without_cache_hits(self) -> None:
        monitor = DynamicProgrammingMonitor(cache_time_savings_factor=0.9)
        monitor.record_operation("op", 10.0, cache_hit=False)
        assert monitor.get_performance_summary()["op"][
            "performance_improvement"
        ] == 0.0

    def test_improvement_positive_with_cache_hits(self) -> None:
        monitor = DynamicProgrammingMonitor(cache_time_savings_factor=0.9)
        monitor.record_operation("op", 100.0, cache_hit=False)
        monitor.record_operation("op", 100.0, cache_hit=False)
        monitor.record_operation("op", 1.0, cache_hit=True)
        improvement = monitor.get_performance_summary()["op"][
            "performance_improvement"
        ]
        assert improvement > 0.0

    def test_get_top_performers_sorted_and_limited(self) -> None:
        monitor = DynamicProgrammingMonitor(cache_time_savings_factor=0.9)
        for _ in range(5):
            monitor.record_operation("fast", 100.0, cache_hit=False)
            monitor.record_operation("fast", 1.0, cache_hit=True)
        monitor.record_operation("slow", 5.0, cache_hit=False)
        top = monitor.get_top_performers(limit=1)
        assert len(top) == 1
        assert top[0]["operation"] == "fast"

    def test_reset_metrics(self) -> None:
        monitor = DynamicProgrammingMonitor()
        monitor.record_operation("op", 5.0, pattern_type="cache")
        monitor.reset_metrics()
        summary = monitor.get_performance_summary()
        assert summary["total_operations"] == 0
        assert summary["pattern_usage"] == {}

    def test_error_tracking_in_summary(self) -> None:
        monitor = DynamicProgrammingMonitor()
        monitor.record_operation("op", 5.0, error=True)
        assert monitor.get_performance_summary()["op"]["error_rate"] == 100.0


class TestSmartCachingMiddleware:
    def test_get_cache_creates_and_reuses(self) -> None:
        middleware = SmartCachingMiddleware(default_cache_size=64)
        first = middleware.get_cache("units")
        second = middleware.get_cache("units")
        assert first is second
        assert middleware.cache_configs["units"]["size"] == 64

    def test_get_cache_custom_configuration(self) -> None:
        middleware = SmartCachingMiddleware(default_cache_size=64)
        middleware.get_cache(
            "custom", size=16, ttl_seconds=30, policy=CachePolicy.FIFO
        )
        config = middleware.cache_configs["custom"]
        assert config == {
            "size": 16,
            "ttl_seconds": 30,
            "policy": CachePolicy.FIFO,
        }

    def test_cached_call_caches_results(self) -> None:
        middleware = SmartCachingMiddleware()
        calls: list[int] = []

        def compute(value: int) -> int:
            calls.append(value)
            return value * 2

        assert middleware.cached_call("math", compute, 21) == 42
        assert middleware.cached_call("math", compute, 21) == 42
        assert calls == [21]

    def test_cached_call_cache_key_overrides_generated_key(self) -> None:
        middleware = SmartCachingMiddleware()
        calls: list[int] = []

        def compute(value: int) -> int:
            calls.append(value)
            return value

        middleware.cached_call("math", compute, 1, cache_key="fixed")  # type: ignore[call-arg]
        middleware.cached_call("math", compute, 2, cache_key="fixed")  # type: ignore[call-arg]
        assert calls == [1]
        assert middleware.get_cache("math").size() == 1

    def test_cached_call_records_errors_and_reraises(self) -> None:
        middleware = SmartCachingMiddleware()

        def explode(_value: int) -> int:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            middleware.cached_call("math", explode, 1)
        summary = middleware.monitor.get_performance_summary()
        assert summary["math"]["error_rate"] == 100.0

    def test_invalidate_cache(self) -> None:
        middleware = SmartCachingMiddleware()
        cache = middleware.get_cache("units")
        cache.put("k", "v")
        middleware.invalidate_cache("units")
        assert cache.size() == 0

    def test_invalidate_missing_cache_is_noop(self) -> None:
        middleware = SmartCachingMiddleware()
        middleware.invalidate_cache("does-not-exist")

    def test_invalidate_all_caches(self) -> None:
        middleware = SmartCachingMiddleware()
        first = middleware.get_cache("one")
        second = middleware.get_cache("two")
        first.put("k", "v")
        second.put("k", "v")
        middleware.invalidate_all_caches()
        assert first.size() == 0
        assert second.size() == 0

    def test_get_cache_statistics(self) -> None:
        middleware = SmartCachingMiddleware(default_cache_size=10)
        cache = middleware.get_cache("units")
        cache.put("k", "v")
        stats = middleware.get_cache_statistics()
        units = stats["units"]
        assert units["current_size"] == 1
        assert units["utilization_percentage"] == pytest.approx(10.0)
        assert units["configuration"]["size"] == 10
        assert "monitor_summary" in stats

    def test_optimize_cache_sizes_disabled(self) -> None:
        middleware = SmartCachingMiddleware(adaptive_sizing=False)
        assert middleware.optimize_cache_sizes() == {}

    def test_optimize_cache_sizes_reduces_on_low_hit_rate(self) -> None:
        middleware = SmartCachingMiddleware(default_cache_size=100)
        values = iter(range(20))

        def next_value() -> int:
            return next(values)

        for i in range(20):
            middleware.cached_call(
                "units", next_value, cache_key=f"key-{i}"  # type: ignore[call-arg]
            )
        optimizations = middleware.optimize_cache_sizes()
        assert optimizations["units"] == 80

    def test_optimize_cache_sizes_increases_on_high_hit_rate(self) -> None:
        middleware = SmartCachingMiddleware(default_cache_size=100)

        def constant_value() -> str:
            return "value"

        for _ in range(20):
            middleware.cached_call(
                "units", constant_value, cache_key="stable"  # type: ignore[call-arg]
            )
        optimizations = middleware.optimize_cache_sizes()
        assert optimizations["units"] == 120


class TestPerformanceTrackingDecorator:
    def test_records_success_and_error(self) -> None:
        monitor = DynamicProgrammingMonitor()

        @performance_tracking("tracked_op", monitor=monitor)
        def work(value: int) -> int:
            if value < 0:
                raise RuntimeError("negative")
            return value * 2

        assert work(2) == 4
        with pytest.raises(RuntimeError, match="negative"):
            work(-1)
        summary = monitor.get_performance_summary()
        assert summary["tracked_op"]["total_requests"] == 2
        assert summary["tracked_op"]["error_rate"] == pytest.approx(50.0)
        assert (
            summary["pattern_usage"]["dynamic_programming"] == 2
        )

    def test_default_name_uses_function_name(self) -> None:
        monitor = DynamicProgrammingMonitor()

        @performance_tracking(monitor=monitor)
        def my_operation() -> None:
            return None

        my_operation()
        assert "my_operation" in monitor.get_performance_summary()


class TestSmartCacheDecorator:
    def test_caches_decorated_function(self) -> None:
        middleware = SmartCachingMiddleware()
        calls: list[int] = []

        @smart_cache("deco", size=8, middleware=middleware)
        def compute(value: int) -> int:
            calls.append(value)
            return value + 1

        assert compute(1) == 2
        assert compute(1) == 2
        assert calls == [1]
        assert middleware.cache_configs["deco"]["size"] == 8

    def test_default_middleware_used_without_injection(self) -> None:
        @smart_cache("global-deco")
        def compute(value: int) -> int:
            return value + 1

        reset_all_metrics()
        assert compute(5) == 6
        assert get_global_cache_middleware().get_cache("global-deco").size() == 1
        reset_all_metrics()


class TestHybridOptimization:
    def test_combines_caching_and_tracking(self) -> None:
        calls: list[int] = []

        @hybrid_optimization("hybrid", "hybrid_op", cache_size=8)
        def compute(value: int) -> int:
            calls.append(value)
            return value * 3

        assert compute(2) == 6
        assert compute(2) == 6
        assert calls == [2]


class TestGlobalAccessors:
    def test_global_instances_are_returned(self) -> None:
        assert isinstance(get_global_monitor(), DynamicProgrammingMonitor)
        assert isinstance(get_global_cache_middleware(), SmartCachingMiddleware)

    def test_generate_performance_report_keys(self) -> None:
        reset_all_metrics()
        report = generate_performance_report()
        assert set(report) == {
            "monitoring_summary",
            "cache_statistics",
            "top_performers",
            "optimization_recommendations",
            "timestamp",
        }

    def test_reset_all_metrics_clears_globals(self) -> None:
        get_global_monitor().record_operation("temp-op", 5.0)
        get_global_cache_middleware().get_cache("temp-cache").put("k", "v")
        reset_all_metrics()
        assert get_global_monitor().get_performance_summary()[
            "total_operations"
        ] == 0
        assert get_global_cache_middleware().get_cache("temp-cache").size() == 0
