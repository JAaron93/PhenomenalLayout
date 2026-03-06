"""Philosophical Context Analysis Engine for detecting semantic fields and conceptual clusters."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from models.neologism_models import PhilosophicalContext

logger = logging.getLogger(__name__)


class PhilosophicalContextAnalyzer:
    """Handles philosophical context analysis including semantic field identification."""

    def __init__(
        self,
        spacy_model: Any | None = None,
        terminology_map: dict[str, str] | None = None,
    ):
        """Initialize the philosophical context analyzer.

        Args:
            spacy_model: spaCy model instance for linguistic analysis
            terminology_map: Dictionary mapping philosophical terms to translations
        """
        self.nlp = spacy_model
        self.terminology_map = terminology_map or {}
        self.philosophical_indicators = self._load_philosophical_indicators()

        logger.info("PhilosophicalContextAnalyzer initialized")

    def _load_philosophical_indicators(self) -> set[str]:
        """Load philosophical indicators from configuration or fallback to hardcoded set."""
        indicators = set()

        # Try to load from config file first
        config_file_path = (
            Path(__file__).parent.parent / "config" / "philosophical_indicators.json"
        )

        try:
            if config_file_path.exists():
                with open(config_file_path, encoding="utf-8") as f:
                    config_data = json.load(f)

                    # Load indicators from each category
                    for _, terms in config_data.items():
                        if isinstance(terms, list):
                            indicators.update(term.lower() for term in terms)

                logger.info(
                    f"Loaded {len(indicators)} philosophical indicators from config file"
                )
            else:
                logger.warning(
                    f"Config file not found at {config_file_path}, using hardcoded indicators"
                )
                raise FileNotFoundError("Config file not found")

        except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(
                f"Could not load config file: {e}, falling back to hardcoded indicators"
            )

            # Fallback to hardcoded indicators
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

        # Add terminology terms as indicators
        if self.terminology_map:
            indicators.update(term.lower() for term in self.terminology_map.keys())

        return indicators

    def analyze_context(
        self, term: str, text: str, start_pos: int, end_pos: int
    ) -> PhilosophicalContext:
        """Analyze philosophical context around a term."""
        context = PhilosophicalContext()

        # Extract context window
        context_window = self._extract_context_window(text, start_pos, end_pos)

        # Calculate philosophical density
        context.philosophical_density = self._calculate_philosophical_density(
            context_window
        )

        # Extract philosophical indicators
        context.philosophical_keywords = self._extract_philosophical_keywords(
            context_window
        )
        context.domain_indicators = self._extract_domain_indicators(context_window)

        # Extract surrounding terms
        context.surrounding_terms = self._extract_surrounding_terms(
            context_window, term
        )

        # Semantic field analysis
        context.semantic_field = self._identify_semantic_field(context_window)

        # Conceptual clustering
        context.conceptual_clusters = self._extract_conceptual_clusters(context_window)

        return context

    def _extract_context_window(
        self, text: str, start_pos: int, end_pos: int, window_size: int = 200
    ) -> str:
        """Extract context window around a term."""
        context_start = max(0, start_pos - window_size)
        context_end = min(len(text), end_pos + window_size)
        return text[context_start:context_end]

    def _calculate_philosophical_density(self, context: str) -> float:
        """Calculate philosophical density of context."""
        if not context:
            return 0.0

        words = context.lower().split()
        if not words:
            return 0.0

        philosophical_word_count = sum(
            1 for word in words if word in self.philosophical_indicators
        )
        density = philosophical_word_count / len(words)

        return min(1.0, density * 3.0)  # Scale up for better differentiation

    def _extract_philosophical_keywords(self, context: str) -> list[str]:
        """Extract philosophical keywords from context."""
        keywords = []
        words = context.lower().split()

        for word in words:
            # Strip punctuation from word
            clean_word = re.sub(r"[^\w]", "", word)
            if clean_word in self.philosophical_indicators:
                keywords.append(clean_word)

        return list(set(keywords))

    def _extract_domain_indicators(self, context: str) -> list[str]:
        """Extract domain-specific indicators from context."""
        indicators = []

        # Philosophical domains
        domain_patterns = {
            "metaphysics": ["sein", "wesen", "substanz", "realität", "ontologie"],
            "epistemology": ["erkenntnis", "wissen", "wahrheit", "gewissheit"],
            "ethics": ["moral", "ethik", "gut", "böse", "pflicht", "tugend"],
            "aesthetics": ["schön", "hässlich", "kunst", "ästhetik", "geschmack"],
            "logic": ["logik", "schluss", "beweis", "argument", "wahrheit"],
        }

        context_lower = context.lower()
        for domain, keywords in domain_patterns.items():
            if any(keyword in context_lower for keyword in keywords):
                indicators.append(domain)

        return indicators

    def _extract_surrounding_terms(self, context: str, target_term: str) -> list[str]:
        """Extract terms surrounding the target term."""
        surrounding = []

        if self.nlp:
            doc = self.nlp(context)
            for token in doc:
                if (
                    token.text.lower() != target_term.lower()
                    and not token.is_stop
                    and not token.is_punct
                    and len(token.text) > 3
                ):
                    surrounding.append(token.text)
        else:
            # Fallback extraction
            words = context.split()
            for word in words:
                cleaned = re.sub(r"[^\w]", "", word)
                if cleaned.lower() != target_term.lower() and len(cleaned) > 3:
                    surrounding.append(cleaned)

        return surrounding[:10]  # Limit to avoid noise

    def _identify_semantic_field(self, context: str) -> str:
        """Identify the dominant semantic field."""
        context_lower = context.lower()

        # Semantic field indicators
        fields = {
            "consciousness": ["bewusstsein", "geist", "psyche", "mental"],
            "existence": ["sein", "dasein", "existenz", "realität"],
            "knowledge": ["wissen", "erkenntnis", "wahrheit", "gewissheit"],
            "value": ["wert", "gut", "böse", "moral", "ethik"],
            "beauty": ["schön", "ästhetik", "kunst", "geschmack"],
            "language": ["sprache", "wort", "bedeutung", "begriff"],
            "time": ["zeit", "temporal", "vergangenheit", "zukunft"],
            "space": ["raum", "spatial", "ort", "stelle"],
        }

        field_scores = {}
        for field, indicators in fields.items():
            score = sum(1 for indicator in indicators if indicator in context_lower)
            if score > 0:
                field_scores[field] = score

        if field_scores:
            return max(field_scores, key=field_scores.get)

        return "general"

    def _extract_conceptual_clusters(self, context: str) -> list[str]:
        """Extract conceptual clusters from context."""
        clusters = []

        # Define conceptual clusters
        cluster_patterns = {
            "german_idealism": ["hegel", "kant", "fichte", "schelling", "idealismus"],
            "phenomenology": [
                "husserl",
                "heidegger",
                "phänomenologie",
                "intentionalität",
            ],
            "existentialism": [
                "kierkegaard",
                "nietzsche",
                "existenz",
                "angst",
                "freedom",
            ],
            "philosophy_of_mind": [
                "bewusstsein",
                "geist",
                "mental",
                "psyche",
                "kognition",
            ],
            "metaphysics": ["sein", "wesen", "substanz", "kausalität", "notwendigkeit"],
        }

        context_lower = context.lower()
        for cluster, keywords in cluster_patterns.items():
            if any(keyword in context_lower for keyword in keywords):
                clusters.append(cluster)

        return clusters

    def extract_semantic_fields(self, detected_neologisms: list[Any]) -> list[str]:
        """Extract semantic fields from detected neologisms."""
        fields = set()

        for neologism in detected_neologisms:
            if (
                hasattr(neologism, "philosophical_context")
                and neologism.philosophical_context.semantic_field
            ):
                fields.add(neologism.philosophical_context.semantic_field)

        return list(fields)

    def extract_dominant_concepts(self, detected_neologisms: list[Any]) -> list[str]:
        """Extract dominant concepts from detected neologisms."""
        concept_counts = {}

        for neologism in detected_neologisms:
            if hasattr(neologism, "philosophical_context"):
                for keyword in neologism.philosophical_context.philosophical_keywords:
                    concept_counts[keyword] = concept_counts.get(keyword, 0) + 1

        # Return top concepts
        sorted_concepts = sorted(
            concept_counts.items(), key=lambda x: x[1], reverse=True
        )
        return [concept for concept, count in sorted_concepts[:10]]

    def update_terminology_map(self, new_terminology: dict[str, str]) -> None:
        """Update the terminology map and refresh philosophical indicators."""
        self.terminology_map.update(new_terminology)
        self.philosophical_indicators = self._load_philosophical_indicators()
        logger.info(f"Updated terminology map with {len(new_terminology)} new terms")

    # Public wrapper methods for backward compatibility with tests
    def calculate_philosophical_density(self, text: str) -> float:
        """Calculate philosophical density of text."""
        return self._calculate_philosophical_density(text)

    def extract_philosophical_keywords(self, text: str) -> list[str]:
        """Extract philosophical keywords from text."""
        return self._extract_philosophical_keywords(text)
