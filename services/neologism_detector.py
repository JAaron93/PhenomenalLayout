"""Neologism Detection Engine for philosophy-focused translation."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Import spaCy for German linguistic analysis
try:
    import spacy  # type: ignore

    SPACY_AVAILABLE = True
except ImportError:
    spacy = None  # type: ignore
    SPACY_AVAILABLE = False

# Import our data models
from models.neologism_models import (
    ConfidenceFactors,
    DetectedNeologism,
    MorphologicalAnalysis,
    NeologismAnalysis,
    NeologismType,
    PhilosophicalContext,
)
from services.confidence_scorer import ConfidenceScorer

# Import the new component classes
from services.morphological_analyzer import MorphologicalAnalyzer
from services.philosophical_context_analyzer import PhilosophicalContextAnalyzer

logger = logging.getLogger(__name__)


class NeologismDetector:
    """Core neologism detection engine with German morphological analysis."""

    def __init__(
        self,
        terminology_path: Optional[str] = None,
        spacy_model: str = "de_core_news_sm",
        cache_size: int = 1000,
        philosophical_threshold: float = 0.3,
        morphological_analyzer: Optional[MorphologicalAnalyzer] = None,
        philosophical_context_analyzer: Optional[PhilosophicalContextAnalyzer] = None,
        confidence_scorer: Optional[ConfidenceScorer] = None,
    ):
        """Initialize the neologism detector.

        Args:
            terminology_path: Path to terminology JSON file
            spacy_model: Name of spaCy German model to use
            cache_size: Size of LRU cache for morphological analysis
            philosophical_threshold: Minimum philosophical density for
                detection
            morphological_analyzer: Optional MorphologicalAnalyzer instance
                (for dependency injection)
            philosophical_context_analyzer: Optional
                PhilosophicalContextAnalyzer instance
            confidence_scorer: Optional ConfidenceScorer instance
        """
        self.terminology_path = terminology_path
        self.spacy_model = spacy_model
        self.cache_size = cache_size
        self.philosophical_threshold = philosophical_threshold

        # Lazy loading attributes - models are loaded only when first accessed
        self._nlp = None
        self._nlp_lock = threading.Lock()
        self._terminology_map = None
        self._philosophical_indicators = None
        self._german_morphological_patterns = None

        # Component analyzers with dependency injection support
        self._morphological_analyzer = morphological_analyzer
        self._philosophical_context_analyzer = philosophical_context_analyzer
        self._confidence_scorer = confidence_scorer

        # Statistics tracking
        self.total_analyses = 0

        logger.info(
            f"NeologismDetector initialized with lazy loading for model: {spacy_model}"
        )

    @property
    def nlp(self) -> Optional[Any]:
        """Lazy loading property for spaCy model with thread safety."""
        if self._nlp is None:
            with self._nlp_lock:
                if self._nlp is None:  # Double-check locking pattern
                    self._nlp = self._initialize_spacy_model()
                    logger.info(f"Lazy-loaded spaCy model: {self.spacy_model}")
        return self._nlp

    @property
    def terminology_map(self) -> dict[str, str]:
        """Lazy loading property for terminology mapping."""
        if self._terminology_map is None:
            self._terminology_map = self._load_terminology()
        return self._terminology_map

    @property
    def philosophical_indicators(self) -> set[str]:
        """Lazy loading property for philosophical indicators."""
        if self._philosophical_indicators is None:
            self._philosophical_indicators = self._load_philosophical_indicators()
        return self._philosophical_indicators

    @property
    def german_morphological_patterns(self) -> dict[str, list[str]]:
        """Lazy loading property for German morphological patterns."""
        if self._german_morphological_patterns is None:
            self._german_morphological_patterns = self._load_german_patterns()
        return self._german_morphological_patterns

    @property
    def morphological_analyzer(self) -> MorphologicalAnalyzer:
        """Lazy loading property for morphological analyzer."""
        if self._morphological_analyzer is None:
            self._morphological_analyzer = MorphologicalAnalyzer(
                spacy_model=self.nlp, cache_size=self.cache_size
            )
        return self._morphological_analyzer

    @property
    def philosophical_context_analyzer(self) -> PhilosophicalContextAnalyzer:
        """Lazy loading property for philosophical context analyzer."""
        if self._philosophical_context_analyzer is None:
            self._philosophical_context_analyzer = PhilosophicalContextAnalyzer(
                spacy_model=self.nlp, terminology_map=self.terminology_map
            )
        return self._philosophical_context_analyzer

    @property
    def confidence_scorer(self) -> ConfidenceScorer:
        """Lazy loading property for confidence scorer."""
        if self._confidence_scorer is None:
            self._confidence_scorer = ConfidenceScorer(
                philosophical_indicators=self.philosophical_indicators,
                german_morphological_patterns=self.german_morphological_patterns,
            )
        return self._confidence_scorer

    def _initialize_spacy_model(self) -> Optional[Any]:
        """Initialize spaCy German model for linguistic analysis."""
        if not SPACY_AVAILABLE:
            logger.warning(
                "spaCy not available, morphological analysis will be limited"
            )
            return None

        try:
            # Try to load the specified model
            nlp = spacy.load(self.spacy_model)
            logger.info(f"Loaded spaCy model: {self.spacy_model}")
            return nlp
        except OSError:
            logger.warning(
                f"spaCy model '{self.spacy_model}' not found, trying fallback"
            )
            try:
                # Try basic German model
                nlp = spacy.load("de_core_news_sm")
                logger.info("Loaded fallback spaCy model: de_core_news_sm")
                return nlp
            except OSError:
                logger.warning(
                    "No German spaCy model available, using linguistic fallback"
                )
                return None

    def _load_terminology(self) -> dict[str, str]:
        """Load terminology mapping from JSON file."""
        terminology: dict[str, str] = {}

        if self.terminology_path and Path(self.terminology_path).exists():
            try:
                with open(self.terminology_path, encoding="utf-8") as f:
                    terminology = json.load(f)
                logger.info(f"Loaded {len(terminology)} terminology entries")
            except Exception as e:
                logger.error(f"Error loading terminology: {e}")
                return {}
        elif not self.terminology_path:
            # Only load default terminology when no explicit path was provided
            try:
                klages_path = (
                    Path(__file__).parent.parent / "config" / "klages_terminology.json"
                )
                if klages_path.exists():
                    with open(klages_path, encoding="utf-8") as f:
                        terminology = json.load(f)
                    logger.info(
                        f"Loaded default Klages terminology: {len(terminology)} entries"
                    )
            except Exception as e:
                logger.warning(f"Could not load Klages terminology: {e}")

        return terminology

    def _load_philosophical_indicators(self) -> set[str]:
        """Load philosophical indicator words and patterns."""
        indicators = {
            # Core philosophical terms
            "philosophie",
            "metaphysik",
            "ontologie",
            "epistemologie",
            "ethik",
            "ästhetik",
            "logik",
            "dialektik",
            "hermeneutik",
            "phänomenologie",
            # Conceptual terms
            "begriff",
            "konzept",
            "idee",
            "prinzip",
            "kategorie",
            "struktur",
            "system",
            "methode",
            "theorie",
            "hypothese",
            "thesis",
            "antithesis",
            # Existence and being
            "sein",
            "dasein",
            "existenz",
            "wesen",
            "substanz",
            "realität",
            "wirklichkeit",
            "erscheinung",
            "phänomen",
            "noumen",
            # Consciousness and mind
            "bewusstsein",
            "geist",
            "seele",
            "psyche",
            "verstand",
            "vernunft",
            "intellekt",
            "intuition",
            "erkenntnis",
            "wahrnehmung",
            "anschauung",
            # Value and meaning
            "wert",
            "bedeutung",
            "sinn",
            "zweck",
            "ziel",
            "ideal",
            "norm",
            "gut",
            "böse",
            "schön",
            "hässlich",
            "wahr",
            "falsch",
            # Temporal and spatial
            "zeit",
            "raum",
            "ewigkeit",
            "unendlichkeit",
            "endlichkeit",
            "temporal",
            "spatial",
            "chronos",
            "kairos",
            # Abstract relations
            "relation",
            "verhältnis",
            "beziehung",
            "zusammenhang",
            "einheit",
            "vielheit",
            "identität",
            "differenz",
            "ähnlichkeit",
            "verschiedenheit",
            # Specific philosophical movements
            "idealismus",
            "materialismus",
            "empirismus",
            "rationalismus",
            "kritizismus",
            "positivismus",
            "existentialismus",
            "nihilismus",
        }

        # Add terminology terms as indicators (avoid circular dependency)
        # Only add if terminology is already loaded, don't trigger lazy loading
        if self._terminology_map is not None:
            indicators.update(term.lower() for term in self._terminology_map.keys())

        return indicators

    def _load_german_patterns(self) -> dict[str, list[str]]:
        """Load German morphological patterns for compound analysis."""
        from utils.language_utils import get_german_morphological_patterns
        return get_german_morphological_patterns()

    def analyze_text(
        self, text: str, text_id: str = "unknown", chunk_size: int = 2000
    ) -> NeologismAnalysis:
        """Analyze text for neologisms with comprehensive detection.

        Args:
            text: Input text to analyze
            text_id: Identifier for the text
            chunk_size: Size of text chunks for processing

        Returns:
            NeologismAnalysis with detected neologisms and statistics
        """
        start_time = time.time()

        # Initialize analysis
        analysis = NeologismAnalysis(
            text_id=text_id,
            analysis_timestamp=datetime.now().isoformat(),
            total_tokens=len(text.split()),
            analyzed_chunks=0,
        )

        try:
            # Process text in chunks for memory efficiency
            chunks = self._chunk_text(text, chunk_size)
            analysis.analyzed_chunks = len(chunks)

            for chunk_idx, chunk in enumerate(chunks):
                chunk_neologisms = self._analyze_chunk(chunk)

                for neologism in chunk_neologisms:
                    neologism.source_text_id = text_id
                    analysis.add_detection(neologism)

            # Calculate analysis quality metrics
            analysis.analysis_quality = self._calculate_analysis_quality(analysis)
            analysis.coverage_ratio = self._calculate_coverage_ratio(analysis, text)

            # Update semantic fields and concepts
            analysis.semantic_fields = self._extract_semantic_fields(analysis)
            analysis.dominant_concepts = self._extract_dominant_concepts(analysis)

        except Exception as e:
            logger.error(f"Error in text analysis: {e}")
            analysis.analysis_quality = 0.0

        finally:
            analysis.processing_time = time.time() - start_time
            # Get cache info from morphological analyzer
            cache_info = self.morphological_analyzer.get_cache_info()
            analysis.cache_hits = cache_info["hits"]
            self.total_analyses += 1

        logger.info(
            f"Analyzed text '{text_id}': {analysis.total_detections} "
            f"neologisms detected"
        )
        return analysis

    def _chunk_text(self, text: str, chunk_size: int) -> list[str]:
        """Split text into chunks while preserving sentence boundaries."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        sentences = self._split_sentences(text)

        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences using spaCy or regex fallback."""
        if self.nlp:
            doc = self.nlp(text)
            return [sent.text for sent in doc.sents]
        else:
            # Fallback sentence splitting that preserves punctuation
            parts = re.split(r"([.!?]+\s*)", text)
            sentences: list[str] = []
            current = ""
            for part in parts:
                if re.match(r"[.!?]+\s*", part):
                    current += part
                    sentences.append(current.strip())
                    current = ""
                else:
                    current += part
            if current.strip():
                sentences.append(current.strip())
            return sentences

    def _analyze_chunk(self, chunk: str) -> list[DetectedNeologism]:
        """Analyze a text chunk for neologisms."""
        neologisms = []

        # Extract candidate terms
        candidates = self._extract_candidates(chunk)

        for candidate in candidates:
            # Check if already known terminology
            if candidate.term.lower() in self.terminology_map:
                continue

            # Perform morphological analysis
            morphological_analysis = self._analyze_morphology(candidate.term)

            # Analyze philosophical context
            philosophical_context = self._analyze_philosophical_context(
                candidate.term, chunk, candidate.start_pos, candidate.end_pos
            )

            # Calculate confidence factors
            confidence_factors = self._calculate_confidence_factors(
                candidate.term, morphological_analysis, philosophical_context
            )

            # Determine if it's a neologism based on confidence
            confidence_score = confidence_factors.calculate_weighted_score()

            if confidence_score >= self.philosophical_threshold:
                neologism = DetectedNeologism(
                    term=candidate.term,
                    confidence=confidence_score,
                    neologism_type=self._classify_neologism_type(
                        morphological_analysis
                    ),
                    start_pos=candidate.start_pos,
                    end_pos=candidate.end_pos,
                    sentence_context=candidate.sentence_context,
                    morphological_analysis=morphological_analysis,
                    philosophical_context=philosophical_context,
                    confidence_factors=confidence_factors,
                    detection_timestamp=datetime.now().isoformat(),
                )

                neologisms.append(neologism)

        return neologisms

    @dataclass
    class CandidateTerm:
        """Temporary structure for candidate terms."""

        term: str
        start_pos: int
        end_pos: int
        sentence_context: str

    def _extract_candidates(self, text: str) -> list[CandidateTerm]:
        """Extract candidate terms from text for neologism analysis."""
        candidates = []

        if self.nlp:
            doc = self.nlp(text)

            for token in doc:
                # Skip short words, punctuation, and common words
                if (
                    len(token.text) < 6
                    or token.is_punct
                    or token.is_stop
                    or token.like_num
                ):
                    continue

                # Focus on nouns and complex words
                if token.pos_ in ["NOUN", "PROPN"] or self._is_compound_word(
                    token.text
                ):
                    sentence_context = token.sent.text if token.sent else text

                    candidates.append(
                        self.CandidateTerm(
                            term=token.text,
                            start_pos=token.idx,
                            end_pos=token.idx + len(token.text),
                            sentence_context=sentence_context,
                        )
                    )
        else:
            # Fallback extraction using regex
            candidates = self._extract_candidates_regex(text)

        return candidates

    def get_compound_patterns(self) -> list[str]:
        """Get the regex patterns used for compound word detection.

        This method exposes the internal regex patterns used by the detector
        for compound word identification. Useful for debugging and testing.

        Returns:
            list[str]: List of regex patterns used for compound detection
        """
        return [
            # CapitalizedCompounds (internal capitals)
            r"\b[A-ZÄÖÜ][a-zäöüß]{5,}(?:[A-ZÄÖÜ][a-zäöüß]+)+\b",
            # Long capitalized words (potential compounds)
            r"\b[A-ZÄÖÜ][a-zäöüß]{10,}\b",
            # linked compounds
            r"\b[a-zäöüß]+(?:s|n|es|en|er|e|ns|ts)[a-zäöüß]{4,}\b",
            # abstract suffixes including philosophical terms
            r"\b[a-zäöüß]+(?:heit|keit|ung|schaft|tum|nis|sal|ismus|ität|logie|sophie|bewusstsein|philosophie)\b",
        ]

    def _extract_candidates_regex(self, text: str) -> list[CandidateTerm]:
        """Fallback candidate extraction using regex patterns."""
        candidates = []

        # Get patterns from the centralized method
        compound_patterns = self.get_compound_patterns()

        sentences = self._split_sentences(text)

        for sentence in sentences:
            for pattern in compound_patterns:
                for match in re.finditer(pattern, sentence):
                    term = match.group()
                    if len(term) >= 6:  # Minimum length for consideration
                        candidates.append(
                            self.CandidateTerm(
                                term=term,
                                start_pos=match.start(),
                                end_pos=match.end(),
                                sentence_context=sentence,
                            )
                        )

        return candidates

    def _is_compound_word(self, word: str) -> bool:
        """Check if word appears to be a German compound."""
        if len(word) < 10:  # Increase minimum length for compounds
            return False

        word_lower = word.lower()

        # Exclude common single words that might match patterns
        single_words = {
            "bewusstsein",
            "wirklichkeit",
            "erkenntnis",
            "wahrnehmung",
            "philosophie",
            "wissenschaft",
            "gesellschaft",
        }
        if word_lower in single_words:
            return False

        # Pattern 1: Philosophical compounds (requires prefix before philosophical terms)
        philosophical_endings = self.german_morphological_patterns[
            "philosophical_endings"
        ]
        for ending in philosophical_endings:
            if word_lower.endswith(ending) and len(word_lower) > len(ending):
                prefix = word_lower[: -len(ending)]
                if len(prefix) >= 4:  # Require meaningful prefix (increased from 3)
                    return True

        # Pattern 2: Philosophical prefix compounds
        if re.search(r"^(?:welt|lebens|seins|geist|seele)\w{4,}$", word_lower):
            return True

        # Pattern 3: Standard compound linking (more restrictive)
        # Only match if there's a clear compound structure with meaningful parts
        if re.search(r"^\w{4,}(?:s|en|er)\w{4,}$", word_lower):
            return True

        # Check for multiple capital letters (German noun compounds)
        capital_count = sum(1 for c in word if c.isupper())
        if capital_count >= 2:
            return True

        return False

    def _analyze_morphology(self, term: str) -> MorphologicalAnalysis:
        """Analyze morphological structure of a term."""
        return self.morphological_analyzer.analyze(term)

    def _analyze_philosophical_context(
        self, term: str, text: str, start_pos: int, end_pos: int
    ) -> PhilosophicalContext:
        """Analyze philosophical context around a term."""
        return self.philosophical_context_analyzer.analyze_context(
            term, text, start_pos, end_pos
        )

    def _calculate_confidence_factors(
        self,
        term: str,
        morphological: MorphologicalAnalysis,
        philosophical: PhilosophicalContext,
    ) -> ConfidenceFactors:
        """Calculate individual confidence factors."""
        return self.confidence_scorer.calculate_confidence_factors(
            term, morphological, philosophical
        )

    def _classify_neologism_type(
        self, morphological: MorphologicalAnalysis
    ) -> NeologismType:
        """Classify the type of neologism."""
        if morphological.is_compound:
            return NeologismType.COMPOUND

        # Check for philosophical indicators first (more specific)
        philosophical_suffixes = ["ismus", "logie", "sophie"]
        if any(suffix in morphological.suffixes for suffix in philosophical_suffixes):
            return NeologismType.PHILOSOPHICAL_TERM

        # Check for technical indicators
        technical_suffixes = ["ation", "ität", "ismus"]
        if any(suffix in morphological.suffixes for suffix in technical_suffixes):
            return NeologismType.TECHNICAL_TERM

        # General derived check (less specific)
        if morphological.prefixes or morphological.suffixes:
            return NeologismType.DERIVED

        return NeologismType.UNKNOWN

    def _calculate_analysis_quality(self, analysis: NeologismAnalysis) -> float:
        """Calculate overall analysis quality score."""
        if not analysis.detected_neologisms:
            return 0.5  # Neutral score for no detections

        # Quality factors
        neologisms = analysis.detected_neologisms
        confidence_avg = sum(n.confidence for n in neologisms) / len(neologisms)
        type_diversity = len({n.neologism_type for n in neologisms})

        quality = (confidence_avg * 0.6) + (min(1.0, type_diversity / 5.0) * 0.4)

        return quality

    def _calculate_coverage_ratio(
        self, analysis: NeologismAnalysis, text: str
    ) -> float:
        """Calculate coverage ratio of analysis."""
        if not analysis.detected_neologisms:
            return 0.0

        # Calculate ratio of analyzed terms to total words
        total_words = len(text.split())
        analyzed_terms = len(analysis.detected_neologisms)

        # Use configurable expected neologism ratio
        expected_ratio = getattr(self, "expected_neologism_ratio", 0.1)
        return min(1.0, analyzed_terms / max(1, total_words * expected_ratio))

    def _extract_semantic_fields(self, analysis: NeologismAnalysis) -> list[str]:
        """Extract semantic fields from analysis."""
        return self.philosophical_context_analyzer.extract_semantic_fields(
            analysis.detected_neologisms
        )

    def _extract_dominant_concepts(self, analysis: NeologismAnalysis) -> list[str]:
        """Extract dominant concepts from analysis."""
        return self.philosophical_context_analyzer.extract_dominant_concepts(
            analysis.detected_neologisms
        )

    def get_statistics(self) -> dict[str, Any]:
        """Get detector statistics."""
        cache_info = self.morphological_analyzer.get_cache_info()

        return {
            "total_analyses": self.total_analyses,
            "cache_hits": cache_info["hits"],
            "cache_misses": cache_info["misses"],
            "cache_size": cache_info["currsize"],
            "cache_hit_rate": cache_info["hit_rate"],
            "spacy_available": SPACY_AVAILABLE,
            "spacy_model": self.spacy_model if self.nlp else None,
            "terminology_entries": len(self.terminology_map),
            "philosophical_indicators": len(self.philosophical_indicators),
        }

    def debug_compound_detection(self, word: str) -> bool:
        """Public debugging method to check if a word appears to be a German compound.

        This method provides safe access to compound word detection logic
        for debugging and testing purposes.

        Args:
            word: The word to analyze for compound structure

        Returns:
            bool: True if the word appears to be a compound, False otherwise
        """
        return self._is_compound_word(word)

    def debug_extract_philosophical_keywords(self, text: str) -> list[str]:
        """Public debugging method to extract philosophical keywords from text.

        This method provides safe access to philosophical keyword extraction logic
        for debugging and testing purposes.

        Args:
            text: The text to analyze for philosophical keywords

        Returns:
            list[str]: List of philosophical keywords found in the text
        """
        return self._extract_philosophical_keywords(text)

    def debug_extract_candidates(self, text: str) -> list[dict[str, Any]]:
        """Public debugging method to extract candidate terms from text.

        This method provides safe access to candidate extraction logic
        for debugging and testing purposes. It returns candidate terms
        that would be considered for neologism analysis.

        Args:
            text: Text to analyze for candidate terms

        Returns:
            list[dict[str, Any]]: List of candidate terms with their metadata.
                Each candidate contains:
                - term: The candidate term text
                - start_pos: Starting position in the text
                - end_pos: Ending position in the text
                - sentence_context: The sentence containing the term
        """
        try:
            candidates = self._extract_candidates(text)
            # Convert CandidateTerm objects to dictionaries for safe external use
            return [
                {
                    "term": candidate.term,
                    "start_pos": candidate.start_pos,
                    "end_pos": candidate.end_pos,
                    "sentence_context": candidate.sentence_context,
                }
                for candidate in candidates
            ]
        except Exception as e:
            # Return error information for debugging
            return [
                {
                    "error": {
                        "type": type(e).__name__,
                        "message": str(e),
                        "text": text,
                    }
                }
            ]

    def debug_analyze_word(self, word: str, context: str = "") -> dict[str, Any]:
        """Comprehensive debug analysis of a single word.

        This method provides detailed information about how a word would be analyzed
        by the neologism detection system, including all intermediate steps and
        decision factors.

        Args:
            word: The word to analyze
            context: Optional context sentence containing the word

        Returns:
            dict: Comprehensive debug information including:
                - basic_info: word length, capitalization, etc.
                - compound_analysis: compound word detection results
                - morphological_analysis: detailed morphological breakdown
                - philosophical_context: philosophical relevance analysis
                - confidence_factors: all confidence calculation factors
                - final_assessment: whether it would be detected as neologism
        """
        try:
            # Basic word information
            basic_info = {
                "word": word,
                "length": len(word),
                "capital_count": sum(1 for c in word if c.isupper()),
                "is_compound": self._is_compound_word(word),
                "in_terminology": word.lower() in self.terminology_map,
            }

            # Morphological analysis
            morphological_analysis = self._analyze_morphology(word)

            # Philosophical context analysis (use provided context or word alone)
            analysis_text = context if context else word
            philosophical_context = self._analyze_philosophical_context(
                word, analysis_text, 0, len(word)
            )

            # Confidence factors calculation
            confidence_factors = self._calculate_confidence_factors(
                word, morphological_analysis, philosophical_context
            )

            # Final confidence score
            confidence_score = confidence_factors.calculate_weighted_score()
            is_neologism = confidence_score >= self.philosophical_threshold

            # Neologism type classification
            neologism_type = self._classify_neologism_type(morphological_analysis)

            return {
                "basic_info": basic_info,
                "compound_analysis": {
                    "is_compound": basic_info["is_compound"],
                    "compound_parts": morphological_analysis.compound_parts,
                    "compound_pattern": morphological_analysis.compound_pattern,
                },
                "morphological_analysis": {
                    "syllable_count": morphological_analysis.syllable_count,
                    "morpheme_count": morphological_analysis.morpheme_count,
                    "word_length": morphological_analysis.word_length,
                    "root_words": morphological_analysis.root_words,
                    "prefixes": morphological_analysis.prefixes,
                    "suffixes": morphological_analysis.suffixes,
                    "is_compound": morphological_analysis.is_compound,
                    "compound_parts": morphological_analysis.compound_parts,
                    "compound_pattern": morphological_analysis.compound_pattern,
                    "structural_complexity": morphological_analysis.structural_complexity,
                    "morphological_productivity": morphological_analysis.morphological_productivity,
                },
                "philosophical_context": {
                    "philosophical_density": philosophical_context.philosophical_density,
                    "semantic_field": philosophical_context.semantic_field,
                    "domain_indicators": philosophical_context.domain_indicators,
                    "surrounding_terms": philosophical_context.surrounding_terms,
                    "philosophical_keywords": philosophical_context.philosophical_keywords,
                    "conceptual_clusters": philosophical_context.conceptual_clusters,
                    "author_terminology": philosophical_context.author_terminology,
                    "related_concepts": philosophical_context.related_concepts,
                },
                "confidence_factors": {
                    "morphological_complexity": confidence_factors.morphological_complexity,
                    "compound_structure_score": confidence_factors.compound_structure_score,
                    "morphological_productivity": confidence_factors.morphological_productivity,
                    "context_density": confidence_factors.context_density,
                    "philosophical_indicators": confidence_factors.philosophical_indicators,
                    "semantic_coherence": confidence_factors.semantic_coherence,
                    "rarity_score": confidence_factors.rarity_score,
                    "frequency_deviation": confidence_factors.frequency_deviation,
                    "corpus_novelty": confidence_factors.corpus_novelty,
                    "known_patterns": confidence_factors.known_patterns,
                    "pattern_productivity": confidence_factors.pattern_productivity,
                    "structural_regularity": confidence_factors.structural_regularity,
                    "phonological_plausibility": confidence_factors.phonological_plausibility,
                    "syntactic_integration": confidence_factors.syntactic_integration,
                    "semantic_transparency": confidence_factors.semantic_transparency,
                    "weighted_score": confidence_score,
                },
                "final_assessment": {
                    "is_neologism": is_neologism,
                    "confidence_score": confidence_score,
                    "threshold": self.philosophical_threshold,
                    "neologism_type": neologism_type.value if neologism_type else None,
                },
                "debug_metadata": {
                    "analysis_timestamp": datetime.now().isoformat(),
                    "detector_config": {
                        "philosophical_threshold": self.philosophical_threshold,
                        "spacy_model": self.spacy_model if self.nlp else None,
                        "terminology_entries": len(self.terminology_map),
                    },
                },
            }

        except Exception as e:
            # Return error information for debugging
            return {
                "error": {
                    "type": type(e).__name__,
                    "message": str(e),
                    "word": word,
                    "context": context,
                },
                "basic_info": {
                    "word": word,
                    "length": len(word),
                    "capital_count": sum(1 for c in word if c.isupper()),
                },
            }

    # Delegation methods for morphological analysis (for backward compatibility with tests)
    def _count_syllables(self, word: str) -> int:
        """Count syllables in a word."""
        return self.morphological_analyzer._count_syllables(word)

    def _split_compound(self, word: str) -> list[str]:
        """Split compound word into parts."""
        return self.morphological_analyzer._split_compound(word)

    def _extract_prefixes(self, word: str) -> list[str]:
        """Extract prefixes from a word."""
        return self.morphological_analyzer._extract_prefixes(word)

    def _extract_suffixes(self, word: str) -> list[str]:
        """Extract suffixes from a word."""
        return self.morphological_analyzer._extract_suffixes(word)

    def _calculate_philosophical_density(self, text: str) -> float:
        """Calculate philosophical density of text."""
        return self.philosophical_context_analyzer.calculate_philosophical_density(text)

    def _extract_philosophical_keywords(self, text: str) -> list[str]:
        """Extract philosophical keywords from text."""
        return self.philosophical_context_analyzer.extract_philosophical_keywords(text)

    def _identify_semantic_field(self, term: str, context: str) -> str:
        """Identify semantic field of a term."""
        return self.philosophical_context_analyzer._identify_semantic_field(context)

    def _extract_context_window(
        self, text: str, start_pos: int, end_pos: int, window_size: int = 50
    ) -> str:
        """Extract context window around a term."""
        start = max(0, start_pos - window_size)
        end = min(len(text), end_pos + window_size)
        return text[start:end]

    def _calculate_rarity_score(self, term: str) -> float:
        """Calculate rarity score for a term."""
        # Simple rarity calculation based on term length and morphological complexity
        base_score = min(len(term) / 20.0, 1.0)  # Longer terms are rarer

        # Check if it's in our terminology map (known terms are less rare)
        if term.lower() in self.terminology_map:
            base_score *= 0.5

        return base_score

    def _calculate_pattern_score(self, term: str, morphological_analysis=None) -> float:
        """Calculate pattern-based score for a term."""
        score = 0.0

        # If morphological analysis is provided, use it for more accurate scoring
        if morphological_analysis:
            # Score based on prefixes
            if morphological_analysis.prefixes:
                score += len(morphological_analysis.prefixes) * 0.2

            # Score based on suffixes
            if morphological_analysis.suffixes:
                score += len(morphological_analysis.suffixes) * 0.2

            # Score based on compound structure
            if morphological_analysis.is_compound:
                score += 0.3

        # Check morphological patterns
        patterns = self.morphological_analyzer.german_morphological_patterns
        for pattern_list in patterns.values():
            for pattern in pattern_list:
                if re.search(pattern, term.lower()):
                    score += 0.1

        return min(score, 1.0)

    def _calculate_phonological_plausibility(self, term: str) -> float:
        """Calculate phonological plausibility score."""
        # Simple phonological plausibility based on German phonotactics
        score = 1.0

        # Penalize unusual consonant clusters (only rare/non-standard clusters)
        # Note: Common German clusters like 'sch', 'ch', 'st', 'sp' are
        # intentionally excluded as they are standard in German phonotactics
        unusual_clusters = ["tsch", "pf", "tz", "ck"]
        for cluster in unusual_clusters:
            if cluster in term.lower():
                score -= 0.1

        # Penalize very long words without vowels
        vowels = "aeiouäöü"
        vowel_count = sum(1 for c in term.lower() if c in vowels)
        if len(term) > 8 and vowel_count < 2:
            score -= 0.3

        return max(score, 0.0)

    def clear_cache(self) -> None:
        """Clear component caches."""
        self.morphological_analyzer.clear_cache()
        logger.info("Component caches cleared")


# Convenience functions for batch processing


def analyze_document_batch(
    detector: NeologismDetector, texts: list[str], text_ids: Optional[list[str]] = None
) -> list[NeologismAnalysis]:
    """Analyze multiple documents for neologisms."""
    if text_ids is None:
        text_ids = [f"doc_{i}" for i in range(len(texts))]

    analyses = []
    for text, text_id in zip(texts, text_ids, strict=False):
        analysis = detector.analyze_text(text, text_id)
        analyses.append(analysis)

    return analyses


def merge_neologism_analyses(
    analyses: list[NeologismAnalysis],
) -> NeologismAnalysis:
    """Merge multiple analyses into a single comprehensive analysis."""
    if not analyses:
        raise ValueError("Cannot merge empty list of analyses")

    # Use the merge function from the models module
    from models.neologism_models import merge_analyses

    return merge_analyses(analyses)
