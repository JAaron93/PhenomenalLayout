"""Dynamic programming implementation for layout strategy selection.

This module replaces the nested if-elif conditional chains in layout.py with
a O(1) lookup table approach. It implements strategy caching, pattern recognition,
and performance optimization for layout preservation decisions.
"""

from __future__ import annotations

import itertools
import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from core.dynamic_programming import (
    PerformanceMetrics,
    StrategyPattern,
    StrategyRegistry,
    get_registry,
    memoize,
    performance_monitor,
)


@contextmanager
def time_operation(
    metrics: PerformanceMetrics, cache_hit: bool = False
) -> Generator[None, None, None]:
    """Context manager for timing operations and recording metrics.

    Args:
        metrics: PerformanceMetrics instance to record timing data
        cache_hit: Whether this operation was a cache hit

    Usage:
        with time_operation(self.metrics) as timer:
            # Your operation code here
            result = some_operation()
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        metrics.record_operation(duration_ms, cache_hit=cache_hit)


# Try to import from dolphin_ocr.layout with fallback
try:
    from dolphin_ocr.layout import (
        BoundingBox,
        FitAnalysis,
        FontInfo,
        LayoutStrategy,
        StrategyType,
    )
except ImportError:
    # Create minimal stubs for when dolphin_ocr.layout is unavailable
    # This allows the module to be imported even if dolphin_ocr is missing
    class BoundingBox:
        """Fallback stub for BoundingBox when dolphin_ocr.layout unavailable."""

        pass

    class FitAnalysis:
        """Fallback stub for FitAnalysis when dolphin_ocr.layout unavailable."""

        pass

    class FontInfo:
        """Fallback stub for FontInfo when dolphin_ocr.layout unavailable."""

        pass

    class LayoutStrategy:
        """Fallback stub for LayoutStrategy when dolphin_ocr.layout unavailable."""

        def __init__(
            self,
            type: Optional[str] = None,
            font_scale: float = 1.0,
            wrap_lines: int = 1,
        ) -> None:
            self.type = type
            self.font_scale = font_scale
            self.wrap_lines = wrap_lines

    class StrategyType:
        """Fallback stub for StrategyType when dolphin_ocr.layout unavailable."""

        NONE: str = "none"
        FONT_SCALE: str = "font_scale"
        TEXT_WRAP: str = "text_wrap"
        HYBRID: str = "hybrid"


# Module logger
logger = logging.getLogger(__name__)


class StrategyKey:
    """Immutable key for strategy lookup table."""

    def __init__(
        self,
        can_fit_unchanged: bool,
        can_scale_single_line: bool,
        can_wrap_within_height: bool,
        sufficient_lines: bool,
    ):
        self.can_fit_unchanged = can_fit_unchanged
        self.can_scale_single_line = can_scale_single_line
        self.can_wrap_within_height = can_wrap_within_height
        self.sufficient_lines = sufficient_lines
        self._hash = hash(self.to_tuple())

    def to_tuple(self) -> tuple[bool, bool, bool, bool]:
        """Convert to tuple for hashing and comparison."""
        return (
            self.can_fit_unchanged,
            self.can_scale_single_line,
            self.can_wrap_within_height,
            self.sufficient_lines,
        )

    def to_int(self) -> int:
        """Convert to integer bit mask for ultra-fast lookup."""
        return (
            (self.can_fit_unchanged << 3)
            | (self.can_scale_single_line << 2)
            | (self.can_wrap_within_height << 1)
            | (self.sufficient_lines << 0)
        )

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, other) -> bool:
        if not isinstance(other, StrategyKey):
            return False
        return self.to_tuple() == other.to_tuple()

    def __repr__(self) -> str:
        return f"StrategyKey({self.to_tuple()})"


@dataclass(frozen=True)
class StrategyBuilder:
    """Builder for creating layout strategies with parameters."""

    strategy_type: StrategyType
    scale_calculation: Optional[str] = None
    lines_calculation: Optional[str] = None
    fallback_strategy: Optional[StrategyType] = None

    def build(
        self, analysis: FitAnalysis, engine_config: dict[str, Any]
    ) -> LayoutStrategy:
        """Build concrete strategy from analysis."""
        if self.strategy_type == StrategyType.NONE:
            return LayoutStrategy(type=StrategyType.NONE, font_scale=1.0, wrap_lines=1)

        elif self.strategy_type == StrategyType.FONT_SCALE:
            scale = max(
                engine_config.get("font_scale_min", 0.6),
                analysis.required_scale_for_single_line,
            )
            return LayoutStrategy(
                type=StrategyType.FONT_SCALE, font_scale=scale, wrap_lines=1
            )

        elif self.strategy_type == StrategyType.TEXT_WRAP:
            lines = analysis.lines_needed
            return LayoutStrategy(
                type=StrategyType.TEXT_WRAP, font_scale=1.0, wrap_lines=lines
            )

        elif self.strategy_type == StrategyType.HYBRID:
            # Calculate optimal scale for available lines
            scale_needed = analysis.max_lines / max(1, analysis.lines_needed)
            clamped_scale = max(
                engine_config.get("font_scale_min", 0.6),
                min(engine_config.get("font_scale_max", 1.2), scale_needed),
            )
            # Simulate lines after scaling
            lines_after_scale = max(1, int(analysis.lines_needed * clamped_scale))

            return LayoutStrategy(
                type=StrategyType.HYBRID,
                font_scale=clamped_scale,
                wrap_lines=min(lines_after_scale, analysis.max_lines),
            )

        # Fallback
        return LayoutStrategy(
            type=StrategyType.TEXT_WRAP, font_scale=1.0, wrap_lines=analysis.max_lines
        )


class DynamicLayoutStrategy(StrategyPattern[LayoutStrategy]):
    """Dynamic strategy for layout decisions."""

    def __init__(
        self, strategy_key: StrategyKey, builder: StrategyBuilder, priority: int = 0
    ):
        self.strategy_key = strategy_key
        self.builder = builder
        self._priority = priority

    def execute(self, context: LayoutContext) -> LayoutStrategy:
        """Execute strategy to produce layout decision."""
        return self.builder.build(context.analysis, context.engine_config)

    def can_handle(self, context: LayoutContext) -> bool:
        """Check if this strategy can handle the context."""
        analysis_key = StrategyKey(
            can_fit_unchanged=context.analysis.can_fit_without_changes,
            can_scale_single_line=context.analysis.can_scale_to_single_line,
            can_wrap_within_height=context.analysis.can_wrap_within_height,
            sufficient_lines=context.analysis.lines_needed
            <= context.analysis.max_lines,
        )
        return analysis_key == self.strategy_key

    @property
    def priority(self) -> int:
        return self._priority


@dataclass
class LayoutContext:
    """Context for layout strategy decisions."""

    analysis: FitAnalysis
    engine_config: dict[str, Any] = field(default_factory=dict)
    original_text: str = ""
    translated_text: str = ""
    bbox: Optional[BoundingBox] = None
    font: Optional[FontInfo] = None


class DynamicLayoutEngine:
    """Dynamic programming implementation of layout strategy selection.

    Replaces the nested conditional logic in LayoutPreservationEngine.determine_layout_strategy()
    with a O(1) lookup table approach for optimal performance.
    """

    def __init__(
        self,
        font_scale_limits: tuple[float, float] = (0.6, 1.2),
        max_bbox_expansion: float = 0.3,
        average_char_width_em: float = 0.5,
        line_height_factor: float = 1.2,
    ):
        self.font_scale_min = font_scale_limits[0]
        self.font_scale_max = font_scale_limits[1]
        self.max_bbox_expansion = max_bbox_expansion
        self.average_char_width_em = average_char_width_em
        self.line_height_factor = line_height_factor

        # Build strategy lookup table
        self.strategy_table = self._build_strategy_table()
        self.strategy_registry = self._build_strategy_registry()

        # Performance tracking
        self.metrics = PerformanceMetrics("dynamic_layout_engine")

        # Engine configuration for strategy builders
        self.engine_config = {
            "font_scale_min": self.font_scale_min,
            "font_scale_max": self.font_scale_max,
            "max_bbox_expansion": self.max_bbox_expansion,
            "average_char_width_em": self.average_char_width_em,
            "line_height_factor": self.line_height_factor,
        }

    def _build_strategy_table(self) -> dict[int, StrategyBuilder]:
        """Pre-compute all possible strategy combinations."""
        table = {}

        # Generate all 16 possible combinations (2^4)
        for conditions in itertools.product([True, False], repeat=4):
            can_fit, can_scale, can_wrap, sufficient_lines = conditions
            key = StrategyKey(can_fit, can_scale, can_wrap, sufficient_lines)

            # Determine strategy based on conditions (replaces original if-elif chain)
            if can_fit:
                # Original fits without changes
                builder = StrategyBuilder(StrategyType.NONE)
            elif can_scale:
                # Can scale to single line
                builder = StrategyBuilder(StrategyType.FONT_SCALE)
            elif can_wrap:
                # Can wrap within height
                builder = StrategyBuilder(StrategyType.TEXT_WRAP)
            else:
                # Need hybrid or fallback
                if sufficient_lines:
                    builder = StrategyBuilder(StrategyType.HYBRID)
                else:
                    # Fallback to best-effort wrapping
                    builder = StrategyBuilder(
                        StrategyType.TEXT_WRAP, fallback_strategy=StrategyType.HYBRID
                    )

            table[key.to_int()] = builder

        return table

    def _build_strategy_registry(self) -> StrategyRegistry[LayoutStrategy]:
        """Build strategy registry for pattern-based selection."""
        registry = StrategyRegistry[LayoutStrategy]()

        # Register strategies in priority order
        priority = 100
        for conditions in itertools.product([True, False], repeat=4):
            can_fit, can_scale, can_wrap, sufficient_lines = conditions
            key = StrategyKey(can_fit, can_scale, can_wrap, sufficient_lines)
            builder = self.strategy_table[key.to_int()]

            # Assign priority based on preference (NONE > FONT_SCALE > TEXT_WRAP > HYBRID)
            if builder.strategy_type == StrategyType.NONE:
                priority_value = 100
            elif builder.strategy_type == StrategyType.FONT_SCALE:
                priority_value = 80
            elif builder.strategy_type == StrategyType.TEXT_WRAP:
                priority_value = 60
            else:  # HYBRID
                priority_value = 40

            strategy = DynamicLayoutStrategy(key, builder, priority_value)
            registry.register(strategy)

        return registry

    @memoize(cache_size=512, ttl_seconds=300)
    def determine_strategy_optimized(self, analysis: FitAnalysis) -> LayoutStrategy:
        """O(1) strategy determination using lookup table.

        This replaces the original determine_layout_strategy method's
        nested conditionals with a direct table lookup.
        """
        with time_operation(self.metrics):
            # Create strategy key from analysis
            key = StrategyKey(
                can_fit_unchanged=analysis.can_fit_without_changes,
                can_scale_single_line=analysis.can_scale_to_single_line,
                can_wrap_within_height=analysis.can_wrap_within_height,
                sufficient_lines=analysis.lines_needed <= analysis.max_lines,
            )

            # O(1) lookup
            builder = self.strategy_table.get(key.to_int())
            if not builder:
                # Fallback to registry-based selection
                context = LayoutContext(
                    analysis=analysis, engine_config=self.engine_config
                )
                strategy = self.strategy_registry.execute(context)
                if strategy:
                    return strategy

                # Ultimate fallback
                return LayoutStrategy(
                    type=StrategyType.TEXT_WRAP,
                    font_scale=1.0,
                    wrap_lines=max(1, analysis.max_lines),
                )

            # Build strategy with current analysis
            result = builder.build(analysis, self.engine_config)

            return result

    @performance_monitor("advanced_strategy_selection")
    def determine_strategy_with_context(
        self,
        analysis: FitAnalysis,
        original_text: str = "",
        translated_text: str = "",
        bbox: Optional[BoundingBox] = None,
        font: Optional[FontInfo] = None,
    ) -> LayoutStrategy:
        """Advanced strategy selection with full context analysis."""
        context = LayoutContext(
            analysis=analysis,
            engine_config=self.engine_config,
            original_text=original_text,
            translated_text=translated_text,
            bbox=bbox,
            font=font,
        )

        # Use strategy registry for context-aware selection
        strategy = self.strategy_registry.execute(context)
        if strategy:
            return strategy

        # Fallback to optimized lookup
        return self.determine_strategy_optimized(analysis)

    def get_strategy_distribution(self) -> dict[StrategyType, int]:
        """Get distribution of strategies in the lookup table."""
        distribution = {}
        for builder in self.strategy_table.values():
            strategy_type = builder.strategy_type
            distribution[strategy_type] = distribution.get(strategy_type, 0) + 1
        return distribution

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics."""
        return {
            "lookup_table_metrics": self.metrics,
            "strategy_registry_metrics": self.strategy_registry.get_metrics(),
            "memoization_metrics": getattr(
                self.determine_strategy_optimized, "metrics", lambda: {}
            )(),
            "cache_stats": getattr(
                self.determine_strategy_optimized, "cache_stats", lambda: {}
            )(),
            "strategy_distribution": self.get_strategy_distribution(),
            "table_size": len(self.strategy_table),
            "registry_strategies": len(self.strategy_registry),
        }

    def benchmark_vs_original(
        self, test_analyses: list[FitAnalysis], iterations: int = 1000
    ) -> dict[str, Any]:
        """Benchmark dynamic approach vs original conditional logic."""
        # Time the optimized approach
        with time_operation(self.metrics):
            for _ in range(iterations):
                for analysis in test_analyses:
                    self.determine_strategy_optimized(analysis)

        # Get timing data from the metrics
        optimized_time = self.metrics.total_duration_ms / 1000  # Convert to seconds

        # Note: Would need original engine for comparison
        # This is a placeholder for the benchmark structure

        return {
            "optimized_time_seconds": optimized_time,
            "test_cases": len(test_analyses),
            "iterations": iterations,
            "avg_time_per_call_ms": (optimized_time / (iterations * len(test_analyses)))
            * 1000,
            "cache_hit_rate": self.metrics.cache_hit_rate,
            "performance_improvement_estimate": self.metrics.performance_improvement,
        }

    def clear_caches(self) -> None:
        """Clear all internal caches."""
        if hasattr(self.determine_strategy_optimized, "clear_cache"):
            self.determine_strategy_optimized.clear_cache()
        self.strategy_registry._cache.clear()

    def analyze_pattern_coverage(
        self, test_analyses: list[FitAnalysis]
    ) -> dict[str, Any]:
        """Analyze how well the lookup table covers real-world patterns."""
        pattern_counts = {}
        total_tests = len(test_analyses)

        for analysis in test_analyses:
            key = StrategyKey(
                can_fit_unchanged=analysis.can_fit_without_changes,
                can_scale_single_line=analysis.can_scale_to_single_line,
                can_wrap_within_height=analysis.can_wrap_within_height,
                sufficient_lines=analysis.lines_needed <= analysis.max_lines,
            )
            key_int = key.to_int()
            pattern_counts[key_int] = pattern_counts.get(key_int, 0) + 1

        # Calculate coverage statistics
        covered_patterns = len(pattern_counts)
        total_patterns = len(self.strategy_table)
        coverage_percentage = (covered_patterns / total_patterns) * 100

        # Find most common patterns
        sorted_patterns = sorted(
            pattern_counts.items(), key=lambda x: x[1], reverse=True
        )

        return {
            "total_test_cases": total_tests,
            "unique_patterns_found": covered_patterns,
            "total_possible_patterns": total_patterns,
            "coverage_percentage": coverage_percentage,
            "most_common_patterns": sorted_patterns[:5],
            "pattern_distribution": pattern_counts,
            "unused_patterns": [
                key for key in self.strategy_table.keys() if key not in pattern_counts
            ],
        }


