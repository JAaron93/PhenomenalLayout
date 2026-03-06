"""Data models for neologism detection and analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NeologismType(Enum):
    """Types of detected neologisms."""

    COMPOUND = "compound"
    PHILOSOPHICAL_TERM = "philosophical_term"
    TECHNICAL_TERM = "technical_term"
    DERIVED = "derived"
    UNKNOWN = "unknown"


class ConfidenceLevel(Enum):
    """Confidence levels for neologism detection."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


@dataclass
class MorphologicalAnalysis:
    """Analysis of word morphology and structure."""

    # Core morphological components
    root_words: list[str] = field(default_factory=list)
    prefixes: list[str] = field(default_factory=list)
    suffixes: list[str] = field(default_factory=list)

    # Compound analysis
    is_compound: bool = False
    compound_parts: list[str] = field(default_factory=list)
    compound_pattern: str | None = None

    # Linguistic features
    word_length: int = 0
    syllable_count: int = 0
    morpheme_count: int = 0

    # Complexity metrics
    structural_complexity: float = 0.0
    morphological_productivity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "root_words": self.root_words,
            "prefixes": self.prefixes,
            "suffixes": self.suffixes,
            "is_compound": self.is_compound,
            "compound_parts": self.compound_parts,
            "compound_pattern": self.compound_pattern,
            "word_length": self.word_length,
            "syllable_count": self.syllable_count,
            "morpheme_count": self.morpheme_count,
            "structural_complexity": self.structural_complexity,
            "morphological_productivity": self.morphological_productivity,
        }


@dataclass
class PhilosophicalContext:
    """Analysis of philosophical context and semantic field."""

    # Context indicators
    philosophical_density: float = 0.0
    semantic_field: str = ""
    domain_indicators: list[str] = field(default_factory=list)

    # Contextual elements
    surrounding_terms: list[str] = field(default_factory=list)
    philosophical_keywords: list[str] = field(default_factory=list)
    conceptual_clusters: list[str] = field(default_factory=list)

    # Authorial context
    author_terminology: list[str] = field(default_factory=list)
    text_genre: str = ""
    historical_period: str = ""

    # Semantic relationships
    related_concepts: list[str] = field(default_factory=list)
    semantic_network: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "philosophical_density": self.philosophical_density,
            "semantic_field": self.semantic_field,
            "domain_indicators": self.domain_indicators,
            "surrounding_terms": self.surrounding_terms,
            "philosophical_keywords": self.philosophical_keywords,
            "conceptual_clusters": self.conceptual_clusters,
            "author_terminology": self.author_terminology,
            "text_genre": self.text_genre,
            "historical_period": self.historical_period,
            "related_concepts": self.related_concepts,
            "semantic_network": self.semantic_network,
        }


@dataclass
class ConfidenceFactors:
    """Individual factors contributing to confidence scoring."""

    # Morphological factors
    morphological_complexity: float = 0.0
    compound_structure_score: float = 0.0
    morphological_productivity: float = 0.0

    # Context factors
    context_density: float = 0.0
    philosophical_indicators: float = 0.0
    semantic_coherence: float = 0.0

    # Frequency factors
    rarity_score: float = 0.0
    frequency_deviation: float = 0.0
    corpus_novelty: float = 0.0

    # Pattern factors
    known_patterns: float = 0.0
    pattern_productivity: float = 0.0
    structural_regularity: float = 0.0

    # Linguistic factors
    phonological_plausibility: float = 0.0
    syntactic_integration: float = 0.0
    semantic_transparency: float = 0.0

    def calculate_weighted_score(self) -> float:
        """Calculate weighted confidence score from individual factors."""
        weights = {
            "morphological": 0.25,
            "context": 0.30,
            "frequency": 0.20,
            "pattern": 0.15,
            "linguistic": 0.10,
        }

        morphological_score = (
            self.morphological_complexity * 0.4
            + self.compound_structure_score * 0.4
            + self.morphological_productivity * 0.2
        )

        context_score = (
            self.context_density * 0.4
            + self.philosophical_indicators * 0.4
            + self.semantic_coherence * 0.2
        )

        frequency_score = (
            self.rarity_score * 0.5
            + self.frequency_deviation * 0.3
            + self.corpus_novelty * 0.2
        )

        pattern_score = (
            self.known_patterns * 0.4
            + self.pattern_productivity * 0.3
            + self.structural_regularity * 0.3
        )

        linguistic_score = (
            self.phonological_plausibility * 0.4
            + self.syntactic_integration * 0.3
            + self.semantic_transparency * 0.3
        )

        total_score = (
            morphological_score * weights["morphological"]
            + context_score * weights["context"]
            + frequency_score * weights["frequency"]
            + pattern_score * weights["pattern"]
            + linguistic_score * weights["linguistic"]
        )

        return min(1.0, max(0.0, total_score))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "morphological_complexity": self.morphological_complexity,
            "compound_structure_score": self.compound_structure_score,
            "morphological_productivity": self.morphological_productivity,
            "context_density": self.context_density,
            "philosophical_indicators": self.philosophical_indicators,
            "semantic_coherence": self.semantic_coherence,
            "rarity_score": self.rarity_score,
            "frequency_deviation": self.frequency_deviation,
            "corpus_novelty": self.corpus_novelty,
            "known_patterns": self.known_patterns,
            "pattern_productivity": self.pattern_productivity,
            "structural_regularity": self.structural_regularity,
            "phonological_plausibility": self.phonological_plausibility,
            "syntactic_integration": self.syntactic_integration,
            "semantic_transparency": self.semantic_transparency,
            "weighted_score": self.calculate_weighted_score(),
        }


