"""Morphological Analysis Engine for German philosophical texts."""

from __future__ import annotations

import logging
import re
from functools import lru_cache

from spacy.language import Language

from models.neologism_models import MorphologicalAnalysis

logger = logging.getLogger(__name__)


class MorphologicalAnalyzer:
    """Analyze German terms including compound analysis."""

    def __init__(self, spacy_model: Language | None = None, cache_size: int = 1000):
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
        return {
            "compound_linking": ["s", "n", "es", "en", "er", "e", "ns", "ts"],
            "philosophical_prefixes": [
                "vor",
                "nach",
                "über",
                "unter",
                "zwischen",
                "gegen",
                "mit",
                "ur",
                "proto",
                "meta",
                "anti",
                "pseudo",
                "neo",
                "para",
            ],
            "abstract_suffixes": [
                "heit",
                "keit",
                "ung",
                "schaft",
                "tum",
                "nis",
                "sal",
                "ismus",
                "ität",
                "ation",
                "logie",
                "sophie",
            ],
            "compound_patterns": [
                r"\w+(?:s|n|es|en|er|e|ns|ts)\w+",
                r"\w+(?:bewusstsein|wirklichkeit|erkenntnis|wahrnehmung)",
                r"(?:welt|lebens|seins|geist|seele)\w+",
            ],
        }

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
        for pattern in self.german_morphological_patterns["compound_patterns"]:
            if re.search(pattern, term, re.IGNORECASE):
                return True
        # Check for common compound structures
        for linking in self.german_morphological_patterns["compound_linking"]:
            if linking in term[1:-1]:  # Check middle of word
                return True
        return False

    def _split_compound(self, term: str) -> list[str]:
        """Split a compound word into its components."""
        # This is a simplified implementation
        # A more sophisticated approach would use a dictionary
        parts = []
        current = term
        while len(current) > 3:  # Minimum length for meaningful parts
            found = False
            # Check for known prefixes
            prefixes = self.german_morphological_patterns["philosophical_prefixes"]
            for prefix in prefixes:
                if current.lower().startswith(prefix):
                    parts.append(prefix)
                    current = current[len(prefix) :]
                    found = True
                    break
            # Check for linking elements
            if not found:
                linking = self.german_morphological_patterns["compound_linking"]
                for link in linking:
                    if current.lower().startswith(link):
                        current = current[len(link) :]
                        found = True
                        break
            # Check for suffixes
            if not found:
                suffixes = self.german_morphological_patterns["abstract_suffixes"]
                for suffix in suffixes:
                    if current.lower().endswith(suffix):
                        parts.append(current)
                        current = ""
                        found = True
                        break
            if not found:
                break
        if current:  # Add remaining part
            parts.append(current)
        return parts

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
        # Word length contributes to complexity
        complexity += min(analysis.word_length / 20.0, 1.0)
        # Compounds increase complexity
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
        # More affixes suggest higher productivity from affixes
        prefix_score = len(analysis.prefixes) * 0.2
        suffix_score = len(analysis.suffixes) * 0.3
        affix_score = prefix_score + suffix_score
        productivity += min(affix_score, 0.7)
        # Compounds suggest higher productivity
        if analysis.is_compound:
            productivity += 0.2
        return min(productivity, 1.0)

    def clear_cache(self):
        """Clear the analysis cache."""
        if hasattr(self, "analyze") and hasattr(self.analyze, "cache_clear"):
            self.analyze.cache_clear()
            logger.debug("Morphological analysis cache cleared")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clear cache."""
        self.clear_cache()
        return False