# Stub class for when LayoutPreservationEngine is unavailable
class _LayoutPreservationEngineStub:
    """Lightweight stub for LayoutPreservationEngine when dolphin_ocr.layout is unavailable."""

    def __init__(self, **kwargs):
        self.config = kwargs
        logger.warning(
            "LayoutPreservationEngine from dolphin_ocr.layout unavailable. "
            "Using stub implementation with limited functionality."
        )

    def analyze_text_fit(self, **kwargs):
        """Stub method that raises clear error when used."""
        raise RuntimeError(
            "LayoutPreservationEngine.analyze_text_fit not available. "
            "The dolphin_ocr.layout module could not be imported. "
            "Please ensure the dolphin_ocr package is properly installed."
        )

    def calculate_quality_score(self, analysis, decision):
        """Stub method that raises clear error when used."""
        raise RuntimeError(
            "LayoutPreservationEngine.calculate_quality_score not available. "
            "The dolphin_ocr.layout module could not be imported. "
            "Please ensure the dolphin_ocr package is properly installed."
        )

    def apply_layout_adjustments(self, **kwargs):
        """Stub method that raises clear error when used."""
        raise RuntimeError(
            "LayoutPreservationEngine.apply_layout_adjustments not available. "
            "The dolphin_ocr.layout module could not be imported. "
            "Please ensure the dolphin_ocr package is properly installed."
        )


