"""Core dynamic programming patterns and registries for PhenomenalLayout.

This module implements the fundamental dynamic programming infrastructure
to replace static if-else conditional chains with data-driven decision systems.
It provides generic registry patterns, factory systems, and caching mechanisms
that can be used across the codebase for performance optimization.
"""

from __future__ import annotations

import functools
import hashlib
import heapq
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Optional, TypeVar, Union

# Type variables for generic implementations
T = TypeVar("T")
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class CachePolicy(Enum):
    """Cache eviction policies for dynamic programming systems."""

    LRU = "lru"  # Least Recently Used
    TTL = "ttl"  # Time To Live
    LFU = "lfu"  # Least Frequently Used
    FIFO = "fifo"  # First In, First Out


@dataclass
class PerformanceMetrics:
    """Performance metrics for dynamic programming operations."""

    operation_name: str
    total_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    total_duration_ms: float = 0.0

    # Separate tracking for cached vs uncached operations
    cache_hit_duration_ms: float = 0.0
    cache_miss_duration_ms: float = 0.0

    # Configurable cache time savings ratio (default: 90% savings)
    cache_time_savings_ratio: float = 0.9

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        if self.total_calls == 0:
            return 0.0
        return (self.cache_hits / self.total_calls) * 100

    @property
    def performance_improvement(self) -> float:
        """Calculate performance improvement from caching.

        Uses measured time differences between cached and uncached operations
        when available, otherwise falls back to configured cache_time_savings_ratio.
        Returns improvement as a percentage.
        """
        if self.cache_hits == 0 or self.total_duration_ms <= 0:
            return 0.0

        # Try to compute actual time savings from measurements
        time_savings_ratio = self._compute_time_savings_ratio()

        # Calculate average uncached duration for benefit estimation
        if self.cache_misses > 0:
            avg_uncached_duration = self.cache_miss_duration_ms / self.cache_misses
        else:
            avg_uncached_duration = self.avg_duration_ms

        # Estimate time that would have been spent without caching
        time_without_cache = self.cache_hits * avg_uncached_duration
        time_with_cache = self.cache_hit_duration_ms

        # Calculate actual benefit
        if time_without_cache > 0:
            actual_savings = time_without_cache - time_with_cache
            return (actual_savings / self.total_duration_ms) * 100

        # Fallback to ratio-based estimation
        cache_benefit = self.cache_hits * (avg_uncached_duration * time_savings_ratio)
        return (cache_benefit / self.total_duration_ms) * 100

    def _compute_time_savings_ratio(self) -> float:
        """Compute actual time savings ratio from measurements.

        Returns the configured ratio if insufficient data is available.
        Guards against division by zero and out-of-range ratios.
        """
        if self.cache_hits == 0 or self.cache_misses == 0:
            # Not enough data, use configured ratio
            return max(0.0, min(1.0, self.cache_time_savings_ratio))

        avg_cached_duration = self.cache_hit_duration_ms / self.cache_hits
        avg_uncached_duration = self.cache_miss_duration_ms / self.cache_misses

        if avg_uncached_duration <= 0:
            # Guard against division by zero
            return max(0.0, min(1.0, self.cache_time_savings_ratio))

        # Calculate actual savings ratio
        measured_ratio = (
            avg_uncached_duration - avg_cached_duration
        ) / avg_uncached_duration

        # Clamp to valid range [0.0, 1.0] and ensure sensible values
        return max(0.0, min(1.0, measured_ratio))

    def record_operation(self, duration_ms: float, cache_hit: bool = False) -> None:
        """Record a single operation's metrics with separate tracking for cached vs uncached."""
        self.total_calls += 1
        self.total_duration_ms += duration_ms

        if cache_hit:
            self.cache_hits += 1
            self.cache_hit_duration_ms += duration_ms
        else:
            self.cache_misses += 1
            self.cache_miss_duration_ms += duration_ms

        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.avg_duration_ms = self.total_duration_ms / self.total_calls


