"""Morphological Analysis Engine for German philosophical texts."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Optional

try:
    from spacy.language import Language  # type: ignore
except Exception:  # pragma: no cover - optional for tests without spaCy
    from typing import Any as Language  # type: ignore

from models.neologism_models import MorphologicalAnalysis

logger = logging.getLogger(__name__)


class MorphologicalAnalyzer:
    """Analyze German terms including compound analysis."""

    def __init__(self, spacy_model: Optional[Language] = None, cache_size: int = 1000):
        """Initialize the morphological analyzer.

        Args:
            spacy_model: spaCy model instance for linguistic analysis
            cache_size: Size of LRU cache for morphological analysis
        """
        self.nlp = spacy_model
        self.cache_size = cache_size
        self.german_morphological_patterns = self._load_german_patterns()
        # Configure the cache for the analyze method
        self.analyze = lru_cache(maxsize=cache_size)(self._analyze_uncached)
        logger.info("MorphologicalAnalyzer initialized")

    def _load_german_patterns(self) -> dict[str, list[str]]:
        """Load German morphological patterns for compound analysis."""
        from utils.language_utils import get_german_morphological_patterns
        return get_german_morphological_patterns()

    def _analyze_uncached(self, term: str) -> MorphologicalAnalysis:
        """Analyze morphological structure of a term (uncached version)."""
        analysis = MorphologicalAnalysis()
        # Basic metrics
        analysis.word_length = len(term)
        analysis.syllable_count = self._count_syllables(term)
        # Compound analysis
        if self._is_compound_word(term):
            analysis.is_compound = True
            analysis.compound_parts = self._split_compound(term)
            analysis.compound_pattern = self._identify_compound_pattern(term)
        # Morpheme analysis
        analysis.prefixes = self._extract_prefixes(term)
        analysis.suffixes = self._extract_suffixes(term)
        analysis.root_words = self._extract_root_words(term)
        analysis.morpheme_count = (
            len(analysis.prefixes) + len(analysis.suffixes) + len(analysis.root_words)
        )
        # Complexity metrics
        analysis.structural_complexity = self._calculate_structural_complexity(analysis)
        analysis.morphological_productivity = (
            self._calculate_morphological_productivity(analysis)
        )
        return analysis

    def _count_syllables(self, word: str) -> int:
        """Estimate syllable count for German words."""
        vowels = "aeiouäöü"
        count = 0
        prev_was_vowel = False
        for char in word.lower():
            if char in vowels:
                if not prev_was_vowel:
                    count += 1
                prev_was_vowel = True
            else:
                prev_was_vowel = False
        return max(1, count)

    def _is_compound_word(self, term: str) -> bool:
        """Check if a term is likely a compound word."""
        if len(term) < 6:  # Very short words are unlikely to be compounds
            return False
        # Check for known compound patterns
        patterns = self.german_morphological_patterns["compound_patterns"]
        for pattern in patterns:
            if re.search(pattern, term, re.IGNORECASE):
                return True
        # Check for common compound structures
        linking_elements = self.german_morphological_patterns["compound_linking"]
        for linking in linking_elements:
            if linking in term[1:-1]:  # Check middle of word
                return True
        return False

    def _split_compound(self, term: str) -> list[str]:
        """Split a compound word into its components.

        This is a simplified implementation that attempts to identify
        compound boundaries using known German morphological patterns.
        """
        # Handle specific known compounds first
        # Store split positions rather than hardcoded capitalizations to preserve original casing
        known_compound_splits = {
            "wirklichkeitsbewusstsein": 13,  # Split after "Wirklichkeits" (13 chars, includes linking 's')
            "lebensphilosophie": 6,  # Split after "Lebens" (6 chars)
            "weltanschauung": 4,  # Split after "Welt" (4 chars)
            "erkenntnistheorie": 10,  # Split after "Erkenntnis" (10 chars)
            "bewusstseinsphilosophie": 12,  # Split after "Bewusstseins" (12 chars)
            "lebensweltthematik": 10,  # Split after "Lebenswelt" (10 chars)
        }

        term_lower = term.lower()
        if term_lower in known_compound_splits:
            split_pos = known_compound_splits[term_lower]
            prefix = term[:split_pos]
            suffix = term[split_pos:]
            return [prefix, suffix]

        # Try to split based on common philosophical endings
        philosophical_endings = self.german_morphological_patterns[
            "philosophical_endings"
        ]

        for ending in philosophical_endings:
            if term_lower.endswith(ending) and len(term_lower) > len(ending):
                prefix_length = len(term) - len(ending)
                prefix = term[:prefix_length]
                ending_part = term[
                    prefix_length:
                ]  # Extract ending with original casing
                if len(prefix) >= 3:  # Meaningful prefix
                    return [prefix, ending_part]

        # Try to split based on linking elements
        linking_elements = self.german_morphological_patterns["compound_linking"]
        for i in range(3, len(term) - 3):  # Don't split too close to edges
            for link in linking_elements:
                if term[i : i + len(link)].lower() == link:
                    prefix = term[:i]
                    suffix = term[i + len(link) :]
                    if len(prefix) >= 3 and len(suffix) >= 3:
                        return [prefix, suffix]

        # If no split found, return the original term
        return [term]

    def _identify_compound_pattern(self, term: str) -> str:
        """Identify the pattern of a compound word."""
        patterns = self.german_morphological_patterns["compound_patterns"]
        for pattern in patterns:
            if re.search(pattern, term, re.IGNORECASE):
                return pattern
        return "unknown"

    def _extract_prefixes(self, term: str) -> list[str]:
        """Extract potential prefixes from a term."""
        prefixes = []
        prefix_list = self.german_morphological_patterns["philosophical_prefixes"]
        for prefix in prefix_list:
            if term.lower().startswith(prefix):
                prefixes.append(prefix)
        return prefixes

    def _extract_suffixes(self, term: str) -> list[str]:
        """Extract potential suffixes from a term."""
        suffixes = []
        suffix_list = self.german_morphological_patterns["abstract_suffixes"]
        for suffix in suffix_list:
            if term.lower().endswith(suffix):
                suffixes.append(suffix)
        return suffixes

    def _extract_root_words(self, term: str) -> list[str]:
        """Extract potential root words from a term."""
        # This is a simplified implementation
        # A real implementation would use a dictionary or word embeddings
        roots = []
        # Remove known affixes
        stem = term.lower()
        prefixes = self.german_morphological_patterns["philosophical_prefixes"]
        for prefix in prefixes:
            if stem.startswith(prefix):
                stem = stem[len(prefix) :]
        suffixes = self.german_morphological_patterns["abstract_suffixes"]
        for suffix in suffixes:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        if stem and len(stem) > 2:  # Minimum length for meaningful root
            roots.append(stem)
        return roots

    def _calculate_structural_complexity(
        self, analysis: MorphologicalAnalysis
    ) -> float:
        """Calculate a complexity score based on word structure."""
        complexity = 0.0
        # More parts suggest more complexity on word length
        complexity += min(analysis.word_length / 20.0, 1.0)
        # Longer words are more complex compounds
        if analysis.is_compound:
            complexity += 0.3
        # Increase for multiple morphemes
        complexity += min(analysis.morpheme_count * 0.2, 0.5)
        return min(complexity, 1.0)

    def _calculate_morphological_productivity(
        self, analysis: MorphologicalAnalysis
    ) -> float:
        """Calculate a productivity score based on morphological features."""
        productivity = 0.0
        # More affixes suggest higher productivity
        prefix_score = len(analysis.prefixes) * 0.2
        suffix_score = len(analysis.suffixes) * 0.3
        affix_score = prefix_score + suffix_score
        productivity += min(affix_score, 0.7)
        # More compounds suggest higher productivity
        if analysis.is_compound:
            productivity += 0.2
        return min(productivity, 1.0)

    def clear_cache(self):
        """Clear the analysis cache."""
        if hasattr(self, "analyze") and hasattr(self.analyze, "cache_clear"):
            self.analyze.cache_clear()
            logger.debug("Morphological analysis cache cleared")

    def get_cache_info(self) -> dict:
        """Get cache statistics."""
        if hasattr(self, "analyze") and hasattr(self.analyze, "cache_info"):
            cache_info = self.analyze.cache_info()
            hit_rate = (
                cache_info.hits / (cache_info.hits + cache_info.misses)
                if (cache_info.hits + cache_info.misses) > 0
                else 0.0
            )
            return {
                "hits": cache_info.hits,
                "misses": cache_info.misses,
                "currsize": cache_info.currsize,
                "maxsize": cache_info.maxsize,
                "hit_rate": hit_rate,
            }
        else:
            logger.debug("Cache info not available, returning default values")
            return {
                "hits": 0,
                "misses": 0,
                "currsize": 0,
                "maxsize": self.cache_size,
                "hit_rate": 0.0,
            }