# Backward compatibility wrapper
class OptimizedLayoutPreservationEngine:
    """Drop-in replacement for LayoutPreservationEngine with dynamic programming optimizations."""

    def __init__(
        self,
        *,
        font_scale_limits: tuple[float, float] = (0.6, 1.2),
        max_bbox_expansion: float = 0.3,
        average_char_width_em: float = 0.5,
        line_height_factor: float = 1.2,
    ):
        # Import original engine for non-optimized methods with fallback
        try:
            from dolphin_ocr.layout import LayoutPreservationEngine

            self.original_engine = LayoutPreservationEngine(
                font_scale_limits=font_scale_limits,
                max_bbox_expansion=max_bbox_expansion,
                average_char_width_em=average_char_width_em,
                line_height_factor=line_height_factor,
            )
        except ImportError as e:
            logger.warning(
                f"Failed to import LayoutPreservationEngine from dolphin_ocr.layout: {e}. "
                f"Using stub implementation."
            )
            self.original_engine = _LayoutPreservationEngineStub(
                font_scale_limits=font_scale_limits,
                max_bbox_expansion=max_bbox_expansion,
                average_char_width_em=average_char_width_em,
                line_height_factor=line_height_factor,
            )

        self.dynamic_engine = DynamicLayoutEngine(
            font_scale_limits=font_scale_limits,
            max_bbox_expansion=max_bbox_expansion,
            average_char_width_em=average_char_width_em,
            line_height_factor=line_height_factor,
        )

    def analyze_text_fit(self, **kwargs) -> FitAnalysis:
        """Delegate to original implementation."""
        return self.original_engine.analyze_text_fit(**kwargs)

    def determine_layout_strategy(self, analysis: FitAnalysis) -> LayoutStrategy:
        """Use optimized dynamic programming approach."""
        return self.dynamic_engine.determine_strategy_optimized(analysis)

    def calculate_quality_score(
        self, analysis: FitAnalysis, decision: LayoutStrategy
    ) -> float:
        """Delegate to original implementation."""
        return self.original_engine.calculate_quality_score(analysis, decision)

    def apply_layout_adjustments(self, **kwargs):
        """Delegate to original implementation."""
        return self.original_engine.apply_layout_adjustments(**kwargs)

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get performance metrics for the optimized engine."""
        return self.dynamic_engine.get_performance_metrics()

    def benchmark_performance(self, test_analyses: list[FitAnalysis]) -> dict[str, Any]:
        """Benchmark optimized vs original performance."""
        return self.dynamic_engine.benchmark_vs_original(test_analyses)


# Registry for global layout strategies
LAYOUT_STRATEGY_REGISTRY = get_registry(
    "layout_strategies", cache_size=256, ttl_seconds=600
)


def register_layout_strategy(
    name: str,
    strategy_factory: Callable[..., LayoutStrategy],
) -> None:
    """Register a custom layout strategy."""
    LAYOUT_STRATEGY_REGISTRY.register(name, strategy_factory)


def get_layout_strategy(name: str, *args, **kwargs) -> Optional[LayoutStrategy]:
    """Get a registered layout strategy."""
    return LAYOUT_STRATEGY_REGISTRY.get(name, *args, **kwargs)


# Export for backward compatibility
__all__ = [
    "DynamicLayoutEngine",
    "OptimizedLayoutPreservationEngine",
    "LayoutContext",
    "StrategyKey",
    "register_layout_strategy",
    "get_layout_strategy",
]
