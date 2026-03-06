"""Data models for user choice management in neologism translation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ChoiceType(Enum):
    """Types of user choices for neologism handling."""

    TRANSLATE = "translate"
    PRESERVE = "preserve"
    CUSTOM_TRANSLATION = "custom_translation"
    SKIP = "skip"


class ChoiceScope(Enum):
    """Scope of user choice application."""

    GLOBAL = "global"  # Apply to all occurrences
    CONTEXTUAL = "contextual"  # Apply to similar contexts
    DOCUMENT = "document"  # Apply within current document
    SESSION = "session"  # Apply within current session only


class ConflictResolution(Enum):
    """Strategies for resolving choice conflicts."""

    LATEST_WINS = "latest_wins"  # Most recent choice takes precedence
    CONTEXT_SPECIFIC = "context_specific"  # Context-aware resolution
    USER_PROMPT = "user_prompt"  # Ask user to resolve
    HIGHEST_CONFIDENCE = "highest_confidence"  # Use choice with highest confidence


class SessionStatus(Enum):
    """Status of user choice sessions."""

    ACTIVE = "active"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


@dataclass
class TranslationContext:
    """Context information for translation choices."""

    # Text context
    sentence_context: str = ""
    paragraph_context: str = ""
    document_context: str = ""

    # Semantic context
    semantic_field: str = ""
    philosophical_domain: str = ""
    author: str = ""
    source_language: str = ""
    target_language: str = ""

    # Positional context
    page_number: int | None = None
    chapter: str | None = None
    section: str | None = None

    # Related terms
    surrounding_terms: list[str] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)

    # Quality metrics
    context_similarity_threshold: float = 0.8
    confidence_score: float = 0.0

    def generate_context_hash(self) -> str:
        """Generate hash for context matching."""
        context_data = {
            "semantic_field": self.semantic_field,
            "philosophical_domain": self.philosophical_domain,
            "author": self.author,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "surrounding_terms": sorted(self.surrounding_terms),
            "related_concepts": sorted(self.related_concepts),
        }

        context_str = json.dumps(context_data, sort_keys=True)
        return hashlib.sha256(context_str.encode()).hexdigest()

    def calculate_similarity(self, other: TranslationContext) -> float:
        """Calculate similarity with another context."""
        if not isinstance(other, TranslationContext):
            return 0.0

        similarity_factors = []

        # Semantic field similarity
        if self.semantic_field and other.semantic_field:
            similarity_factors.append(
                1.0 if self.semantic_field == other.semantic_field else 0.0
            )

        # Philosophical domain similarity
        if self.philosophical_domain and other.philosophical_domain:
            similarity_factors.append(
                1.0 if self.philosophical_domain == other.philosophical_domain else 0.0
            )

        # Author similarity
        if self.author and other.author:
            similarity_factors.append(1.0 if self.author == other.author else 0.0)

        # Language pair similarity
        lang_match = (
            self.source_language == other.source_language
            and self.target_language == other.target_language
        )
        similarity_factors.append(1.0 if lang_match else 0.0)

        # Surrounding terms overlap
        if self.surrounding_terms and other.surrounding_terms:
            overlap = set(self.surrounding_terms) & set(other.surrounding_terms)
            total_terms = set(self.surrounding_terms) | set(other.surrounding_terms)
            term_similarity = len(overlap) / len(total_terms) if total_terms else 0.0
            similarity_factors.append(term_similarity)

        # Related concepts overlap
        if self.related_concepts and other.related_concepts:
            overlap = set(self.related_concepts) & set(other.related_concepts)
            total_concepts = set(self.related_concepts) | set(other.related_concepts)
            concept_similarity = (
                len(overlap) / len(total_concepts) if total_concepts else 0.0
            )
            similarity_factors.append(concept_similarity)

        # Calculate weighted average
        if similarity_factors:
            return sum(similarity_factors) / len(similarity_factors)

        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "sentence_context": self.sentence_context,
            "paragraph_context": self.paragraph_context,
            "document_context": self.document_context,
            "semantic_field": self.semantic_field,
            "philosophical_domain": self.philosophical_domain,
            "author": self.author,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "page_number": self.page_number,
            "chapter": self.chapter,
            "section": self.section,
            "surrounding_terms": self.surrounding_terms,
            "related_concepts": self.related_concepts,
            "context_similarity_threshold": self.context_similarity_threshold,
            "confidence_score": self.confidence_score,
            "context_hash": self.generate_context_hash(),
        }


@dataclass
class UserChoice:
    """Individual user choice for neologism translation."""

    # Core choice data
    choice_id: str
    neologism_term: str
    choice_type: ChoiceType
    translation_result: str = ""

    # Context information
    context: TranslationContext = field(default_factory=TranslationContext)

    # Choice metadata
    choice_scope: ChoiceScope = ChoiceScope.CONTEXTUAL
    confidence_level: float = 1.0
    user_notes: str = ""

    # Temporal information
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used_at: str | None = None

    # Usage tracking
    usage_count: int = 0
    success_rate: float = 1.0

    # Relationship data
    session_id: str | None = None
    document_id: str | None = None
    parent_choice_id: str | None = None

    # Validation and quality
    is_validated: bool = False
    validation_source: str = ""
    quality_score: float = 0.0

    # Export/import metadata
    export_tags: set[str] = field(default_factory=set)
    import_source: str = ""

    def update_usage_stats(self, success: bool = True) -> None:
        """Update usage statistics."""
        self.usage_count += 1
        self.last_used_at = datetime.now().isoformat()

        # Update success rate using exponential moving average
        alpha = 0.1  # Learning rate
        if success:
            self.success_rate = self.success_rate * (1 - alpha) + alpha
        else:
            self.success_rate = self.success_rate * (1 - alpha)

        self.updated_at = datetime.now().isoformat()

    def is_applicable_to_context(self, target_context: TranslationContext) -> bool:
        """Check if choice is applicable to a given context."""
        if self.choice_scope == ChoiceScope.GLOBAL:
            return True

        if self.choice_scope == ChoiceScope.SESSION:
            return target_context.document_context == self.context.document_context

        if self.choice_scope == ChoiceScope.DOCUMENT:
            return target_context.document_context == self.context.document_context

        if self.choice_scope == ChoiceScope.CONTEXTUAL:
            similarity = self.context.calculate_similarity(target_context)
            return similarity >= self.context.context_similarity_threshold

        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "choice_id": self.choice_id,
            "neologism_term": self.neologism_term,
            "choice_type": self.choice_type.value,
            "translation_result": self.translation_result,
            "context": self.context.to_dict(),
            "choice_scope": self.choice_scope.value,
            "confidence_level": self.confidence_level,
            "user_notes": self.user_notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
            "session_id": self.session_id,
            "document_id": self.document_id,
            "parent_choice_id": self.parent_choice_id,
            "is_validated": self.is_validated,
            "validation_source": self.validation_source,
            "quality_score": self.quality_score,
            "export_tags": list(self.export_tags),
            "import_source": self.import_source,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


@dataclass
class ChoiceSession:
    """Session for tracking user choices during translation."""

    # Session identification
    session_id: str
    session_name: str = ""

    # Session metadata
    status: SessionStatus = SessionStatus.ACTIVE
    document_id: str | None = None
    document_name: str = ""

    # User and context
    user_id: str | None = None
    source_language: str = ""
    target_language: str = ""

    # Temporal information
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    # Session statistics
    total_choices: int = 0
    translate_count: int = 0
    preserve_count: int = 0
    custom_count: int = 0
    skip_count: int = 0

    # Quality metrics
    average_confidence: float = 0.0
    consistency_score: float = 0.0

    # Configuration
    auto_apply_choices: bool = True
    conflict_resolution_strategy: ConflictResolution = (
        ConflictResolution.CONTEXT_SPECIFIC
    )

    # Session notes and tags
    session_notes: str = ""
    session_tags: set[str] = field(default_factory=set)

    def add_choice_stats(self, choice: UserChoice) -> None:
        """Add choice statistics to session."""
        self.total_choices += 1

        if choice.choice_type == ChoiceType.TRANSLATE:
            self.translate_count += 1
        elif choice.choice_type == ChoiceType.PRESERVE:
            self.preserve_count += 1
        elif choice.choice_type == ChoiceType.CUSTOM_TRANSLATION:
            self.custom_count += 1
        elif choice.choice_type == ChoiceType.SKIP:
            self.skip_count += 1

        # Update average confidence
        if self.total_choices > 0:
            self.average_confidence = (
                self.average_confidence * (self.total_choices - 1)
                + choice.confidence_level
            ) / self.total_choices

        self.updated_at = datetime.now().isoformat()

    def complete_session(self) -> None:
        """Mark session as completed."""
        self.status = SessionStatus.COMPLETED
        self.completed_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def calculate_consistency_score(self, choices: list[UserChoice]) -> float:
        """Calculate consistency score based on choices."""
        if len(choices) < 2:
            return 1.0

        # Group similar terms
        term_groups = {}
        for choice in choices:
            term_key = choice.neologism_term.lower()
            if term_key not in term_groups:
                term_groups[term_key] = []
            term_groups[term_key].append(choice)

        # Calculate consistency within groups
        consistency_scores = []
        for _term, term_choices in term_groups.items():
            if len(term_choices) < 2:
                consistency_scores.append(1.0)
                continue

            # Check if all choices are the same
            choice_types = [c.choice_type for c in term_choices]
            translations = [c.translation_result for c in term_choices]

            type_consistency = len(set(choice_types)) == 1
            translation_consistency = len(set(translations)) == 1

            consistency = 1.0 if type_consistency and translation_consistency else 0.5
            consistency_scores.append(consistency)

        return (
            sum(consistency_scores) / len(consistency_scores)
            if consistency_scores
            else 1.0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "status": self.status.value,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "user_id": self.user_id,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "total_choices": self.total_choices,
            "translate_count": self.translate_count,
            "preserve_count": self.preserve_count,
            "custom_count": self.custom_count,
            "skip_count": self.skip_count,
            "average_confidence": self.average_confidence,
            "consistency_score": self.consistency_score,
            "auto_apply_choices": self.auto_apply_choices,
            "conflict_resolution_strategy": self.conflict_resolution_strategy.value,
            "session_notes": self.session_notes,
            "session_tags": list(self.session_tags),
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


@dataclass
class ChoiceConflict:
    """Represents a conflict between user choices."""

    # Conflict identification
    conflict_id: str
    neologism_term: str

    # Conflicting choices
    choice_a: UserChoice
    choice_b: UserChoice

    # Conflict analysis
    conflict_type: str = "translation_mismatch"
    severity: float = 0.5
    context_similarity: float = 0.0

    # Resolution information
    resolution_strategy: ConflictResolution = ConflictResolution.LATEST_WINS
    resolved_choice_id: str | None = None
    resolution_notes: str = ""

    # Temporal information
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: str | None = None

    # Metadata
    session_id: str | None = None
    auto_resolved: bool = False

    def analyze_conflict(self) -> None:
        """Analyze the conflict and set metrics."""
        self.context_similarity = self.choice_a.context.calculate_similarity(
            self.choice_b.context
        )

        # Determine conflict type
        if self.choice_a.choice_type != self.choice_b.choice_type:
            self.conflict_type = "choice_type_mismatch"
        elif self.choice_a.translation_result != self.choice_b.translation_result:
            self.conflict_type = "translation_mismatch"
        else:
            self.conflict_type = "context_mismatch"

        # Calculate severity
        if self.context_similarity > 0.8:
            self.severity = 0.9  # High severity for similar contexts
        elif self.context_similarity > 0.5:
            self.severity = 0.6  # Medium severity
        else:
            self.severity = 0.3  # Low severity for different contexts

    def resolve_conflict(
        self, resolution_strategy: ConflictResolution
    ) -> str | None:
        """Resolve conflict and return winning choice ID."""
        self.resolution_strategy = resolution_strategy

        if resolution_strategy == ConflictResolution.LATEST_WINS:
            # Compare creation timestamps
            if self.choice_a.created_at > self.choice_b.created_at:
                self.resolved_choice_id = self.choice_a.choice_id
            else:
                self.resolved_choice_id = self.choice_b.choice_id

        elif resolution_strategy == ConflictResolution.HIGHEST_CONFIDENCE:
            # Compare confidence levels
            if self.choice_a.confidence_level > self.choice_b.confidence_level:
                self.resolved_choice_id = self.choice_a.choice_id
            else:
                self.resolved_choice_id = self.choice_b.choice_id

        elif resolution_strategy == ConflictResolution.CONTEXT_SPECIFIC:
            # Keep both choices for context-specific application
            self.resolved_choice_id = None
            self.resolution_notes = "Both choices kept for context-specific application"

        self.resolved_at = datetime.now().isoformat()
        self.auto_resolved = True

        return self.resolved_choice_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "conflict_id": self.conflict_id,
            "neologism_term": self.neologism_term,
            "choice_a": self.choice_a.to_dict(),
            "choice_b": self.choice_b.to_dict(),
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "context_similarity": self.context_similarity,
            "resolution_strategy": self.resolution_strategy.value,
            "resolved_choice_id": self.resolved_choice_id,
            "resolution_notes": self.resolution_notes,
            "detected_at": self.detected_at,
            "resolved_at": self.resolved_at,
            "session_id": self.session_id,
            "auto_resolved": self.auto_resolved,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


@dataclass
class TranslationPreference:
    """User preferences for translation behavior."""

    # Identification
    preference_id: str
    user_id: str | None = None

    # Translation preferences
    default_choice_scope: ChoiceScope = ChoiceScope.CONTEXTUAL
    default_conflict_resolution: ConflictResolution = (
        ConflictResolution.CONTEXT_SPECIFIC
    )

    # Matching preferences
    context_similarity_threshold: float = 0.8
    auto_apply_similar_choices: bool = True

    # Quality preferences
    min_confidence_threshold: float = 0.5
    require_validation: bool = False

    # Language pair preferences
    language_pair_preferences: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Domain preferences
    domain_preferences: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Export/import preferences
    export_format: str = "json"
    include_context: bool = True
    include_statistics: bool = True

    # Temporal information
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def update_language_preference(
        self, source_lang: str, target_lang: str, preferences: dict[str, Any]
    ) -> None:
        """Update preferences for a specific language pair."""
        key = f"{source_lang}-{target_lang}"
        self.language_pair_preferences[key] = preferences
        self.updated_at = datetime.now().isoformat()

    def update_domain_preference(
        self, domain: str, preferences: dict[str, Any]
    ) -> None:
        """Update preferences for a specific domain."""
        self.domain_preferences[domain] = preferences
        self.updated_at = datetime.now().isoformat()

    def get_language_preference(
        self, source_lang: str, target_lang: str
    ) -> dict[str, Any]:
        """Get preferences for a specific language pair."""
        key = f"{source_lang}-{target_lang}"
        return self.language_pair_preferences.get(key, {})

    def get_domain_preference(self, domain: str) -> dict[str, Any]:
        """Get preferences for a specific domain."""
        return self.domain_preferences.get(domain, {})

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "preference_id": self.preference_id,
            "user_id": self.user_id,
            "default_choice_scope": self.default_choice_scope.value,
            "default_conflict_resolution": self.default_conflict_resolution.value,
            "context_similarity_threshold": self.context_similarity_threshold,
            "auto_apply_similar_choices": self.auto_apply_similar_choices,
            "min_confidence_threshold": self.min_confidence_threshold,
            "require_validation": self.require_validation,
            "language_pair_preferences": self.language_pair_preferences,
            "domain_preferences": self.domain_preferences,
            "export_format": self.export_format,
            "include_context": self.include_context,
            "include_statistics": self.include_statistics,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# Helper functions for working with user choice data


def create_choice_id(neologism_term: str, context_hash: str) -> str:
    """Create a unique choice ID."""
    data = f"{neologism_term}:{context_hash}:{datetime.now().isoformat()}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def create_session_id() -> str:
    """Create a unique session ID."""
    data = f"session:{datetime.now().isoformat()}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def create_conflict_id(choice_a_id: str, choice_b_id: str) -> str:
    """Create a unique conflict ID."""
    data = f"conflict:{choice_a_id}:{choice_b_id}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def filter_choices_by_context(
    choices: list[UserChoice], target_context: TranslationContext
) -> list[UserChoice]:
    """Filter choices that are applicable to a given context."""
    return [
        choice for choice in choices if choice.is_applicable_to_context(target_context)
    ]


def find_best_matching_choice(
    choices: list[UserChoice], target_context: TranslationContext
) -> UserChoice | None:
    """Find the best matching choice for a given context."""
    applicable_choices = filter_choices_by_context(choices, target_context)

    if not applicable_choices:
        return None

    # Sort by combination of context similarity and usage success
    def choice_score(choice: UserChoice) -> float:
        similarity = choice.context.calculate_similarity(target_context)
        return (similarity * 0.6) + (choice.success_rate * 0.4)

    return max(applicable_choices, key=choice_score)


def detect_choice_conflicts(
    choices: list[UserChoice], similarity_threshold: float = 0.8
) -> list[ChoiceConflict]:
    """Detect conflicts between user choices."""
    conflicts = []

    for i, choice_a in enumerate(choices):
        for choice_b in choices[i + 1 :]:
            # Check if choices are for the same term
            if choice_a.neologism_term.lower() != choice_b.neologism_term.lower():
                continue

            # Check if contexts are similar enough to be conflicting
            similarity = choice_a.context.calculate_similarity(choice_b.context)

            if similarity >= similarity_threshold:
                # Check if actual choices differ
                if (
                    choice_a.choice_type != choice_b.choice_type
                    or choice_a.translation_result != choice_b.translation_result
                ):
                    conflict = ChoiceConflict(
                        conflict_id=create_conflict_id(
                            choice_a.choice_id, choice_b.choice_id
                        ),
                        neologism_term=choice_a.neologism_term,
                        choice_a=choice_a,
                        choice_b=choice_b,
                        context_similarity=similarity,
                    )
                    conflict.analyze_conflict()
                    conflicts.append(conflict)

    return conflicts
