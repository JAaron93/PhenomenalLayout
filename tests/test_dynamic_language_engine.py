"""Coverage-gap unit tests for the dynamic language detection engine.

Exercises CompiledPattern consistency/weight validation, fingerprint
scoring, detector initialization failure and idempotence, inner
result-cache hits, detection failure fallbacks, batch cache reuse,
confidence analysis, benchmarking, and the singleton/registry accessors.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

import core.dynamic_language_engine as cle
from core.dynamic_language_engine import (
    DEFAULT_MIN_TEXT_LENGTH,
    CompiledPattern,
    DynamicLanguageDetector,
    LanguageScore,
    OptimizedLanguageDetector,
    TextFingerprint,
    get_language_detector,
    register_language_detector,
)
from services.language_detector import (
    LANGUAGE_MAP,
    LANGUAGE_PATTERNS,
    LanguageDetector,
)

GERMAN_TEXT = "Der schnelle braune Fuchs springt über den faulen Hund hinaus."


class _StubOriginalDetector:
    """Stand-in for LanguageDetector at the OptimizedLanguageDetector boundary."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    def detect_language(
        self,
        file_path: str,
        text_extractor: Any = None,
        pre_extracted_text: Any = None,
    ) -> str:
        self.calls.append((file_path, text_extractor, pre_extracted_text))
        return "StubLanguage"


def _poisoned_german_pattern(detector: DynamicLanguageDetector) -> None:
    """Replace the German pattern with one whose scoring weights are invalid."""
    original = detector.compiled_patterns["German"]
    detector.compiled_patterns["German"] = CompiledPattern(
        language="German",
        words_regex=original.words_regex,
        chars_regex=original.chars_regex,
        word_weight=original.word_weight,
        char_weight=original.char_weight,
        word_list=original.word_list,
        char_list=original.char_list,
        word_pattern_weight=0.0,
        char_pattern_weight=0.3,
    )


class TestCompiledPatternContract:
    """Validation and scoring behavior of CompiledPattern."""

    def test_words_regex_none_with_word_list_raises(self) -> None:
        """A word list without a compiled regex is inconsistent."""
        with pytest.raises(ValueError, match=r"Inconsistent word pattern"):
            CompiledPattern(
                language="Broken",
                words_regex=None,
                chars_regex=re.compile("[a]"),
                word_weight=1.0,
                char_weight=1.0,
                word_list=("a",),
                char_list=("a",),
            )

    def test_chars_regex_none_with_char_list_raises(self) -> None:
        """A char list without a compiled regex is inconsistent."""
        with pytest.raises(ValueError, match=r"Inconsistent char pattern"):
            CompiledPattern(
                language="Broken",
                words_regex=re.compile(r"\b(?:a)\b"),
                chars_regex=None,
                word_weight=1.0,
                char_weight=1.0,
                word_list=("a",),
                char_list=("a",),
            )

    def test_non_positive_pattern_weights_raise_in_compute_score(self) -> None:
        """compute_score rejects non-positive pattern-mix weights."""
        pattern = CompiledPattern(
            language="Broken",
            words_regex=re.compile(r"\b(?:a)\b"),
            chars_regex=None,
            word_weight=1.0,
            char_weight=1.0,
            word_list=("a",),
            char_list=(),
            word_pattern_weight=0.0,
            char_pattern_weight=0.3,
        )

        with pytest.raises(ValueError, match=r"Pattern weights must be positive"):
            pattern.compute_score("a", {"a"})

    def test_compute_score_normalizes_pattern_weights(self) -> None:
        """Pattern weights are normalized before combining word/char scores."""
        pattern = CompiledPattern(
            language="German",
            words_regex=re.compile(r"\b(?:der)\b"),
            chars_regex=re.compile("[ä]"),
            word_weight=1.0,
            char_weight=2.0,
            word_list=("der",),
            char_list=("ä",),
            word_pattern_weight=3.0,
            char_pattern_weight=1.0,
        )

        score = pattern.compute_score("der ärmel", {"der"})

        # word_score = 1*1/1*100 = 100; char_score = 1*2/9*100 = 22.22;
        # normalized mix 0.75/0.25 -> 0.75*100 + 0.25*22.22 = 80.56.
        assert score.language == "German"
        assert score.word_matches == 1
        assert score.char_matches == 1
        assert score.word_score == pytest.approx(100.0)
        assert score.char_score == pytest.approx(22.22, rel=1e-3)
        assert score.confidence == pytest.approx(80.56, rel=1e-3)

    def test_language_score_total_score_exposes_confidence(self) -> None:
        """total_score is an alias for the confidence field."""
        assert LanguageScore(language="German", confidence=42.0).total_score == 42.0


