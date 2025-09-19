"""Dynamic programming implementation for choice resolution and conflict handling.

This module replaces the nested conditional logic in choice resolution with
pre-computed resolution strategies, context similarity matrices, and intelligent
caching for optimal conflict resolution performance.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from core.dynamic_programming import (
    DynamicRegistry,
    PerformanceMetrics,
    SmartCache,
    StrategyPattern,
    StrategyRegistry,
    memoize,
    performance_monitor,
)
from models.user_choice_models import (
    ChoiceConflict,
    ConflictResolution,
)


class ConflictType(Enum):
    """Types of choice conflicts."""

    TRANSLATION_MISMATCH = "translation_mismatch"
    SCOPE_CONFLICT = "scope_conflict"
    CONFIDENCE_DISAGREEMENT = "confidence_disagreement"
    CONTEXT_OVERLAP = "context_overlap"
    TEMPORAL_CONFLICT = "temporal_conflict"


@dataclass(frozen=True)
class ConflictKey:
    """Immutable key for conflict resolution lookup."""

    conflict_type: ConflictType
    severity_range: tuple[float, float]
    context_similarity: float
    confidence_gap: float
    temporal_distance_hours: float

    def to_hash(self) -> int:
        """Convert to hash for dictionary lookup."""
        data = (
            self.conflict_type.value,
            self.severity_range,
            round(self.context_similarity, 2),
            round(self.confidence_gap, 2),
            round(self.temporal_distance_hours, 1),
        )
        return hash(data)


@dataclass
class ResolutionStrategy:
    """Strategy for resolving a specific type of conflict."""

    strategy_type: ConflictResolution
    confidence_threshold: float
    auto_resolve: bool = True
    explanation: str = ""

    def apply(self, conflict: ChoiceConflict) -> Optional[str]:
        """Apply resolution strategy to conflict."""
        if self.strategy_type == ConflictResolution.LATEST_WINS:
            return self._resolve_latest_wins(conflict)
        elif self.strategy_type == ConflictResolution.HIGHEST_CONFIDENCE:
            return self._resolve_highest_confidence(conflict)
        elif self.strategy_type == ConflictResolution.CONTEXT_SPECIFIC:
            return None  # Keep both choices
        else:  # USER_PROMPT
            return None  # Requires manual resolution

    def _resolve_latest_wins(self, conflict: ChoiceConflict) -> str:
        """Resolve by selecting the most recent choice."""
        if conflict.choice_a.created_at > conflict.choice_b.created_at:
            return conflict.choice_a.choice_id
        return conflict.choice_b.choice_id

    def _resolve_highest_confidence(self, conflict: ChoiceConflict) -> str:
        """Resolve by selecting the highest confidence choice."""
        if conflict.choice_a.confidence_level > conflict.choice_b.confidence_level:
            return conflict.choice_a.choice_id
        return conflict.choice_b.choice_id


@dataclass
class ConflictContext:
    """Context for conflict resolution decisions."""

    conflict: ChoiceConflict
    user_preferences: dict[str, Any] = field(default_factory=dict)
    session_context: dict[str, Any] = field(default_factory=dict)

    def calculate_context_similarity(self) -> float:
        """Calculate similarity between conflicting choice contexts."""
        return self.conflict.choice_a.context.calculate_similarity(
            self.conflict.choice_b.context
        )

    def calculate_confidence_gap(self) -> float:
        """Calculate confidence difference between choices."""
        return abs(
            self.conflict.choice_a.confidence_level
            - self.conflict.choice_b.confidence_level
        )


class DynamicConflictStrategy(StrategyPattern[Optional[str]]):
    """Dynamic strategy for conflict resolution."""

    def __init__(
        self,
        conflict_key: ConflictKey,
        resolution_strategy: ResolutionStrategy,
        priority: int = 0,
    ):
        self.conflict_key = conflict_key
        self.resolution_strategy = resolution_strategy
        self._priority = priority

    def execute(self, context: ConflictContext) -> Optional[str]:
        """Execute resolution strategy."""
        return self.resolution_strategy.apply(context.conflict)

    def can_handle(self, context: ConflictContext) -> bool:
        """Check if this strategy can handle the conflict."""
        # Simplified matching based on context similarity
        similarity = context.calculate_context_similarity()
        confidence_gap = context.calculate_confidence_gap()

        return (
            abs(self.conflict_key.context_similarity - similarity) <= 0.1
            and abs(self.conflict_key.confidence_gap - confidence_gap) <= 0.1
        )

    @property
    def priority(self) -> int:
        return self._priority


class DynamicConflictResolutionEngine:
    """Dynamic programming implementation for conflict resolution."""

    def __init__(self, cache_size: int = 512):
        # Core components
        self.resolution_table: dict[int, ResolutionStrategy] = {}
        self.strategy_registry: StrategyRegistry[Optional[str]] = StrategyRegistry()

        # Caching systems
        self.resolution_cache: SmartCache[str, Optional[str]] = SmartCache(
            max_size=cache_size, ttl_seconds=1800
        )

        # Performance tracking
        self.metrics = PerformanceMetrics("dynamic_conflict_resolution")

        # Initialize strategies
        self._build_resolution_table()
        self._register_strategies()

    def _build_resolution_table(self) -> None:
        """Pre-compute resolution strategies for common conflict patterns."""
        # High confidence gap + high similarity -> Highest confidence
        self.resolution_table[1] = ResolutionStrategy(
            ConflictResolution.HIGHEST_CONFIDENCE,
            confidence_threshold=0.8,
            explanation="High confidence gap with similar contexts",
        )

        # Low similarity -> Latest wins
        self.resolution_table[2] = ResolutionStrategy(
            ConflictResolution.LATEST_WINS,
            confidence_threshold=0.5,
            explanation="Different contexts, recent conflict",
        )

        # High similarity + low confidence gap -> Context specific
        self.resolution_table[3] = ResolutionStrategy(
            ConflictResolution.CONTEXT_SPECIFIC,
            confidence_threshold=0.6,
            explanation="Very similar contexts, maintain both choices",
        )

    def _register_strategies(self) -> None:
        """Register strategies in the strategy registry."""
        for table_key, strategy in self.resolution_table.items():
            conflict_key = ConflictKey(
                conflict_type=ConflictType.TRANSLATION_MISMATCH,
                severity_range=(0.0, 1.0),
                context_similarity=0.5,
                confidence_gap=0.3,
                temporal_distance_hours=12.0,
            )

            dynamic_strategy = DynamicConflictStrategy(
                conflict_key=conflict_key,
                resolution_strategy=strategy,
                priority=table_key * 10,
            )

            self.strategy_registry.register(dynamic_strategy)

    @memoize(cache_size=256, ttl_seconds=600)
    def resolve_conflict_optimized(
        self, conflict: ChoiceConflict, **context_kwargs
    ) -> Optional[str]:
        """Optimized conflict resolution with caching and pre-computed strategies."""
        start_time = time.perf_counter()

        try:
            # Create resolution context
            context = ConflictContext(conflict=conflict, **context_kwargs)

            # Create cache key
            cache_key = f"{conflict.conflict_id}:{conflict.context_similarity:.2f}"

            # Check cache
            cached_result = self.resolution_cache.get(cache_key)
            if cached_result is not None:
                duration_ms = (time.perf_counter() - start_time) * 1000
                self.metrics.record_operation(duration_ms, cache_hit=True)
                return cached_result

            # Try strategy registry
            strategy = self.strategy_registry.select_strategy(context)
            resolution_result = None

            if strategy:
                resolution_result = strategy.execute(context)

            # Fallback to simple resolution
            if resolution_result is None:
                resolution_result = self._default_resolution(conflict)

            # Cache result
            self.resolution_cache.put(cache_key, resolution_result)

            duration_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.record_operation(duration_ms, cache_hit=False)

            return resolution_result

        except Exception as e:
            import logging

            logging.error(f"Error resolving conflict {conflict.conflict_id}: {e}")
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.record_operation(duration_ms, cache_hit=False)
            return None

    def _default_resolution(self, conflict: ChoiceConflict) -> str:
        """Default resolution when no strategy matches."""
        # Simple fallback: latest wins
        if conflict.choice_a.created_at > conflict.choice_b.created_at:
            return conflict.choice_a.choice_id
        return conflict.choice_b.choice_id

    @performance_monitor("batch_conflict_resolution")
    def resolve_conflicts_batch(
        self, conflicts: list[ChoiceConflict]
    ) -> dict[str, Optional[str]]:
        """Batch conflict resolution for improved throughput."""
        results = {}

        for conflict in conflicts:
            resolution = self.resolve_conflict_optimized(conflict)
            results[conflict.conflict_id] = resolution

        return results

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics."""
        return {
            "resolution_metrics": self.metrics,
            "cache_stats": self.resolution_cache.stats(),
            "memoization_stats": getattr(
                self.resolve_conflict_optimized, "cache_stats", lambda: {}
            )(),
            "strategy_registry_stats": self.strategy_registry.get_metrics(),
        }

    def clear_caches(self) -> None:
        """Clear all internal caches."""
        self.resolution_cache.clear()
        if hasattr(self.resolve_conflict_optimized, "clear_cache"):
            self.resolve_conflict_optimized.clear_cache()


