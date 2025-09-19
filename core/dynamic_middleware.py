"""Performance monitoring and caching middleware for dynamic programming patterns.

This module provides comprehensive monitoring, metrics collection, and intelligent
caching middleware that can be applied across all dynamic programming implementations
in the PhenomenalLayout system.
"""

from __future__ import annotations

import functools
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional, TypeVar

from core.dynamic_programming import (
    CachePolicy,
    SmartCache,
)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class MiddlewareMetrics:
    """Comprehensive metrics for middleware operations."""

    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    error_count: int = 0
    performance_improvements: dict[str, float] = field(default_factory=dict)

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.cache_hits / self.total_requests) * 100

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average duration."""
        if self.total_requests == 0:
            return 0.0
        return self.total_duration_ms / self.total_requests

    @property
    def error_rate(self) -> float:
        """Calculate error rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.error_count / self.total_requests) * 100

    def record_request(
        self, duration_ms: float, cache_hit: bool = False, error: bool = False
    ) -> None:
        """Record a single request's metrics."""
        self.total_requests += 1
        self.total_duration_ms += duration_ms

        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

        if error:
            self.error_count += 1

        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)


class DynamicProgrammingMonitor:
    """Monitor performance improvements from dynamic programming patterns."""

    def __init__(self, cache_time_savings_factor: float = 0.9):
        self.cache_time_savings_factor = cache_time_savings_factor
        self.metrics: dict[str, MiddlewareMetrics] = defaultdict(MiddlewareMetrics)
        self.pattern_usage: dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()

    def record_operation(
        self,
        operation: str,
        duration_ms: float,
        cache_hit: bool = False,
        error: bool = False,
        pattern_type: Optional[str] = None,
    ) -> None:
        """Record operation metrics."""
        with self._lock:
            self.metrics[operation].record_request(duration_ms, cache_hit, error)

            if pattern_type:
                self.pattern_usage[pattern_type] += 1

    def get_performance_summary(self) -> dict[str, Any]:
        """Generate comprehensive performance summary."""
        with self._lock:
            summary = {}

            for operation, metrics in self.metrics.items():
                summary[operation] = {
                    "total_requests": metrics.total_requests,
                    "cache_hit_rate": metrics.cache_hit_rate,
                    "avg_duration_ms": metrics.avg_duration_ms,
                    "min_duration_ms": metrics.min_duration_ms
                    if metrics.min_duration_ms != float("inf")
                    else 0,
                    "max_duration_ms": metrics.max_duration_ms,
                    "error_rate": metrics.error_rate,
                    "performance_improvement": self._calculate_improvement(
                        operation, metrics
                    ),
                }

            summary["pattern_usage"] = dict(self.pattern_usage)
            summary["total_operations"] = sum(
                m.total_requests for m in self.metrics.values()
            )
            summary["overall_cache_hit_rate"] = self._calculate_overall_cache_rate()

            return summary

    def _calculate_improvement(
        self, operation: str, metrics: MiddlewareMetrics
    ) -> float:
        """Calculate estimated performance improvement."""
        if metrics.cache_hits == 0:
            return 0.0

        # Estimate improvement based on cache hits (assume 90% time savings on cache hits)
        cache_time_saved = metrics.cache_hits * (
            metrics.avg_duration_ms * self.cache_time_savings_factor
        )
        total_time = metrics.total_duration_ms

        if total_time > 0:
            return (cache_time_saved / total_time) * 100
        return 0.0

    def _calculate_overall_cache_rate(self) -> float:
        """Calculate overall cache hit rate across all operations."""
        total_hits = sum(m.cache_hits for m in self.metrics.values())
        total_requests = sum(m.total_requests for m in self.metrics.values())

        if total_requests == 0:
            return 0.0
        return (total_hits / total_requests) * 100

    def get_top_performers(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get top performing operations by improvement."""
        performers = []

        with self._lock:
            for operation, metrics in self.metrics.items():
                improvement = self._calculate_improvement(operation, metrics)
                performers.append(
                    {
                        "operation": operation,
                        "improvement_percentage": improvement,
                        "cache_hit_rate": metrics.cache_hit_rate,
                        "total_requests": metrics.total_requests,
                        "avg_duration_ms": metrics.avg_duration_ms,
                    }
                )

        performers.sort(key=lambda x: x["improvement_percentage"], reverse=True)
        return performers[:limit]

    def reset_metrics(self) -> None:
        """Reset all collected metrics."""
        with self._lock:
            self.metrics.clear()
            self.pattern_usage.clear()


class SmartCachingMiddleware:
    """Intelligent caching middleware with adaptive policies."""

    def __init__(
        self,
        default_cache_size: int = 256,
        default_ttl_seconds: Optional[float] = None,
        adaptive_sizing: bool = True,
    ):
        self.default_cache_size = default_cache_size
        self.default_ttl_seconds = default_ttl_seconds
        self.adaptive_sizing = adaptive_sizing

        # Cache registry
        self.caches: dict[str, SmartCache] = {}
        self.cache_configs: dict[str, dict[str, Any]] = {}

        # Performance tracking
        self.monitor = DynamicProgrammingMonitor()

        # Thread safety
        self._lock = threading.RLock()

    def get_cache(
        self,
        name: str,
        size: Optional[int] = None,
        ttl_seconds: Optional[float] = None,
        policy: CachePolicy = CachePolicy.LRU,
    ) -> SmartCache:
        """Get or create a cache with specified configuration."""
        with self._lock:
            if name not in self.caches:
                cache_size = size or self.default_cache_size
                cache_ttl = ttl_seconds or self.default_ttl_seconds

                self.caches[name] = SmartCache(
                    max_size=cache_size, policy=policy, ttl_seconds=cache_ttl
                )

                self.cache_configs[name] = {
                    "size": cache_size,
                    "ttl_seconds": cache_ttl,
                    "policy": policy,
                }

            return self.caches[name]

    def cached_call(
        self,
        cache_name: str,
        func: Callable,
        *args,
        cache_key: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Execute function with caching."""
        cache = self.get_cache(cache_name)

        # Generate cache key
        if cache_key is None:
            cache_key = self._generate_cache_key(func.__name__, args, kwargs)

        start_time = time.perf_counter()

        # Check cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.monitor.record_operation(cache_name, duration_ms, cache_hit=True)
            return cached_result

        # Execute function
        try:
            result = func(*args, **kwargs)
            cache.put(cache_key, result)

            duration_ms = (time.perf_counter() - start_time) * 1000
            self.monitor.record_operation(cache_name, duration_ms, cache_hit=False)

            return result

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.monitor.record_operation(
                cache_name, duration_ms, cache_hit=False, error=True
            )
            raise e

    def _generate_cache_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """Generate cache key from function arguments."""
        import hashlib

        key_data = f"{func_name}:{args}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()[:16]

    def invalidate_cache(self, cache_name: str) -> None:
        """Invalidate specific cache."""
        with self._lock:
            if cache_name in self.caches:
                self.caches[cache_name].clear()

    def invalidate_all_caches(self) -> None:
        """Invalidate all caches."""
        with self._lock:
            for cache in self.caches.values():
                cache.clear()

    def get_cache_statistics(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        with self._lock:
            stats = {}

            for name, cache in self.caches.items():
                config = self.cache_configs.get(name, {})
                cache_stats = cache.stats()

                stats[name] = {
                    "configuration": config,
                    "current_size": cache.size(),
                    "cache_stats": cache_stats,
                    "utilization_percentage": (cache.size() / config.get("size", 1))
                    * 100,
                }

            stats["monitor_summary"] = self.monitor.get_performance_summary()
            return stats

    def optimize_cache_sizes(self) -> dict[str, int]:
        """Optimize cache sizes based on usage patterns."""
        if not self.adaptive_sizing:
            return {}

        optimizations = {}
        summary = self.monitor.get_performance_summary()

        with self._lock:
            for cache_name, cache in self.caches.items():
                if cache_name in summary:
                    metrics = summary[cache_name]
                    current_size = self.cache_configs[cache_name]["size"]

                    # Simple optimization heuristic
                    hit_rate = metrics["cache_hit_rate"]
                    if hit_rate < 50 and current_size > 64:
                        # Low hit rate, reduce size
                        new_size = max(64, int(current_size * 0.8))
                        optimizations[cache_name] = new_size
                    elif hit_rate > 90 and current_size < 1024:
                        # High hit rate, increase size
                        new_size = min(1024, int(current_size * 1.2))
                        optimizations[cache_name] = new_size

        return optimizations


def performance_tracking(
    operation_name: Optional[str] = None,
    cache_name: Optional[str] = None,
    monitor: Optional[DynamicProgrammingMonitor] = None,
) -> Callable[[F], F]:
    """Decorator for performance tracking."""

    def decorator(func: F) -> F:
        name = operation_name or func.__name__
        global_monitor = monitor or _global_monitor

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            error_occurred = False

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error_occurred = True
                raise e
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                global_monitor.record_operation(
                    name,
                    duration_ms,
                    error=error_occurred,
                    pattern_type="dynamic_programming",
                )

        return wrapper

    return decorator


def smart_cache(
    cache_name: str,
    size: int = 256,
    ttl_seconds: Optional[float] = None,
    policy: CachePolicy = CachePolicy.LRU,
    middleware: Optional[SmartCachingMiddleware] = None,
) -> Callable[[F], F]:
    """Decorator for smart caching."""

    def decorator(func: F) -> F:
        cache_middleware = middleware or _global_cache_middleware

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return cache_middleware.cached_call(cache_name, func, *args, **kwargs)

        # Ensure cache exists with proper configuration
        cache_middleware.get_cache(cache_name, size, ttl_seconds, policy)

        return wrapper

    return decorator


def hybrid_optimization(
    cache_name: str,
    operation_name: Optional[str] = None,
    cache_size: int = 256,
    ttl_seconds: Optional[float] = None,
) -> Callable[[F], F]:
    """Combined decorator for caching and performance monitoring."""

    def decorator(func: F) -> F:
        # Apply both decorators
        cached_func = smart_cache(cache_name, cache_size, ttl_seconds)(func)
        monitored_func = performance_tracking(operation_name)(cached_func)
        return monitored_func

    return decorator


# Global instances
_global_monitor = DynamicProgrammingMonitor()
_global_cache_middleware = SmartCachingMiddleware()


def get_global_monitor() -> DynamicProgrammingMonitor:
    """Get global performance monitor instance."""
    return _global_monitor


def get_global_cache_middleware() -> SmartCachingMiddleware:
    """Get global cache middleware instance."""
    return _global_cache_middleware


def generate_performance_report() -> dict[str, Any]:
    """Generate comprehensive performance report."""
    return {
        "monitoring_summary": _global_monitor.get_performance_summary(),
        "cache_statistics": _global_cache_middleware.get_cache_statistics(),
        "top_performers": _global_monitor.get_top_performers(),
        "optimization_recommendations": _global_cache_middleware.optimize_cache_sizes(),
        "timestamp": time.time(),
    }


def reset_all_metrics() -> None:
    """Reset all performance metrics and caches."""
    _global_monitor.reset_metrics()
    _global_cache_middleware.invalidate_all_caches()


# Export for use in other modules
__all__ = [
    "DynamicProgrammingMonitor",
    "SmartCachingMiddleware",
    "MiddlewareMetrics",
    "performance_tracking",
    "smart_cache",
    "hybrid_optimization",
    "get_global_monitor",
    "get_global_cache_middleware",
    "generate_performance_report",
    "reset_all_metrics",
]