class CacheEntry(Generic[V]):
    """Generic cache entry with metadata."""

    def __init__(self, value: V, timestamp: float = None, access_count: int = 0):
        self.value = value
        self.timestamp = timestamp or time.time()
        self.access_count = access_count
        self.last_accessed = self.timestamp

    def access(self) -> V:
        """Access the cached value and update metadata."""
        self.access_count += 1
        self.last_accessed = time.time()
        return self.value


class SmartCache(Generic[K, V]):
    """Intelligent caching system with multiple eviction policies.

    Uses efficient auxiliary structures:
    - LFU: Min-heap for O(log n) eviction
    - FIFO: OrderedDict for O(1) eviction
    - LRU: List for O(1) eviction (existing)
    """

    def __init__(
        self,
        max_size: int = 256,
        policy: CachePolicy = CachePolicy.LRU,
        ttl_seconds: Optional[float] = None,
    ):
        self.max_size = max_size
        self.policy = policy
        self.ttl_seconds = ttl_seconds
        self._cache: dict[K, CacheEntry[V]] = {}
        self._lock = threading.RLock()

        # Policy-specific auxiliary structures
        from collections import deque

        self._access_order: deque[K] = deque()  # For LRU

        # For LFU: min-heap of (access_count, insertion_order, key)
        self._lfu_heap: list[tuple[int, int, K]] = []
        self._lfu_insertion_counter = 0  # To break ties in heap
        self._lfu_stale_keys: set[K] = set()  # Track stale heap entries

        # For FIFO: OrderedDict for O(1) insert/delete
        self._fifo_order: OrderedDict[K, None] = OrderedDict()

    def get(self, key: K) -> Optional[V]:
        """Get value from cache with policy-aware access tracking."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # Check TTL expiration
            if self.ttl_seconds and (time.time() - entry.timestamp) > self.ttl_seconds:
                self._remove_key(key)
                return None

            # Update access patterns based on policy
            if self.policy == CachePolicy.LRU:
                if key in self._access_order:
                    self._access_order.remove(key)
                self._access_order.append(key)
                return entry.access()
            elif self.policy == CachePolicy.LFU:
                # LFU: Update heap with new access count
                # First increment the actual entry's access count
                value = entry.access()  # This increments access_count
                new_count = entry.access_count
                # Mark old entry as stale and push updated entry
                self._lfu_stale_keys.add(key)
                heapq.heappush(
                    self._lfu_heap, (new_count, self._lfu_insertion_counter, key)
                )
                self._lfu_insertion_counter += 1
                return value
            else:
                return entry.access()

    def put(self, key: K, value: V) -> None:
        """Store value in cache with intelligent eviction."""
        with self._lock:
            # Check if we need to evict
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._evict_one()

            # Store the entry
            self._cache[key] = CacheEntry(value)

            # Update auxiliary structures based on policy
            if self.policy == CachePolicy.LRU:
                if key in self._access_order:
                    self._access_order.remove(key)
                self._access_order.append(key)
            elif self.policy == CachePolicy.LFU:
                # LFU: Add to heap with access count 0 (will be 1 after first access)
                heapq.heappush(self._lfu_heap, (0, self._lfu_insertion_counter, key))
                self._lfu_insertion_counter += 1
            elif self.policy == CachePolicy.FIFO:
                # FIFO: Add to OrderedDict (removing if exists to maintain order)
                if key in self._fifo_order:
                    del self._fifo_order[key]
                self._fifo_order[key] = None

    def _remove_key(self, key: K) -> None:
        """Remove key from cache and all auxiliary structures."""
        if key not in self._cache:
            return

        del self._cache[key]

        # Clean up auxiliary structures
        if key in self._access_order:
            self._access_order.remove(key)

        if key in self._fifo_order:
            del self._fifo_order[key]

        # For LFU heap, just mark as stale (cleaned up during eviction)
        self._lfu_stale_keys.add(key)

    def _evict_one(self) -> None:
        """Evict one entry based on the configured policy with O(log n) or O(1) complexity."""
        if not self._cache:
            return

        if self.policy == CachePolicy.LRU:
            # O(1) eviction
            if self._access_order:
                oldest_key = self._access_order.popleft()
                del self._cache[oldest_key]

        elif self.policy == CachePolicy.LFU:
            # O(log n) eviction using min-heap
            while self._lfu_heap:
                access_count, insertion_order, key = heapq.heappop(self._lfu_heap)

                # Skip stale entries
                if key in self._lfu_stale_keys:
                    self._lfu_stale_keys.discard(key)
                    continue

                # Verify key still exists and has correct access count
                if key in self._cache and self._cache[key].access_count == access_count:
                    del self._cache[key]
                    self._lfu_stale_keys.discard(key)  # Clean up just in case
                    break

        elif self.policy == CachePolicy.FIFO:
            # O(1) eviction using OrderedDict
            if self._fifo_order:
                oldest_key, _ = self._fifo_order.popitem(last=False)
                if oldest_key in self._cache:
                    del self._cache[oldest_key]

    def clear(self) -> None:
        """Clear all cached entries and auxiliary structures."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self._lfu_heap.clear()
            self._lfu_stale_keys.clear()
            self._fifo_order.clear()
            self._lfu_insertion_counter = 0

    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "policy": self.policy.value,
                "ttl_seconds": self.ttl_seconds,
                "hit_rate": 0.0,  # Would need to track separately
            }