# Backward compatibility wrapper
class _UserChoiceManagerStub:
    """Lightweight stub for UserChoiceManager when services are unavailable."""

    def __init__(self, db_path: str = "database/user_choices.db"):
        self.db_path = db_path
        logging.warning(
            "UserChoiceManager service unavailable. "
            "Using stub implementation with limited functionality."
        )

    def __getattr__(self, name):
        """Handle arbitrary method calls safely."""

        def stub_method(*args, **kwargs):
            logging.warning(
                f"UserChoiceManager method '{name}' called on stub. "
                f"Returning None/empty result."
            )
            return None

        return stub_method


class OptimizedUserChoiceManager:
    """Drop-in replacement for UserChoiceManager with dynamic programming optimizations."""

    def __init__(
        self,
        db_path: str = "database/user_choices.db",
        auto_resolve_conflicts: bool = True,
        session_expiry_hours: int = 24,
    ):
        # Import original manager for compatibility with fallback
        try:
            from services.user_choice_manager import UserChoiceManager

            self.original_manager = UserChoiceManager(
                db_path=db_path,
                auto_resolve_conflicts=auto_resolve_conflicts,
                session_expiry_hours=session_expiry_hours,
            )
        except ImportError as e:
            logging.warning(
                f"Failed to import UserChoiceManager: {e}. "
                f"Using stub implementation."
            )
            self.original_manager = _UserChoiceManagerStub(db_path)

        self.dynamic_engine = DynamicConflictResolutionEngine()

    def resolve_conflict(self, conflict: ChoiceConflict) -> Optional[str]:
        """Use optimized conflict resolution."""
        return self.dynamic_engine.resolve_conflict_optimized(conflict)

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get performance metrics."""
        return self.dynamic_engine.get_performance_metrics()

    def __getattr__(self, name):
        """Delegate other methods to original manager."""
        return getattr(self.original_manager, name)


# Global registry for conflict resolution engines
CONFLICT_RESOLUTION_REGISTRY = DynamicRegistry[DynamicConflictResolutionEngine](
    cache_size=16, ttl_seconds=3600
)


def register_conflict_resolver(name: str, resolver_factory: callable) -> None:
    """Register a custom conflict resolver."""
    CONFLICT_RESOLUTION_REGISTRY.register(name, resolver_factory)


def get_conflict_resolver(
    name: str = "default", **kwargs
) -> DynamicConflictResolutionEngine:
    """Get a conflict resolver instance."""
    if name == "default":
        return DynamicConflictResolutionEngine(**kwargs)
    return CONFLICT_RESOLUTION_REGISTRY.get(name, **kwargs)


# Convenience functions for unified API
def create_session_for_document(
    manager,  # UserChoiceManager or OptimizedUserChoiceManager
    document_name: str,
    user_id: Optional[str] = None,
    source_lang: str = "de",
    target_lang: str = "en",
):
    """Create a session for processing a document.

    This convenience function provides a unified API for creating sessions,
    working with both UserChoiceManager and OptimizedUserChoiceManager.

    Args:
        manager: UserChoiceManager or OptimizedUserChoiceManager instance
        document_name: Name of the document being processed
        user_id: Optional user identifier
        source_lang: Source language code (default: "de")
        target_lang: Target language code (default: "en")

    Returns:
        ChoiceSession: Created session object
    """
    return manager.create_session(
        session_name=f"Processing: {document_name}",
        document_name=document_name,
        user_id=user_id,
        source_language=source_lang,
        target_language=target_lang,
    )


# Export for backward compatibility
__all__ = [
    "DynamicConflictResolutionEngine",
    "OptimizedUserChoiceManager",
    "ConflictKey",
    "ResolutionStrategy",
    "ConflictContext",
    "register_conflict_resolver",
    "get_conflict_resolver",
    "create_session_for_document",
]