@dataclass
class DetectedNeologism:
    """Represents a detected neologism with analysis data."""

    # Core identification
    term: str
    confidence: float
    neologism_type: NeologismType

    # Position information
    start_pos: int
    end_pos: int
    sentence_context: str
    paragraph_context: str = ""

    # Analysis results
    morphological_analysis: MorphologicalAnalysis = field(
        default_factory=MorphologicalAnalysis
    )
    philosophical_context: PhilosophicalContext = field(
        default_factory=PhilosophicalContext
    )
    confidence_factors: ConfidenceFactors = field(default_factory=ConfidenceFactors)

    # Metadata
    detection_timestamp: str | None = None
    source_text_id: str | None = None
    page_number: int | None = None

    # Additional properties
    translation_suggestions: list[str] = field(default_factory=list)
    glossary_candidates: list[str] = field(default_factory=list)
    related_terms: list[str] = field(default_factory=list)

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get confidence level based on numeric confidence."""
        if self.confidence >= 0.8:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.6:
            return ConfidenceLevel.MEDIUM
        elif self.confidence >= 0.4:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.UNCERTAIN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "term": self.term,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "neologism_type": self.neologism_type.value,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "sentence_context": self.sentence_context,
            "paragraph_context": self.paragraph_context,
            "morphological_analysis": self.morphological_analysis.to_dict(),
            "philosophical_context": self.philosophical_context.to_dict(),
            "confidence_factors": self.confidence_factors.to_dict(),
            "detection_timestamp": self.detection_timestamp,
            "source_text_id": self.source_text_id,
            "page_number": self.page_number,
            "translation_suggestions": self.translation_suggestions,
            "glossary_candidates": self.glossary_candidates,
            "related_terms": self.related_terms,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectedNeologism:
        """Create DetectedNeologism instance from dictionary data."""
        # Create nested objects from dictionaries
        morphological_analysis = MorphologicalAnalysis()
        if data.get("morphological_analysis"):
            morph_data = data["morphological_analysis"]
            morphological_analysis = MorphologicalAnalysis(
                root_words=morph_data.get("root_words", []),
                prefixes=morph_data.get("prefixes", []),
                suffixes=morph_data.get("suffixes", []),
                is_compound=morph_data.get("is_compound", False),
                compound_parts=morph_data.get("compound_parts", []),
                compound_pattern=morph_data.get("compound_pattern"),
                word_length=morph_data.get("word_length", 0),
                syllable_count=morph_data.get("syllable_count", 0),
                morpheme_count=morph_data.get("morpheme_count", 0),
                structural_complexity=morph_data.get("structural_complexity", 0.0),
                morphological_productivity=morph_data.get(
                    "morphological_productivity", 0.0
                ),
            )

        philosophical_context = PhilosophicalContext()
        if data.get("philosophical_context"):
            phil_data = data["philosophical_context"]
            philosophical_context = PhilosophicalContext(
                philosophical_density=phil_data.get("philosophical_density", 0.0),
                semantic_field=phil_data.get("semantic_field", ""),
                domain_indicators=phil_data.get("domain_indicators", []),
                surrounding_terms=phil_data.get("surrounding_terms", []),
                philosophical_keywords=phil_data.get("philosophical_keywords", []),
                conceptual_clusters=phil_data.get("conceptual_clusters", []),
                author_terminology=phil_data.get("author_terminology", []),
                text_genre=phil_data.get("text_genre", ""),
                historical_period=phil_data.get("historical_period", ""),
                related_concepts=phil_data.get("related_concepts", []),
                semantic_network=phil_data.get("semantic_network", {}),
            )

        confidence_factors = ConfidenceFactors()
        if data.get("confidence_factors"):
            conf_data = data["confidence_factors"]
            confidence_factors = ConfidenceFactors(
                morphological_complexity=conf_data.get("morphological_complexity", 0.0),
                compound_structure_score=conf_data.get("compound_structure_score", 0.0),
                morphological_productivity=conf_data.get(
                    "morphological_productivity", 0.0
                ),
                context_density=conf_data.get("context_density", 0.0),
                philosophical_indicators=conf_data.get("philosophical_indicators", 0.0),
                semantic_coherence=conf_data.get("semantic_coherence", 0.0),
                rarity_score=conf_data.get("rarity_score", 0.0),
                frequency_deviation=conf_data.get("frequency_deviation", 0.0),
                corpus_novelty=conf_data.get("corpus_novelty", 0.0),
                known_patterns=conf_data.get("known_patterns", 0.0),
                pattern_productivity=conf_data.get("pattern_productivity", 0.0),
                structural_regularity=conf_data.get("structural_regularity", 0.0),
                phonological_plausibility=conf_data.get(
                    "phonological_plausibility", 0.0
                ),
                syntactic_integration=conf_data.get("syntactic_integration", 0.0),
                semantic_transparency=conf_data.get("semantic_transparency", 0.0),
            )

        # Handle neologism type conversion
        neologism_type = NeologismType.UNKNOWN
        if "neologism_type" in data:
            if isinstance(data["neologism_type"], str):
                try:
                    neologism_type = NeologismType(data["neologism_type"])
                except ValueError:
                    neologism_type = NeologismType.UNKNOWN
            elif isinstance(data["neologism_type"], NeologismType):
                neologism_type = data["neologism_type"]

        return cls(
            term=data.get("term", ""),
            confidence=data.get("confidence", 0.0),
            neologism_type=neologism_type,
            start_pos=data.get("start_pos", 0),
            end_pos=data.get("end_pos", 0),
            sentence_context=data.get("sentence_context", ""),
            paragraph_context=data.get("paragraph_context", ""),
            morphological_analysis=morphological_analysis,
            philosophical_context=philosophical_context,
            confidence_factors=confidence_factors,
            detection_timestamp=data.get("detection_timestamp"),
            source_text_id=data.get("source_text_id"),
            page_number=data.get("page_number"),
            translation_suggestions=data.get("translation_suggestions", []),
            glossary_candidates=data.get("glossary_candidates", []),
            related_terms=data.get("related_terms", []),
        )


@dataclass
class NeologismAnalysis:
    """Comprehensive analysis results for a text or document."""

    # Analysis metadata
    text_id: str
    analysis_timestamp: str
    total_tokens: int
    analyzed_chunks: int

    # Detection results
    detected_neologisms: list[DetectedNeologism] = field(default_factory=list)
    total_detections: int = 0

    # Statistical summary
    confidence_distribution: dict[str, int] = field(default_factory=dict)
    type_distribution: dict[str, int] = field(default_factory=dict)

    # Context analysis
    philosophical_density_avg: float = 0.0
    semantic_fields: list[str] = field(default_factory=list)
    dominant_concepts: list[str] = field(default_factory=list)

    # Performance metrics
    processing_time: float = 0.0
    memory_usage: float | None = None
    cache_hits: int = 0

    # Quality indicators
    analysis_quality: float = 0.0
    coverage_ratio: float = 0.0

    def add_detection(self, neologism: DetectedNeologism) -> None:
        """Add a detected neologism to the analysis."""
        self.detected_neologisms.append(neologism)
        self.total_detections = len(self.detected_neologisms)
        self._update_statistics()

    def _update_statistics(self) -> None:
        """Update statistical summaries."""
        if not self.detected_neologisms:
            return

        # Update confidence distribution
        self.confidence_distribution = {
            ConfidenceLevel.HIGH.value: 0,
            ConfidenceLevel.MEDIUM.value: 0,
            ConfidenceLevel.LOW.value: 0,
            ConfidenceLevel.UNCERTAIN.value: 0,
        }

        # Update type distribution
        self.type_distribution = {
            NeologismType.COMPOUND.value: 0,
            NeologismType.PHILOSOPHICAL_TERM.value: 0,
            NeologismType.TECHNICAL_TERM.value: 0,
            NeologismType.DERIVED.value: 0,
            NeologismType.UNKNOWN.value: 0,
        }

        # Count distributions
        for neologism in self.detected_neologisms:
            self.confidence_distribution[neologism.confidence_level.value] += 1
            self.type_distribution[neologism.neologism_type.value] += 1

        # Calculate averages
        if self.detected_neologisms:
            self.philosophical_density_avg = sum(
                n.philosophical_context.philosophical_density
                for n in self.detected_neologisms
            ) / len(self.detected_neologisms)

    def get_high_confidence_neologisms(self) -> list[DetectedNeologism]:
        """Get neologisms with high confidence scores."""
        return [
            n
            for n in self.detected_neologisms
            if n.confidence_level == ConfidenceLevel.HIGH
        ]

    def get_neologisms_by_type(
        self, neologism_type: NeologismType
    ) -> list[DetectedNeologism]:
        """Get neologisms of a specific type."""
        return [
            n for n in self.detected_neologisms if n.neologism_type == neologism_type
        ]

    def get_summary_statistics(self) -> dict[str, Any]:
        """Get summary statistics for the analysis."""
        return {
            "total_detections": self.total_detections,
            "confidence_distribution": self.confidence_distribution,
            "type_distribution": self.type_distribution,
            "philosophical_density_avg": self.philosophical_density_avg,
            "semantic_fields": self.semantic_fields,
            "dominant_concepts": self.dominant_concepts,
            "analysis_quality": self.analysis_quality,
            "coverage_ratio": self.coverage_ratio,
            "processing_time": self.processing_time,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "text_id": self.text_id,
            "analysis_timestamp": self.analysis_timestamp,
            "total_tokens": self.total_tokens,
            "analyzed_chunks": self.analyzed_chunks,
            "detected_neologisms": [n.to_dict() for n in self.detected_neologisms],
            "total_detections": self.total_detections,
            "confidence_distribution": self.confidence_distribution,
            "type_distribution": self.type_distribution,
            "philosophical_density_avg": self.philosophical_density_avg,
            "semantic_fields": self.semantic_fields,
            "dominant_concepts": self.dominant_concepts,
            "processing_time": self.processing_time,
            "memory_usage": self.memory_usage,
            "cache_hits": self.cache_hits,
            "analysis_quality": self.analysis_quality,
            "coverage_ratio": self.coverage_ratio,
            "summary_statistics": self.get_summary_statistics(),
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# Helper functions for working with neologism data


def merge_analyses(analyses: list[NeologismAnalysis]) -> NeologismAnalysis:
    """Merge multiple neologism analyses into a single analysis."""
    if not analyses:
        raise ValueError("Cannot merge empty list of analyses")

    if len(analyses) == 1:
        return analyses[0]

    # Create merged analysis
    merged = NeologismAnalysis(
        text_id="merged_analysis",
        analysis_timestamp=analyses[0].analysis_timestamp,
        total_tokens=sum(a.total_tokens for a in analyses),
        analyzed_chunks=sum(a.analyzed_chunks for a in analyses),
    )

    # Merge detections
    for analysis in analyses:
        for neologism in analysis.detected_neologisms:
            merged.add_detection(neologism)

    # Merge performance metrics
    merged.processing_time = sum(a.processing_time for a in analyses)
    merged.cache_hits = sum(a.cache_hits for a in analyses)

    # Calculate merged quality indicators
    if analyses:
        merged.analysis_quality = sum(a.analysis_quality for a in analyses) / len(
            analyses
        )
        merged.coverage_ratio = sum(a.coverage_ratio for a in analyses) / len(analyses)

    return merged


def filter_neologisms_by_confidence(
    neologisms: list[DetectedNeologism], min_confidence: float = 0.5
) -> list[DetectedNeologism]:
    """Filter neologisms by minimum confidence threshold."""
    return [n for n in neologisms if n.confidence >= min_confidence]


def sort_neologisms_by_confidence(
    neologisms: list[DetectedNeologism], descending: bool = True
) -> list[DetectedNeologism]:
    """Sort neologisms by confidence score."""
    return sorted(neologisms, key=lambda n: n.confidence, reverse=descending)