class DynamicRegistry(Generic[T]):
    """Generic registry with dynamic loading and intelligent caching."""

    def __init__(
        self,
        cache_size: int = 256,
        cache_policy: CachePolicy = CachePolicy.LRU,
        ttl_seconds: Optional[float] = None,
    ):
        self._registry: dict[str, Callable[..., T]] = {}
        self._cache: SmartCache[tuple, T] = SmartCache(
            max_size=cache_size, policy=cache_policy, ttl_seconds=ttl_seconds
        )
        self._metrics: dict[str, PerformanceMetrics] = defaultdict(
            lambda: PerformanceMetrics("unknown")
        )
        self._lock = threading.RLock()

    def register(self, key: str, factory: Callable[..., T]) -> None:
        """Register a factory function for dynamic creation."""
        with self._lock:
            self._registry[key] = factory
            if key not in self._metrics:
                self._metrics[key] = PerformanceMetrics(key)

    def get(self, key: str, *args, **kwargs) -> Optional[T]:
        """Get or create instance with intelligent caching."""
        # Create cache key from arguments
        cache_key = self._create_cache_key(key, args, kwargs)

        # Try cache first
        start_time = time.perf_counter()
        cached_result = self._cache.get(cache_key)

        if cached_result is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._metrics[key].record_operation(duration_ms, cache_hit=True)
            return cached_result

        # Create new instance
        with self._lock:
            if key not in self._registry:
                return None

            try:
                result = self._registry[key](*args, **kwargs)
                self._cache.put(cache_key, result)

                duration_ms = (time.perf_counter() - start_time) * 1000
                self._metrics[key].record_operation(duration_ms, cache_hit=False)

                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._metrics[key].record_operation(duration_ms, cache_hit=False)
                raise e

    def _create_cache_key(self, key: str, args: tuple, kwargs: dict) -> tuple:
        """Create a hashable cache key from arguments."""

        def _normalize_value(value):
            """Recursively normalize unhashable values into hashable representations."""
            try:
                # Try to hash the value first - if it works, return as-is
                hash(value)
                return value
            except TypeError:
                # Value is unhashable, need to normalize it
                if isinstance(value, list):
                    return tuple(_normalize_value(item) for item in value)
                elif isinstance(value, set):
                    # Convert to sorted tuple for deterministic ordering
                    try:
                        return tuple(sorted(_normalize_value(item) for item in value))
                    except TypeError:
                        # Items might not be sortable, fall back to repr-based sorting
                        return tuple(
                            sorted((_normalize_value(item) for item in value), key=str)
                        )
                elif isinstance(value, dict):
                    # Convert to tuple of sorted (key, value) pairs with recursive normalization
                    normalized_items = []
                    for k, v in sorted(value.items()):
                        normalized_items.append(
                            (_normalize_value(k), _normalize_value(v))
                        )
                    return tuple(normalized_items)
                elif hasattr(value, "__dataclass_fields__"):
                    # Handle dataclass objects
                    import dataclasses

                    normalized_fields = []
                    for field_obj in sorted(
                        dataclasses.fields(value), key=lambda f: f.name
                    ):
                        field_name = field_obj.name
                        field_value = getattr(value, field_name)
                        normalized_fields.append(
                            (field_name, _normalize_value(field_value))
                        )
                    return (value.__class__.__name__, tuple(normalized_fields))
                elif hasattr(value, "__dict__"):
                    # Handle regular objects with __dict__
                    normalized_attrs = []
                    for k, v in sorted(value.__dict__.items()):
                        normalized_attrs.append((k, _normalize_value(v)))
                    return (value.__class__.__name__, tuple(normalized_attrs))
                elif hasattr(value, "_name") and hasattr(value, "_value"):
                    # Handle enum objects
                    return (value.__class__.__name__, value._name, value._value)
                elif hasattr(value, "name") and hasattr(value, "value"):
                    # Handle enum objects (alternative pattern)
                    return (value.__class__.__name__, value.name, value.value)
                else:
                    # For any other unhashable type, use repr as stable string representation
                    return repr(value)

        # Normalize args tuple recursively
        normalized_args = tuple(_normalize_value(arg) for arg in args)

        # Normalize kwargs dict recursively
        normalized_kwargs_items = []
        for k, v in sorted(kwargs.items()):
            normalized_kwargs_items.append((_normalize_value(k), _normalize_value(v)))
        normalized_kwargs = tuple(normalized_kwargs_items)

        return (key, normalized_args, normalized_kwargs)

    def clear_cache(self) -> None:
        """Clear all cached instances."""
        self._cache.clear()

    def get_metrics(
        self, key: Optional[str] = None
    ) -> Union[PerformanceMetrics, dict[str, PerformanceMetrics]]:
        """Get performance metrics for a specific key or all keys."""
        if key:
            return self._metrics.get(key, PerformanceMetrics(key))
        return dict(self._metrics)

    def get_registered_keys(self) -> list[str]:
        """Get list of all registered factory keys."""
        with self._lock:
            return list(self._registry.keys())


