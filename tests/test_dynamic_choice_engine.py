"""Tests for dynamic conflict resolution (core/dynamic_choice_engine.py)."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any, cast

import pytest

from core.dynamic_choice_engine import (
    CONFLICT_RESOLUTION_REGISTRY,
    ConflictContext,
    ConflictKey,
    ConflictType,
    DynamicConflictResolutionEngine,
    DynamicConflictStrategy,
    OptimizedUserChoiceManager,
    ResolutionStrategy,
    _UserChoiceManagerStub,
    create_session_for_document,
    get_conflict_resolver,
    register_conflict_resolver,
)
from models.user_choice_models import (
    ChoiceConflict,
    ChoiceScope,
    ChoiceType,
    ConflictResolution,
    TranslationContext,
    UserChoice,
)

OLDER = "2023-01-01T10:00:00"
NEWER = "2023-01-02T10:00:00"


def make_choice(
    choice_id: str, confidence: float, created_at: str, sentence: str
) -> UserChoice:
    context = TranslationContext(
        sentence_context=sentence,
        semantic_field="ontology",
        source_language="German",
        target_language="English",
    )
    return UserChoice(
        choice_id=choice_id,
        neologism_term="Dasein",
        choice_type=ChoiceType.TRANSLATE,
        translation_result="being-there",
        context=context,
        choice_scope=ChoiceScope.CONTEXTUAL,
        confidence_level=confidence,
        created_at=created_at,
    )


def make_conflict(
    conflict_id: str,
    conf_a: float = 0.9,
    conf_b: float = 0.5,
    created_a: str = NEWER,
    created_b: str = OLDER,
    similarity: float = 0.5,
) -> ChoiceConflict:
    return ChoiceConflict(
        conflict_id=conflict_id,
        neologism_term="Dasein",
        choice_a=make_choice(
            f"a-{conflict_id}", conf_a, created_a, f"Das Sein {conflict_id}"
        ),
        choice_b=make_choice(
            f"b-{conflict_id}", conf_b, created_b, f"Das Wesen {conflict_id}"
        ),
        context_similarity=similarity,
    )


class TestConflictKey:
    def test_to_hash_is_deterministic(self) -> None:
        key = ConflictKey(
            conflict_type=ConflictType.SCOPE_CONFLICT,
            severity_range=(0.0, 1.0),
            context_similarity=0.5,
            confidence_gap=0.3,
            temporal_distance_hours=12.0,
        )
        assert key.to_hash() == key.to_hash()

    def test_to_hash_rounds_float_components(self) -> None:
        base = ConflictKey(
            conflict_type=ConflictType.SCOPE_CONFLICT,
            severity_range=(0.0, 1.0),
            context_similarity=0.1231,
            confidence_gap=0.4561,
            temporal_distance_hours=12.341,
        )
        rounded = ConflictKey(
            conflict_type=ConflictType.SCOPE_CONFLICT,
            severity_range=(0.0, 1.0),
            context_similarity=0.1234,
            confidence_gap=0.4564,
            temporal_distance_hours=12.344,
        )
        assert base.to_hash() == rounded.to_hash()

    def test_to_hash_differs_by_conflict_type(self) -> None:
        common: dict[str, Any] = {
            "severity_range": (0.0, 1.0),
            "context_similarity": 0.5,
            "confidence_gap": 0.3,
            "temporal_distance_hours": 12.0,
        }
        first = ConflictKey(
            conflict_type=ConflictType.SCOPE_CONFLICT, **common
        )
        second = ConflictKey(
            conflict_type=ConflictType.TEMPORAL_CONFLICT, **common
        )
        assert first.to_hash() != second.to_hash()


class TestResolutionStrategy:
    def test_latest_wins_selects_newer_choice(self) -> None:
        strategy = ResolutionStrategy(
            ConflictResolution.LATEST_WINS, confidence_threshold=0.5
        )
        conflict = make_conflict("lw1", created_a=NEWER, created_b=OLDER)
        assert strategy.apply(conflict) == "a-lw1"

    def test_latest_wins_selects_choice_b_when_newer(self) -> None:
        strategy = ResolutionStrategy(
            ConflictResolution.LATEST_WINS, confidence_threshold=0.5
        )
        conflict = make_conflict("lw2", created_a=OLDER, created_b=NEWER)
        assert strategy.apply(conflict) == "b-lw2"

    def test_highest_confidence_selects_choice_a(self) -> None:
        strategy = ResolutionStrategy(
            ConflictResolution.HIGHEST_CONFIDENCE, confidence_threshold=0.8
        )
        conflict = make_conflict("hc1", conf_a=0.9, conf_b=0.4)
        assert strategy.apply(conflict) == "a-hc1"

    def test_highest_confidence_selects_choice_b(self) -> None:
        strategy = ResolutionStrategy(
            ConflictResolution.HIGHEST_CONFIDENCE, confidence_threshold=0.8
        )
        conflict = make_conflict("hc2", conf_a=0.4, conf_b=0.9)
        assert strategy.apply(conflict) == "b-hc2"

    def test_context_specific_keeps_both_choices(self) -> None:
        strategy = ResolutionStrategy(
            ConflictResolution.CONTEXT_SPECIFIC, confidence_threshold=0.6
        )
        assert strategy.apply(make_conflict("cs1")) is None

    def test_user_prompt_requires_manual_resolution(self) -> None:
        strategy = ResolutionStrategy(
            ConflictResolution.USER_PROMPT, confidence_threshold=0.6
        )
        assert strategy.apply(make_conflict("up1")) is None

    def test_defaults(self) -> None:
        strategy = ResolutionStrategy(
            ConflictResolution.LATEST_WINS, confidence_threshold=0.5
        )
        assert strategy.auto_resolve is True
        assert strategy.explanation == ""


class TestConflictContext:
    def test_calculate_context_similarity_forwards_to_model(self) -> None:
        conflict = make_conflict("cc1")
        context = ConflictContext(conflict=conflict)
        expected = conflict.choice_a.context.calculate_similarity(
            conflict.choice_b.context
        )
        assert context.calculate_context_similarity() == expected

    def test_calculate_confidence_gap(self) -> None:
        conflict = make_conflict("cc2", conf_a=0.9, conf_b=0.4)
        context = ConflictContext(conflict=conflict)
        assert context.calculate_confidence_gap() == pytest.approx(0.5)

    def test_defaults_are_empty_dicts(self) -> None:
        context = ConflictContext(conflict=make_conflict("cc3"))
        assert context.user_preferences == {}
        assert context.session_context == {}


class TestDynamicConflictStrategy:
    def _fake_conflict(
        self, similarity: float, conf_a: float, conf_b: float
    ) -> ChoiceConflict:
        fake = SimpleNamespace(
            choice_a=SimpleNamespace(
                confidence_level=conf_a,
                context=SimpleNamespace(
                    calculate_similarity=lambda _other: similarity
                ),
            ),
            choice_b=SimpleNamespace(
                confidence_level=conf_b,
                context=SimpleNamespace(
                    calculate_similarity=lambda _other: similarity
                ),
            ),
        )
        return cast(ChoiceConflict, fake)

    def _strategy_with_key(
        self, similarity: float, confidence_gap: float, priority: int = 5
    ) -> DynamicConflictStrategy:
        key = ConflictKey(
            conflict_type=ConflictType.TRANSLATION_MISMATCH,
            severity_range=(0.0, 1.0),
            context_similarity=similarity,
            confidence_gap=confidence_gap,
            temporal_distance_hours=12.0,
        )
        resolution = ResolutionStrategy(
            ConflictResolution.LATEST_WINS, confidence_threshold=0.5
        )
        return DynamicConflictStrategy(
            conflict_key=key, resolution_strategy=resolution, priority=priority
        )

    def test_can_handle_within_tolerance(self) -> None:
        strategy = self._strategy_with_key(similarity=0.5, confidence_gap=0.3)
        context = ConflictContext(
            conflict=self._fake_conflict(0.55, 0.9, 0.55)
        )
        assert strategy.can_handle(context) is True

    def test_can_handle_rejects_similarity_outside_tolerance(self) -> None:
        strategy = self._strategy_with_key(similarity=0.5, confidence_gap=0.3)
        context = ConflictContext(
            conflict=self._fake_conflict(0.9, 0.9, 0.6)
        )
        assert strategy.can_handle(context) is False

    def test_can_handle_rejects_confidence_gap_outside_tolerance(
        self,
    ) -> None:
        strategy = self._strategy_with_key(similarity=0.5, confidence_gap=0.3)
        context = ConflictContext(
            conflict=self._fake_conflict(0.5, 0.9, 0.1)
        )
        assert strategy.can_handle(context) is False

    def test_execute_applies_resolution_strategy(self) -> None:
        strategy = self._strategy_with_key(similarity=0.5, confidence_gap=0.3)
        conflict = make_conflict("ex1", created_a=NEWER, created_b=OLDER)
        context = ConflictContext(conflict=conflict)
        assert strategy.execute(context) == "a-ex1"

    def test_priority_property(self) -> None:
        assert self._strategy_with_key(0.5, 0.3, priority=42).priority == 42


class TestDynamicConflictResolutionEngine:
    def test_resolution_table_is_precomputed(self) -> None:
        engine = DynamicConflictResolutionEngine()
        assert set(engine.resolution_table) == {1, 2, 3}
        assert (
            engine.resolution_table[1].strategy_type
            == ConflictResolution.HIGHEST_CONFIDENCE
        )
        assert (
            engine.resolution_table[2].strategy_type
            == ConflictResolution.LATEST_WINS
        )
        assert (
            engine.resolution_table[3].strategy_type
            == ConflictResolution.CONTEXT_SPECIFIC
        )
        assert len(engine.strategy_registry) == 3

    def test_resolve_returns_choice_id(self) -> None:
        engine = DynamicConflictResolutionEngine()
        result = engine.resolve_conflict_optimized(make_conflict("r1"))
        assert result in ("a-r1", "b-r1")

    def test_memoized_second_call_returns_cached_result(self) -> None:
        engine = DynamicConflictResolutionEngine()
        # The memo decorator keeps a function-level cache shared across
        # engine instances; clear it so this test owns its cache state.
        engine.clear_caches()
        conflict = make_conflict("r2")
        first = engine.resolve_conflict_optimized(conflict)
        second = engine.resolve_conflict_optimized(conflict)
        assert first == second
        memo_stats = engine.get_performance_metrics()["memoization_stats"]
        assert memo_stats["size"] == 1

    def test_resolution_cache_hit_path(self) -> None:
        engine = DynamicConflictResolutionEngine()
        conflict = make_conflict("r3")
        underlying = cast(Any, engine.resolve_conflict_optimized).__wrapped__
        assert underlying is not None
        first = underlying(engine, conflict)
        second = underlying(engine, conflict)
        assert first == second
        assert engine.metrics.cache_hits >= 1

    def test_unexpected_context_kwargs_return_none(self) -> None:
        engine = DynamicConflictResolutionEngine()
        result = engine.resolve_conflict_optimized(
            make_conflict("r4"), unexpected_kwarg="boom"
        )
        assert result is None

    def test_default_resolution_latest_wins(self) -> None:
        engine = DynamicConflictResolutionEngine()
        conflict = make_conflict("r5", created_a=OLDER, created_b=NEWER)
        assert engine._default_resolution(conflict) == "b-r5"

    def test_batch_resolution(self) -> None:
        engine = DynamicConflictResolutionEngine()
        conflicts = [make_conflict(f"b{i}") for i in range(3)]
        results = engine.resolve_conflicts_batch(conflicts)
        # Choice A is both newer and more confident, so every strategy
        # (and the latest-wins default) must select it.
        assert results == {f"b{i}": f"a-b{i}" for i in range(3)}

    def test_get_performance_metrics_keys(self) -> None:
        engine = DynamicConflictResolutionEngine()
        metrics = engine.get_performance_metrics()
        assert set(metrics) == {
            "resolution_metrics",
            "cache_stats",
            "memoization_stats",
            "strategy_registry_stats",
        }

    def test_clear_caches(self) -> None:
        engine = DynamicConflictResolutionEngine()
        engine.resolve_conflict_optimized(make_conflict("r6"))
        engine.clear_caches()
        assert engine.resolution_cache.size() == 0


class TestOptimizedUserChoiceManager:
    def test_delegates_conflict_resolution(self, tmp_path: Any) -> None:
        manager = OptimizedUserChoiceManager(db_path=str(tmp_path / "choices.db"))
        conflict = make_conflict("m1", created_a=NEWER, created_b=OLDER)
        assert manager.resolve_conflict(conflict) == "a-m1"

    def test_getattr_delegates_to_original_manager(
        self, tmp_path: Any
    ) -> None:
        manager = OptimizedUserChoiceManager(db_path=str(tmp_path / "choices.db"))
        # `create_session` only exists on the wrapped original manager, so
        # reaching it exercises the __getattr__ delegation path.
        assert callable(manager.create_session)

    def test_get_performance_metrics_delegates(self, tmp_path: Any) -> None:
        manager = OptimizedUserChoiceManager(db_path=str(tmp_path / "choices.db"))
        assert "resolution_metrics" in manager.get_performance_metrics()

    def test_stub_fallback_when_service_unavailable(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "services.user_choice_manager", None)
        manager = OptimizedUserChoiceManager(db_path=str(tmp_path / "choices.db"))
        assert isinstance(manager.original_manager, _UserChoiceManagerStub)
        assert manager.any_unknown_method() is None


class TestResolverRegistry:
    def test_default_resolver_created_on_demand(self) -> None:
        resolver = get_conflict_resolver("default", cache_size=32)
        assert isinstance(resolver, DynamicConflictResolutionEngine)
        assert resolver.resolution_cache.max_size == 32

    def test_registered_resolver_is_cached(self) -> None:
        def factory() -> DynamicConflictResolutionEngine:
            return DynamicConflictResolutionEngine(cache_size=8)

        register_conflict_resolver("custom-test", factory)
        CONFLICT_RESOLUTION_REGISTRY.clear_cache()
        first = get_conflict_resolver("custom-test")
        second = get_conflict_resolver("custom-test")
        assert first is second
        assert first.resolution_cache.max_size == 8

    def test_unregistered_resolver_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="not registered"):
            get_conflict_resolver("never-registered-xyz")


class TestCreateSessionForDocument:
    def test_forwards_session_parameters(self) -> None:
        captured: dict[str, Any] = {}

        def fake_create_session(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"session": True}

        manager = SimpleNamespace(create_session=fake_create_session)
        result = create_session_for_document(
            manager, "Klages_1929.pdf", user_id="user-1"
        )
        assert result == {"session": True}
        assert captured["session_name"] == "Processing: Klages_1929.pdf"
        assert captured["document_name"] == "Klages_1929.pdf"
        assert captured["user_id"] == "user-1"
        assert captured["source_language"] == "de"
        assert captured["target_language"] == "en"