class TestDetectorInitialization:
    """Detector construction, validity gating, and pattern initialization."""

    def test_is_text_valid_rejects_empty_and_whitespace(self) -> None:
        """Empty and whitespace-only texts never qualify for detection."""
        detector = DynamicLanguageDetector()

        assert detector._is_text_valid_for_detection("") is False
        assert detector._is_text_valid_for_detection("   \n\t") is False
        assert detector._is_text_valid_for_detection(GERMAN_TEXT) is True

    def test_initialize_patterns_is_idempotent(self) -> None:
        """Re-initialization short-circuits when patterns are already compiled."""
        detector = DynamicLanguageDetector()
        compiled_before = dict(detector.compiled_patterns)

        detector._initialize_patterns()

        assert detector.compiled_patterns == compiled_before

    def test_initialize_patterns_failure_records_and_reraises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pattern compilation failures record metrics before re-raising."""
        monkeypatch.setattr(cle, "LANGUAGE_PATTERNS", {"Broken": None})

        with pytest.raises(AttributeError):
            DynamicLanguageDetector()

    def test_compile_pattern_without_words_yields_none_regex(self) -> None:
        """Char-only pattern data compiles with no word regex and no word list."""
        detector = DynamicLanguageDetector()

        pattern = detector._compile_pattern(
            "CharOnly",
            {"words": [], "chars": ["ä", "ß"], "word_weight": 1.0, "char_weight": 2.0},
        )

        assert pattern.words_regex is None
        assert pattern.word_list == ()
        assert pattern.chars_regex is not None
        assert pattern.chars_regex.findall("ä ß") == ["ä", "ß"]

    def test_all_supported_patterns_compile_with_word_regexes(self) -> None:
        """Every shipped language compiles a word regex and registers an index."""
        detector = DynamicLanguageDetector()

        assert set(detector.compiled_patterns) == set(LANGUAGE_PATTERNS)
        assert set(detector.language_index) == set(LANGUAGE_PATTERNS)
        for pattern in detector.compiled_patterns.values():
            assert pattern.words_regex is not None


class TestDetectLanguageOptimized:
    """Single-text optimized detection including cache and failure paths."""

    def test_inner_result_cache_hit_on_equivalent_kwargs(self) -> None:
        """An explicit min_length equal to the default hits the inner cache."""
        detector = DynamicLanguageDetector()
        detector.clear_caches()

        first = detector.detect_language_optimized(GERMAN_TEXT)
        second = detector.detect_language_optimized(
            GERMAN_TEXT, min_length=DEFAULT_MIN_TEXT_LENGTH
        )

        assert first == second == "German"

    def test_scoring_failure_is_swallowed_and_returns_unknown(self) -> None:
        """Detection errors are logged and surface as "Unknown"."""
        detector = DynamicLanguageDetector()
        detector.clear_caches()
        _poisoned_german_pattern(detector)

        assert detector.detect_language_optimized(GERMAN_TEXT) == "Unknown"


class TestBatchDetection:
    """Batch detection with cache-reuse behavior."""

    def test_batch_second_run_serves_every_text_from_cache(self) -> None:
        """A repeated batch is fully served by the result cache."""
        detector = DynamicLanguageDetector()
        texts = [
            GERMAN_TEXT,
            "The quick brown fox jumps over the lazy dog nearby.",
        ]

        first = detector.detect_languages_batch(texts)
        second = detector.detect_languages_batch(texts)

        assert first == second
        assert first[0] == "German"
        assert first[1] == "English"


class TestConfidenceReporting:
    """Confidence-aware detection and detailed score reporting."""

    def test_short_text_returns_unknown_with_zero_confidence(self) -> None:
        """Below the minimum length detection short-circuits."""
        detector = DynamicLanguageDetector()

        assert detector.detect_language_with_confidence("hi") == ("Unknown", 0.0)

    def test_confident_detection_returns_language_and_score(self) -> None:
        """Clear German text reports the language with a positive confidence."""
        detector = DynamicLanguageDetector()

        language, confidence = detector.detect_language_with_confidence(GERMAN_TEXT)

        assert language == "German"
        assert confidence > 0.0

    def test_below_threshold_returns_unknown_but_keeps_confidence(self) -> None:
        """A confidence under the threshold downgrades the label to Unknown."""
        detector = DynamicLanguageDetector(confidence_threshold=1_000_000.0)

        language, confidence = detector.detect_language_with_confidence(GERMAN_TEXT)

        assert language == "Unknown"
        assert confidence > 0.0

    def test_get_language_scores_empty_for_short_text(self) -> None:
        """Short texts return an empty score table."""
        detector = DynamicLanguageDetector()

        assert detector.get_language_scores("hi") == {}

    def test_single_language_analysis_has_zero_confidence_gap(self) -> None:
        """With one compiled pattern the gap is zero and quality is low."""
        detector = DynamicLanguageDetector()
        detector.compiled_patterns = {"Solo": detector.compiled_patterns["German"]}

        analysis = detector.analyze_detection_confidence(GERMAN_TEXT)

        assert analysis["detected_language"] == "German"
        assert analysis["confidence"] > 0.0
        assert analysis["confidence_gap"] == 0.0
        assert analysis["detection_quality"] == "low"
        # The aliased pattern keeps its intrinsic language label.
        assert list(analysis["all_scores"]) == ["German"]


class TestDetectorMaintenance:
    """Performance metrics, benchmarking, and threshold maintenance."""

    def test_get_performance_metrics_exposes_sections(self) -> None:
        """Metrics bundle detection, pattern, cache, and memoization stats."""
        detector = DynamicLanguageDetector()
        detector.detect_language_optimized(GERMAN_TEXT)

        metrics = detector.get_performance_metrics()

        assert set(metrics) == {
            "detection_metrics",
            "pattern_compilation_metrics",
            "cache_stats",
            "optimization_status",
            "memoization_stats",
        }
        assert metrics["optimization_status"]["patterns_compiled"] == len(
            LANGUAGE_PATTERNS
        )

    def test_benchmark_vs_original_returns_report(self) -> None:
        """Benchmark compares cached and uncached detection timing profiles."""
        detector = DynamicLanguageDetector()
        texts = [GERMAN_TEXT, "The quick brown fox jumps over the lazy dog nearby."]

        report = detector.benchmark_vs_original(texts, iterations=2)

        assert report["test_cases"] == 2
        assert report["iterations"] == 2
        assert report["speedup_factor"] >= 0
        assert report["avg_optimized_ms"] >= 0
        assert report["avg_uncached_ms"] >= 0
        assert 0.0 <= report["cache_effectiveness"] <= 100.0

    def test_get_supported_languages_lists_compiled_patterns(self) -> None:
        """Supported languages mirror the compiled pattern keys."""
        detector = DynamicLanguageDetector()

        assert detector.get_supported_languages() == list(LANGUAGE_PATTERNS)

    def test_update_confidence_threshold_clamps_and_clears_cache(self) -> None:
        """Threshold updates are clamped to [0, 1] and drop cached results."""
        detector = DynamicLanguageDetector()
        detector.result_cache.put(TextFingerprint.create("cache me please").to_cache_key(), "German")

        detector.update_confidence_threshold(0.8)
        assert detector.confidence_threshold == 0.8
        assert detector.result_cache.size() == 0

        detector.update_confidence_threshold(5.0)
        assert detector.confidence_threshold == 1.0

        detector.update_confidence_threshold(-2.0)
        assert detector.confidence_threshold == 0.0


class TestLazySingletonAccessor:
    """Thread-safe lazy singleton for the original detector class."""

    def test_get_language_detector_returns_class_and_reuses_it(self) -> None:
        """The singleton resolves to LanguageDetector and is stable across calls."""
        first = cle._get_language_detector()
        second = cle._get_language_detector()

        assert first is LanguageDetector
        assert second is first


class TestOptimizedLanguageDetectorWrapper:
    """Drop-in wrapper delegation with dependency injection."""

    def test_pre_extracted_text_uses_dynamic_detection(self) -> None:
        """Pre-extracted text routes through the optimized detector only."""
        stub = _StubOriginalDetector()
        wrapper = OptimizedLanguageDetector(
            original_detector=stub, dynamic_detector=DynamicLanguageDetector()
        )

        result = wrapper.detect_language("book.pdf", pre_extracted_text=GERMAN_TEXT)

        assert result == "German"
        assert stub.calls == []

    def test_unknown_dynamic_result_falls_back_to_original(self) -> None:
        """Unknown optimized results fall back to file-based detection."""
        stub = _StubOriginalDetector()
        wrapper = OptimizedLanguageDetector(
            original_detector=stub, dynamic_detector=DynamicLanguageDetector()
        )

        result = wrapper.detect_language("book.pdf", pre_extracted_text="hi")

        assert result == "StubLanguage"
        assert stub.calls == [("book.pdf", None, "hi")]

    def test_missing_pre_extracted_text_goes_straight_to_original(self) -> None:
        """Without pre-extracted text the original detector is used directly."""
        stub = _StubOriginalDetector()
        wrapper = OptimizedLanguageDetector(
            original_detector=stub, dynamic_detector=DynamicLanguageDetector()
        )

        assert wrapper.detect_language("book.pdf") == "StubLanguage"
        assert stub.calls == [("book.pdf", None, None)]

    def test_text_based_detection_delegates_to_dynamic_detector(self) -> None:
        """detect_language_from_text uses the optimized engine."""
        wrapper = OptimizedLanguageDetector(
            original_detector=_StubOriginalDetector(),
            dynamic_detector=DynamicLanguageDetector(),
        )

        assert wrapper.detect_language_from_text(GERMAN_TEXT) == "German"

    def test_supported_languages_and_metrics_delegate(self) -> None:
        """Introspection helpers forward to the dynamic detector."""
        dynamic = DynamicLanguageDetector()
        wrapper = OptimizedLanguageDetector(
            original_detector=_StubOriginalDetector(), dynamic_detector=dynamic
        )

        assert wrapper.get_supported_languages() == dynamic.get_supported_languages()
        assert set(wrapper.get_performance_metrics()) == set(
            dynamic.get_performance_metrics()
        )

    def test_default_construction_builds_both_detectors_and_default_map(self) -> None:
        """Default wiring builds real detectors and adopts LANGUAGE_MAP."""
        wrapper = OptimizedLanguageDetector()

        assert isinstance(wrapper.original_detector, LanguageDetector)
        assert isinstance(wrapper.dynamic_detector, DynamicLanguageDetector)
        assert wrapper.language_map == LANGUAGE_MAP

    def test_explicit_language_map_is_preserved(self) -> None:
        """An injected language map replaces the module default."""
        wrapper = OptimizedLanguageDetector(
            original_detector=_StubOriginalDetector(),
            dynamic_detector=DynamicLanguageDetector(),
            language_map={"xx": "TestLang"},
        )

        assert wrapper.language_map == {"xx": "TestLang"}

    def test_clear_caches_tolerates_missing_memoize_attachment(self) -> None:
        """clear_caches skips the memoize hook when it is not attached."""
        detector = DynamicLanguageDetector()
        detector.result_cache.put(TextFingerprint.create("cache sweep").to_cache_key(), "German")

        def detached_cache_stub(*args: Any, **kwargs: Any) -> str:
            return "Unknown"

        detector.detect_language_optimized = detached_cache_stub

        detector.clear_caches()

        assert detector.result_cache.size() == 0


class TestDetectorRegistryFunctions:
    """Named-detector registry access helpers."""

    def test_register_and_get_custom_detector(self) -> None:
        """Registered factories build detectors with forwarded kwargs."""
        register_language_detector(
            "covgap-detector", lambda **kwargs: DynamicLanguageDetector(**kwargs)
        )

        detector = get_language_detector("covgap-detector", confidence_threshold=0.9)

        assert isinstance(detector, DynamicLanguageDetector)
        assert detector.confidence_threshold == 0.9

    def test_default_detector_shortcut_builds_new_detector(self) -> None:
        """The default name constructs a fresh detector."""
        detector = get_language_detector(min_text_length=12)

        assert isinstance(detector, DynamicLanguageDetector)
        assert detector.min_text_length == 12

    def test_unregistered_detector_name_raises_key_error(self) -> None:
        """Unknown registry names raise a descriptive KeyError."""
        with pytest.raises(KeyError, match=r"not registered"):
            get_language_detector("covgap-missing-detector")