class DecisionTreeNode(Generic[T]):
    """Node in a dynamic decision tree for pattern matching."""

    def __init__(self, condition: Callable[[Any], bool], result: Optional[T] = None):
        self.condition = condition
        self.result = result
        self.children: list[DecisionTreeNode[T]] = []
        self.cache: SmartCache[str, T] = SmartCache(max_size=64)

    def add_child(self, child: DecisionTreeNode[T]) -> None:
        """Add a child node to the decision tree."""
        self.children.append(child)

    def evaluate(self, context: Any) -> Optional[T]:
        """Evaluate the decision tree with caching."""
        # Create cache key from context
        context_key = self._create_context_key(context)

        # Check cache first
        cached_result = self.cache.get(context_key)
        if cached_result is not None:
            return cached_result

        # Evaluate condition
        if self.condition(context):
            if self.result is not None:
                self.cache.put(context_key, self.result)
                return self.result

            # Check children
            for child in self.children:
                child_result = child.evaluate(context)
                if child_result is not None:
                    self.cache.put(context_key, child_result)
                    return child_result

        return None

    def _create_context_key(self, context: Any) -> str:
        """Create a cache key from context object."""
        if hasattr(context, "__dict__"):
            # Hash object attributes
            context_str = str(sorted(context.__dict__.items()))
        else:
            context_str = str(context)

        import hashlib

        return hashlib.md5(context_str.encode(), usedforsecurity=False).hexdigest()[:16]


