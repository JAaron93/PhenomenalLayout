"""Confidence Scoring Engine for neologism detection confidence calculation.

This module uses a set of baseline constants to estimate frequency- and
morphology-driven signals. The constants below are plugged into the
baseline formula used by ``_calculate_baseline_frequency`` and, in turn,
``_calculate_frequency_deviation``:

    base = DEFAULT_BASELINE_FREQ
    if is_compound:
        base *= COMPOUND_FREQ_FACTOR
    base *= max(LENGTH_PENALTY_MIN, 1.0 - len(term) / LENGTH_NORM_FACTOR)

Assumptions:
- Frequencies are relative proportions in the 0.0-1.0 range
- Compounds are typically rarer than simple forms
- Extremely long words should not be penalized without bound; clamp the
  penalty with a minimum factor

Tuning notes: Update the constants below rather than changing the
functions so downstream calculations remain consistent and easy to test.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Optional

from models.neologism_models import (
    ConfidenceFactors,
    MorphologicalAnalysis,
    PhilosophicalContext,
)

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Handles confidence scoring for neologism detection."""

    # Baseline frequency constants
    # DEFAULT_BASELINE_FREQ: relative frequency 0.0-1.0
    # - Meaning: expected baseline relative frequency for common words
    # - Example: 5e-5 ~ 50 occurrences per million tokens
    # - Rationale: conservative default when no corpus is available
    DEFAULT_BASELINE_FREQ: float = 5e-5

    # COMPOUND_FREQ_FACTOR: unitless multiplicative factor 0.0-1.0
    # - Meaning: compounds are rarer than simple forms
    # - Example: 0.2 means compounds are about 5x rarer
    # - Rationale: heuristic based on typical German compounding frequency
    COMPOUND_FREQ_FACTOR: float = 0.2

    # LENGTH_PENALTY_MIN: unitless multiplicative floor 0.0-1.0
    # - Meaning: minimum penalty factor for long words
    # - Example: never reduce baseline below 25% due to length alone
    # - Rationale: prevents unbounded penalization of very long words
    LENGTH_PENALTY_MIN: float = 0.25

    # LENGTH_NORM_FACTOR: length in characters
    # - Meaning: normalization scale for long-word penalty
    # - Example: words longer than ~30 chars hit the max length penalty
    # - Rationale: keeps length effect moderate and interpretable
    LENGTH_NORM_FACTOR: float = 30.0

    def __init__(
        self,
        philosophical_indicators: Optional[set[str]] = None,
        german_morphological_patterns: Optional[dict[str, list[str]]] = None,
        corpus_frequencies: Optional[dict[str, int]] = None,
        corpus_total_tokens: Optional[int] = None,
    ):
        """Initialize the confidence scorer.

        Args:
            philosophical_indicators: Set of philosophical indicator words
            german_morphological_patterns: German morphological patterns
                dictionary
            corpus_frequencies: Optional token frequency lookup for a
                background corpus (keys are lowercase tokens, values are
                counts)
            corpus_total_tokens: Optional total token count of the corpus.
        """
        # Normalize indicators to lowercase to enable case-insensitive checks
        self.philosophical_indicators = {
            s.lower() for s in (philosophical_indicators or set())
        }
        self.german_morphological_patterns = (
            german_morphological_patterns or self._load_default_patterns()
        )
        self._corpus_freq = corpus_frequencies or {}
        self._corpus_total = (
            corpus_total_tokens
            if corpus_total_tokens is not None
            else int(sum(self._corpus_freq.values()))
        )

        logger.info("ConfidenceScorer initialized")

    def _load_default_patterns(self) -> dict[str, list[str]]:
        """Load default German morphological patterns."""
        from utils.language_utils import get_german_morphological_patterns
        return get_german_morphological_patterns()

    def calculate_confidence_factors(
        self,
        term: str,
        morphological: MorphologicalAnalysis,
        philosophical: PhilosophicalContext,
    ) -> ConfidenceFactors:
        """Calculate individual confidence factors."""
        factors = ConfidenceFactors()

        # Morphological factors
        factors.morphological_complexity = morphological.structural_complexity
        factors.compound_structure_score = 0.8 if morphological.is_compound else 0.2
        factors.morphological_productivity = morphological.morphological_productivity

        # Context factors
        factors.context_density = philosophical.philosophical_density
        factors.philosophical_indicators = min(
            1.0, len(philosophical.philosophical_keywords) / 5.0
        )
        factors.semantic_coherence = (
            0.7 if philosophical.semantic_field != "general" else 0.3
        )

        # Frequency factors (simplified - would need corpus analysis for full
        # implementation)
        factors.rarity_score = self._calculate_rarity_score(term)
        # Corpus-based frequency deviation (with graceful fallback)
        factors.frequency_deviation = self._calculate_frequency_deviation(
            term,
            morphological,
        )
        factors.corpus_novelty = 0.8 if len(term) > 12 else 0.4

        # Pattern factors
        factors.known_patterns = self._calculate_pattern_score(
            term,
            morphological,
        )
        factors.pattern_productivity = 0.7 if morphological.is_compound else 0.4
        factors.structural_regularity = 0.8 if morphological.compound_pattern else 0.5

        # Linguistic factors
        factors.phonological_plausibility = self._calculate_phonological_plausibility(
            term
        )
        # Heuristic syntactic integration estimation
        factors.syntactic_integration = self._estimate_syntactic_integration(
            term,
            morphological,
        )
        factors.semantic_transparency = 0.6 if morphological.is_compound else 0.4

        return factors

    def _calculate_rarity_score(self, term: str) -> float:
        """Calculate rarity score for a term."""
        # Simplified rarity calculation
        # In a full implementation, this would check against frequency corpora

        # Length-based rarity (longer words are typically rarer)
        length_score = min(1.0, len(term) / 20.0)

        # Compound rarity (compounds are typically rarer)
        compound_score = 0.3 if self._is_compound_word(term) else 0.0

        # Abstract suffix rarity
        abstract_score = 0.0
        for suffix in self.german_morphological_patterns["abstract_suffixes"]:
            if term.lower().endswith(suffix):
                abstract_score = 0.4
                break

        return min(1.0, length_score + compound_score + abstract_score)

    # ---------------- Frequency and syntax helpers -----------------

    def update_corpus_frequencies(
        self, freq: dict[str, int], total_tokens: Optional[int] = None
    ) -> None:
        """Replace corpus frequency data used for frequency-based signals.

        Args:
            freq: Mapping of lowercase tokens to counts.
            total_tokens: Optional explicit total token count. If omitted,
                the sum of counts is used.
        """
        self._corpus_freq = freq
        self._corpus_total = (
            total_tokens if total_tokens is not None else int(sum(freq.values()))
        )

    def _relative_frequency(self, token: str) -> float:
        """Return relative frequency of token from corpus (0.0-1.0).

        Falls back to 0 when corpus is unavailable.
        """
        if not self._corpus_freq or self._corpus_total <= 0:
            return 0.0
        count = float(self._corpus_freq.get(token.lower(), 0))
        return count / self._corpus_total

    def _calculate_baseline_frequency(
        self, term: str, morphological: MorphologicalAnalysis
    ) -> float:
        """Calculate expected baseline frequency based on morphology.

        Returns a baseline relative frequency in the range [0.0, 1.0].
        """
        base = self.DEFAULT_BASELINE_FREQ
        if morphological.is_compound:
            base *= self.COMPOUND_FREQ_FACTOR
        base *= max(
            self.LENGTH_PENALTY_MIN,
            1.0 - (len(term) / self.LENGTH_NORM_FACTOR),
        )
        return base

    def _calculate_frequency_deviation(
        self, term: str, morphological: MorphologicalAnalysis
    ) -> float:
        """Estimate frequency deviation using an optional corpus.

        The idea: compare observed relative frequency with a simple baseline
        expected frequency derived from morphological cues (compounds occur
        less frequently than simple forms). We compute the absolute
        log-scale difference and normalize to [0, 1].
        """
        rel = self._relative_frequency(term)
        # Baseline expectation by morphology and length (very rough)
        base = self._calculate_baseline_frequency(term, morphological)

        eps = 1e-12
        # Log-ratio distance; larger distance => higher deviation
        distance = abs(math.log10((rel + eps) / (base + eps)))
        # Normalize: distances > 6 treated as max deviation
        score = min(1.0, distance / 6.0)
        return float(max(0.0, score))

    def _estimate_syntactic_integration(
        self, term: str, morphological: MorphologicalAnalysis
    ) -> float:
        """Estimate syntactic integration without full parser context.

        Heuristics for German:
        - Noun-like capitalization and abstract noun suffixes improve score
        - Valid compound/linking patterns improve score
        - Digits/symbols or excessive punctuation reduce score
        """
        score = 0.5
        # Noun capitalization (German)
        if term[:1].isupper():
            score += 0.15
        # Abstract noun suffixes
        if any(
            term.lower().endswith(suf)
            for suf in self.german_morphological_patterns["abstract_suffixes"]
        ):
            score += 0.1
        # Compound/linking patterns
        if morphological.is_compound or morphological.compound_pattern:
            score += 0.1
        # Penalize digits/symbols (less likely in standard lexical items)
        if re.search(r"[\d_@#*]", term):
            score -= 0.2
        # Penalize excessive internal punctuation
        hyphen_count = term.count("-")
        if hyphen_count >= 2:
            score -= 0.1
        return max(0.0, min(1.0, score))

    def _is_compound_word(self, word: str) -> bool:
        """Check if word appears to be a German compound."""
        if len(word) < 8:
            return False

        # Check for multiple capital letters (German noun compounds)
        capital_count = sum(1 for c in word if c.isupper())
        if capital_count >= 2:
            return True

        # Check for common compound patterns
        compound_patterns = [
            # Standard compound linking
            r"\w+(?:s|n|es|en|er|e|ns|ts)\w+",
            # Philosophical compounds
            r"\w+(?:bewusstsein|wirklichkeit|erkenntnis|wahrnehmung)",
            # Philosophical prefix compounds
            r"(?:welt|lebens|seins|geist|seele)\w+",
        ]

        for pattern in compound_patterns:
            if re.search(pattern, word.lower()):
                return True

        return False

    def _calculate_pattern_score(
        self, term: str, morphological: MorphologicalAnalysis
    ) -> float:
        """Calculate pattern recognition score."""
        score = 0.0

        # Known morphological patterns
        if morphological.is_compound:
            score += 0.4

        if morphological.prefixes:
            score += 0.3

        if morphological.suffixes:
            score += 0.3

        # Philosophical term patterns
        term_lower = term.lower()
        if any(indicator in term_lower for indicator in self.philosophical_indicators):
            score += 0.4

        return min(1.0, score)

    def _calculate_phonological_plausibility(self, term: str) -> float:
        """Calculate phonological plausibility for German."""
        # Simplified phonological analysis
        # In a full implementation, this would use proper phonological rules

        score = 0.5  # Base score

        # Check for common German phonological patterns
        if re.search(r"[aeiouäöü]", term.lower()):
            score += 0.2  # Contains vowels

        # Check for problematic consonant clusters
        if re.search(
            r"[bcdfghjklmnpqrstvwxyz]{4,}",
            term.lower(),
        ):
            score -= 0.3  # Too many consecutive consonants

        # Check for typical German sounds
        if re.search(
            r"(?:sch|ch|th|pf|tz)",
            term.lower(),
        ):
            score += 0.1  # Contains German sound patterns

        return max(0.0, min(1.0, score))

    def calculate_final_confidence(self, factors: ConfidenceFactors) -> float:
        """Calculate final confidence score from factors."""
        return factors.calculate_weighted_score()

    def get_confidence_breakdown(self, factors: ConfidenceFactors) -> dict[str, float]:
        """Get detailed breakdown of confidence calculation."""
        # Calculate individual category scores
        morphological_score = (
            factors.morphological_complexity * 0.4
            + factors.compound_structure_score * 0.4
            + factors.morphological_productivity * 0.2
        )

        context_score = (
            factors.context_density * 0.4
            + factors.philosophical_indicators * 0.4
            + factors.semantic_coherence * 0.2
        )

        frequency_score = (
            factors.rarity_score * 0.5
            + factors.frequency_deviation * 0.3
            + factors.corpus_novelty * 0.2
        )

        pattern_score = (
            factors.known_patterns * 0.4
            + factors.pattern_productivity * 0.3
            + factors.structural_regularity * 0.3
        )

        linguistic_score = (
            factors.phonological_plausibility * 0.4
            + factors.syntactic_integration * 0.3
            + factors.semantic_transparency * 0.3
        )

        return {
            "morphological": morphological_score,
            "context": context_score,
            "frequency": frequency_score,
            "pattern": pattern_score,
            "linguistic": linguistic_score,
            "final": factors.calculate_weighted_score(),
        }

    def adjust_confidence_threshold(
        self, base_threshold: float, context_factors: dict[str, Any]
    ) -> float:
        """Adjust confidence threshold based on context factors."""
        adjusted = base_threshold

        # Adjust based on text genre
        if context_factors.get("text_genre") == "philosophical":
            adjusted -= 0.1  # Lower threshold for philosophical texts

        # Adjust based on philosophical density
        philosophical_density = context_factors.get(
            "philosophical_density",
            0.0,
        )
        if philosophical_density > 0.5:
            # Lower threshold for high philosophical density
            adjusted -= 0.05

        # Adjust based on author context
        known_authors = [
            "klages",
            "heidegger",
            "nietzsche",
        ]
        if context_factors.get("author_context") in known_authors:
            # Lower threshold for known philosophical authors
            adjusted -= 0.05

        return max(0.1, min(0.9, adjusted))  # Keep within reasonable bounds

    def validate_confidence_factors(self, factors: ConfidenceFactors) -> bool:
        """Validate that confidence factors are within expected ranges."""
        factor_values = [
            factors.morphological_complexity,
            factors.compound_structure_score,
            factors.morphological_productivity,
            factors.context_density,
            factors.philosophical_indicators,
            factors.semantic_coherence,
            factors.rarity_score,
            factors.frequency_deviation,
            factors.corpus_novelty,
            factors.known_patterns,
            factors.pattern_productivity,
            factors.structural_regularity,
            factors.phonological_plausibility,
            factors.syntactic_integration,
            factors.semantic_transparency,
        ]

        # Check that all factors are in valid range [0.0, 1.0]
        return all(0.0 <= value <= 1.0 for value in factor_values)

    def update_patterns(self, new_patterns: dict[str, list[str]]) -> None:
        """Update morphological patterns."""
        self.german_morphological_patterns.update(new_patterns)
        logger.info("Updated morphological patterns")

    def update_philosophical_indicators(self, new_indicators: set[str]) -> None:
        """Update philosophical indicators."""
        # Normalize to lowercase on ingestion to keep comparisons
        # case-insensitive throughout the scorer
        self.philosophical_indicators.update({s.lower() for s in new_indicators})
        logger.info(
            "Updated philosophical indicators with %d new terms",
            len(new_indicators),
        )