class StrategyPattern(ABC, Generic[T]):
    """Abstract base for strategy pattern implementation."""

    @abstractmethod
    def execute(self, context: Any) -> T:
        """Execute the strategy with given context."""
        pass

    @abstractmethod
    def can_handle(self, context: Any) -> bool:
        """Check if this strategy can handle the given context."""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Get strategy priority (higher = more preferred)."""
        pass


class StrategyRegistry(Generic[T]):
    """Registry for strategy pattern with dynamic selection."""

    def __init__(self):
        self._strategies: list[StrategyPattern[T]] = []
        self._cache: SmartCache[str, StrategyPattern[T]] = SmartCache(max_size=128)
        self._metrics = PerformanceMetrics("strategy_selection")

    def register(self, strategy: StrategyPattern[T]) -> None:
        """Register a strategy."""
        self._strategies.append(strategy)
        # Sort by priority (highest first)
        self._strategies.sort(key=lambda s: s.priority, reverse=True)

    def select_strategy(self, context: Any) -> Optional[StrategyPattern[T]]:
        """Select the best strategy for the given context."""
        start_time = time.perf_counter()

        # Create cache key
        context_key = self._create_context_key(context)

        # Check cache
        cached_strategy = self._cache.get(context_key)
        if cached_strategy is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._metrics.record_operation(duration_ms, cache_hit=True)
            return cached_strategy

        # Find best strategy
        for strategy in self._strategies:
            if strategy.can_handle(context):
                self._cache.put(context_key, strategy)
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._metrics.record_operation(duration_ms, cache_hit=False)
                return strategy

        duration_ms = (time.perf_counter() - start_time) * 1000
        self._metrics.record_operation(duration_ms, cache_hit=False)
        return None

    def execute(self, context: Any) -> Optional[T]:
        """Select and execute the best strategy."""
        strategy = self.select_strategy(context)
        if strategy:
            return strategy.execute(context)
        return None

    def _create_context_key(self, context: Any) -> str:
        """Create cache key from context."""
        if hasattr(context, "__dict__"):
            context_str = str(sorted(context.__dict__.items()))
        else:
            context_str = str(context)

        return hashlib.md5(context_str.encode(), usedforsecurity=False).hexdigest()[:16]

    def get_metrics(self) -> PerformanceMetrics:
        """Get strategy selection performance metrics."""
        return self._metrics

    @property
    def strategy_count(self) -> int:
        """Get the number of registered strategies.

        Returns:
            int: The total number of strategies currently registered in this registry.

        Note:
            This property provides public access to the strategy count without
            exposing the internal _strategies list implementation.
        """
        return len(self._strategies)

    def __len__(self) -> int:
        """Return the number of registered strategies.

        This enables using len(strategy_registry) for getting the strategy count.

        Returns:
            int: The total number of strategies currently registered.
        """
        return len(self._strategies)


# Decorators for dynamic programming patterns


def memoize(cache_size: int = 128, ttl_seconds: Optional[float] = None):
    """Memoization decorator with configurable cache policies."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: SmartCache[tuple, T] = SmartCache(
            max_size=cache_size, policy=CachePolicy.LRU, ttl_seconds=ttl_seconds
        )
        metrics = PerformanceMetrics(func.__name__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            def _normalize_value(value):
                """Recursively normalize unhashable values into hashable representations."""
                try:
                    # Try to hash the value first - if it works, return as-is
                    hash(value)
                    return value
                except TypeError:
                    # Value is unhashable, need to normalize it
                    if isinstance(value, list):
                        return tuple(_normalize_value(item) for item in value)
                    elif isinstance(value, set):
                        # Convert to sorted tuple for deterministic ordering
                        try:
                            return tuple(
                                sorted(_normalize_value(item) for item in value)
                            )
                        except TypeError:
                            # Items might not be sortable, fall back to repr-based sorting
                            return tuple(
                                sorted(
                                    (_normalize_value(item) for item in value), key=str
                                )
                            )
                    elif isinstance(value, dict):
                        # Convert to tuple of sorted (key, value) pairs with recursive normalization
                        normalized_items = []
                        for k, v in sorted(value.items()):
                            normalized_items.append(
                                (_normalize_value(k), _normalize_value(v))
                            )
                        return tuple(normalized_items)
                    elif hasattr(value, "__dataclass_fields__"):
                        # Handle dataclass objects
                        import dataclasses

                        normalized_fields = []
                        for field_obj in sorted(
                            dataclasses.fields(value), key=lambda f: f.name
                        ):
                            field_name = field_obj.name
                            field_value = getattr(value, field_name)
                            normalized_fields.append(
                                (field_name, _normalize_value(field_value))
                            )
                        return (value.__class__.__name__, tuple(normalized_fields))
                    elif hasattr(value, "__dict__"):
                        # Handle regular objects with __dict__
                        normalized_attrs = []
                        for k, v in sorted(value.__dict__.items()):
                            normalized_attrs.append((k, _normalize_value(v)))
                        return (value.__class__.__name__, tuple(normalized_attrs))
                    elif hasattr(value, "_name") and hasattr(value, "_value"):
                        # Handle enum objects
                        return (value.__class__.__name__, value._name, value._value)
                    elif hasattr(value, "name") and hasattr(value, "value"):
                        # Handle enum objects (alternative pattern)
                        return (value.__class__.__name__, value.name, value.value)
                    else:
                        # For any other unhashable type, use repr as stable string representation
                        return repr(value)

            # Create cache key with normalization
            normalized_args = tuple(_normalize_value(arg) for arg in args)
            normalized_kwargs_items = []
            for k, v in sorted(kwargs.items()):
                normalized_kwargs_items.append(
                    (_normalize_value(k), _normalize_value(v))
                )
            normalized_kwargs = tuple(normalized_kwargs_items)
            cache_key = (normalized_args, normalized_kwargs)

            start_time = time.perf_counter()

            # Check cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                duration_ms = (time.perf_counter() - start_time) * 1000
                metrics.record_operation(duration_ms, cache_hit=True)
                return cached_result

            # Compute result
            result = func(*args, **kwargs)
            cache.put(cache_key, result)

            duration_ms = (time.perf_counter() - start_time) * 1000
            metrics.record_operation(duration_ms, cache_hit=False)

            return result

        # Attach cache management methods
        wrapper.clear_cache = cache.clear
        wrapper.cache_stats = cache.stats
        wrapper.metrics = lambda: metrics

        return wrapper

    return decorator


def performance_monitor(operation_name: Optional[str] = None):
    """Decorator to monitor function performance."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        name = operation_name or func.__name__
        metrics = PerformanceMetrics(name)

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                metrics.record_operation(duration_ms)
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                metrics.record_operation(duration_ms)
                raise e

        wrapper.get_metrics = lambda: metrics
        return wrapper

    return decorator


# Factory patterns for common use cases


class DynamicFactory(Generic[T]):
    """Generic factory with dynamic type resolution."""

    def __init__(self):
        self._creators: dict[str, Callable[..., T]] = {}
        self._cache: SmartCache[str, type[T]] = SmartCache(max_size=64)

    def register(self, type_name: str, creator: Callable[..., T]) -> None:
        """Register a creator function for a type."""
        self._creators[type_name] = creator

    def create(self, type_name: str, *args, **kwargs) -> Optional[T]:
        """Create an instance of the specified type."""
        creator = self._creators.get(type_name)
        if creator:
            return creator(*args, **kwargs)
        return None

    def get_registered_types(self) -> list[str]:
        """Get list of registered type names."""
        return list(self._creators.keys())


# Global registry instances for common patterns
_GLOBAL_REGISTRIES: dict[str, DynamicRegistry] = {}
_GLOBAL_LOCK = threading.RLock()


def get_registry(name: str, **kwargs) -> DynamicRegistry:
    """Get or create a global registry instance."""
    with _GLOBAL_LOCK:
        if name not in _GLOBAL_REGISTRIES:
            _GLOBAL_REGISTRIES[name] = DynamicRegistry(**kwargs)
        return _GLOBAL_REGISTRIES[name]


def clear_all_registries() -> None:
    """Clear all global registries (useful for testing)."""
    with _GLOBAL_LOCK:
        for registry in _GLOBAL_REGISTRIES.values():
            registry.clear_cache()
        _GLOBAL_REGISTRIES.clear()
