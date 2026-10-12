#!/usr/bin/env python3
"""Simple test runner for PhenomenalLayout to check basic functionality without pytest.

This script provides a lightweight test runner that doesn't require pytest.
It dynamically resolves the project root directory to ensure reliable imports
regardless of the execution location.
"""

import json
import math
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any


# Dynamically resolve the project root directory based on script location
# This ensures reliable imports regardless of where the script is executed from
def setup_project_path() -> str:
    """Set up the project path for reliable imports."""
    # Get the directory containing this script
    script_dir: Path = Path(__file__).resolve().parent

    # Get the actual project root (parent of scripts directory)
    project_root: str = str(script_dir.parent)
    if project_root not in sys.path:
        # Add at end to avoid overriding system packages
        sys.path.append(project_root)

    return project_root


# Set up the project path
PROJECT_ROOT: str = setup_project_path()  # side-effect: ensure repo root is on sys.path


def run_test(test_name: str, test_func: Callable[[], None]) -> bool:
    """Run a single test function."""
    try:
        print(f"Running {test_name}...")
        test_func()
        print(f"✓ {test_name} PASSED")
        return True
    except Exception as e:
        print(f"✗ {test_name} FAILED: {e}")
        traceback.print_exc()
        return False


def test_user_choice_models() -> None:
    """Test user choice models basic functionality."""
    from models.user_choice_models import (
        ChoiceScope,
        ChoiceType,
        TranslationContext,
        UserChoice,
        create_choice_id,
    )

    # Test TranslationContext creation
    context: TranslationContext = TranslationContext(
        sentence_context="Test sentence",
        semantic_field="test",
        philosophical_domain="test",
        author="test",
        source_language="en",
        target_language="de",
    )

    # Test UserChoice creation
    choice: UserChoice = UserChoice(
        choice_id="test_id",
        neologism_term="test_term",
        choice_type=ChoiceType.TRANSLATE,
        choice_scope=ChoiceScope.SESSION,
        context=context,
        translation_result="test_translation",
    )

    # Verify the choice was created successfully
    assert choice.choice_id == "test_id"
    assert choice.neologism_term == "test_term"

    # Test create_choice_id function
    choice_id: str = create_choice_id("test_term", "test_hash")
    assert len(choice_id) == 16, f"Expected length 16, got {len(choice_id)}"
    assert choice_id.isalnum(), f"Choice ID should be alphanumeric, got: {choice_id}"

    print("User choice models test completed successfully")


def test_choice_database() -> None:
    """Test choice database basic functionality."""
    import os
    import tempfile

    from database.choice_database import ChoiceDatabase
    from models.user_choice_models import (
        ChoiceScope,
        ChoiceType,
        TranslationContext,
        UserChoice,
    )

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path: str = tmp.name

    try:
        # Test database creation
        db: ChoiceDatabase = ChoiceDatabase(db_path)

        # Verify database was created
        assert db is not None

        # Test context creation
        context: TranslationContext = TranslationContext(
            sentence_context="Test sentence",
            semantic_field="test",
            philosophical_domain="test",
            author="test",
            source_language="en",
            target_language="de",
        )

        # Test choice creation
        choice: UserChoice = UserChoice(
            choice_id="test_id",
            neologism_term="test_term",
            choice_type=ChoiceType.TRANSLATE,
            choice_scope=ChoiceScope.SESSION,
            context=context,
            translation_result="test_translation",
        )

        # Test basic database operations
        db.save_user_choice(choice)
        retrieved_choice: Any = db.get_user_choice("test_id")
        assert retrieved_choice is not None, "Failed to retrieve saved choice"

        # Verify the choice was created successfully
        assert choice.choice_id == "test_id"

        print("Choice database test completed successfully")

    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_neologism_models() -> None:
    """Test neologism models basic functionality."""
    from models.neologism_models import (
        ConfidenceFactors,
        ConfidenceLevel,
        DetectedNeologism,
        MorphologicalAnalysis,
        NeologismType,
        PhilosophicalContext,
    )

    # Test NeologismType enum
    assert NeologismType.COMPOUND.value == "compound"
    assert NeologismType.PHILOSOPHICAL_TERM.value == "philosophical_term"
    assert NeologismType.TECHNICAL_TERM.value == "technical_term"
    assert NeologismType.DERIVED.value == "derived"
    assert NeologismType.UNKNOWN.value == "unknown"
    print("✓ NeologismType enum validation passed")

    # Test ConfidenceLevel enum
    assert ConfidenceLevel.HIGH.value == "high"
    assert ConfidenceLevel.MEDIUM.value == "medium"
    assert ConfidenceLevel.LOW.value == "low"
    assert ConfidenceLevel.UNCERTAIN.value == "uncertain"
    print("✓ ConfidenceLevel enum validation passed")

    # Test MorphologicalAnalysis creation and attributes
    analysis: MorphologicalAnalysis = MorphologicalAnalysis(
        root_words=["test", "word"],
        prefixes=["pre", "sub"],
        suffixes=["ing", "ed"],
        is_compound=True,
        compound_parts=["test", "word"],
        compound_pattern="noun+noun",
        word_length=8,
        syllable_count=2,
        morpheme_count=3,
        structural_complexity=0.75,
        morphological_productivity=0.6,
    )

    # Verify all MorphologicalAnalysis attributes
    assert analysis.root_words == [
        "test",
        "word",
    ], f"Expected ['test', 'word'], got {analysis.root_words}"
    assert analysis.prefixes == [
        "pre",
        "sub",
    ], f"Expected ['pre', 'sub'], got {analysis.prefixes}"
    assert analysis.suffixes == [
        "ing",
        "ed",
    ], f"Expected ['ing', 'ed'], got {analysis.suffixes}"
    assert analysis.is_compound is True, f"Expected True, got {analysis.is_compound}"
    assert analysis.compound_parts == [
        "test",
        "word",
    ], f"Expected ['test', 'word'], got {analysis.compound_parts}"
    assert (
        analysis.compound_pattern == "noun+noun"
    ), f"Expected 'noun+noun', got {analysis.compound_pattern}"
    assert analysis.word_length == 8, f"Expected 8, got {analysis.word_length}"
    assert analysis.syllable_count == 2, f"Expected 2, got {analysis.syllable_count}"
    assert analysis.morpheme_count == 3, f"Expected 3, got {analysis.morpheme_count}"
    assert (
        analysis.structural_complexity == 0.75
    ), f"Expected 0.75, got {analysis.structural_complexity}"
    assert (
        analysis.morphological_productivity == 0.6
    ), f"Expected 0.6, got {analysis.morphological_productivity}"

    # Test to_dict method
    analysis_dict: dict[str, Any] = analysis.to_dict()
    assert isinstance(analysis_dict, dict), "to_dict should return a dictionary"
    assert "root_words" in analysis_dict, "Dictionary should contain 'root_words' key"
    assert (
        analysis_dict["is_compound"] is True
    ), "Dictionary should preserve boolean values"
    print("✓ MorphologicalAnalysis creation and validation passed")

    # Test PhilosophicalContext creation and attributes
    phil_context: PhilosophicalContext = PhilosophicalContext(
        philosophical_density=0.8,
        semantic_field="epistemology",
        domain_indicators=["knowledge", "belief"],
        surrounding_terms=["concept", "theory"],
        philosophical_keywords=["consciousness", "reality"],
        conceptual_clusters=["mind", "perception"],
        author_terminology=["Bewusstsein", "Wirklichkeit"],
        text_genre="philosophical_treatise",
        historical_period="20th_century",
        related_concepts=["phenomenology", "ontology"],
        semantic_network={"consciousness": ["awareness", "perception"]},
    )

    # Verify PhilosophicalContext attributes
    assert (
        phil_context.philosophical_density == 0.8
    ), f"Expected 0.8, got {phil_context.philosophical_density}"
    assert (
        phil_context.semantic_field == "epistemology"
    ), f"Expected 'epistemology', got {phil_context.semantic_field}"
    assert phil_context.domain_indicators == [
        "knowledge",
        "belief",
    ], f"Expected ['knowledge', 'belief'], got {phil_context.domain_indicators}"
    assert phil_context.surrounding_terms == [
        "concept",
        "theory",
    ], f"Expected ['concept', 'theory'], got {phil_context.surrounding_terms}"
    assert phil_context.philosophical_keywords == [
        "consciousness",
        "reality",
    ], f"Expected ['consciousness', 'reality'], got {phil_context.philosophical_keywords}"
    assert (
        phil_context.text_genre == "philosophical_treatise"
    ), f"Expected 'philosophical_treatise', got {phil_context.text_genre}"

    # Test PhilosophicalContext to_dict method
    phil_dict: dict[str, Any] = phil_context.to_dict()
    assert isinstance(
        phil_dict, dict
    ), "PhilosophicalContext to_dict should return a dictionary"
    assert (
        "philosophical_density" in phil_dict
    ), "Dictionary should contain 'philosophical_density' key"
    assert (
        phil_dict["semantic_field"] == "epistemology"
    ), "Dictionary should preserve string values"
    print("✓ PhilosophicalContext creation and validation passed")

    # Test ConfidenceFactors creation and attributes
    confidence_factors: ConfidenceFactors = ConfidenceFactors(
        morphological_complexity=0.7,
        compound_structure_score=0.8,
        morphological_productivity=0.6,
        context_density=0.9,
        philosophical_indicators=0.85,
        semantic_coherence=0.75,
        rarity_score=0.9,
        frequency_deviation=0.8,
        corpus_novelty=0.95,
    )

    # Verify ConfidenceFactors attributes
    assert (
        confidence_factors.morphological_complexity == 0.7
    ), f"Expected 0.7, got {confidence_factors.morphological_complexity}"
    assert (
        confidence_factors.compound_structure_score == 0.8
    ), f"Expected 0.8, got {confidence_factors.compound_structure_score}"
    assert (
        confidence_factors.context_density == 0.9
    ), f"Expected 0.9, got {confidence_factors.context_density}"
    assert (
        confidence_factors.rarity_score == 0.9
    ), f"Expected 0.9, got {confidence_factors.rarity_score}"

    # Test ConfidenceFactors weighted score calculation
    weighted_score: float = confidence_factors.calculate_weighted_score()
    assert isinstance(weighted_score, float), "Weighted score should be a float"
    assert (
        0.0 <= weighted_score <= 1.0
    ), f"Weighted score should be between 0 and 1, got {weighted_score}"

    # Test ConfidenceFactors to_dict method
    factors_dict: dict[str, Any] = confidence_factors.to_dict()
    assert isinstance(
        factors_dict, dict
    ), "ConfidenceFactors to_dict should return a dictionary"
    assert (
        "morphological_complexity" in factors_dict
    ), "Dictionary should contain 'morphological_complexity' key"
    assert (
        "weighted_score" in factors_dict
    ), "Dictionary should contain calculated 'weighted_score'"
    print("✓ ConfidenceFactors creation and validation passed")

    # Test DetectedNeologism creation and attributes
    detected_neologism: DetectedNeologism = DetectedNeologism(
        term="Wirklichkeitsbewusstsein",
        confidence=0.85,
        neologism_type=NeologismType.COMPOUND,
        start_pos=10,
        end_pos=33,
        sentence_context="Das Wirklichkeitsbewusstsein ist wichtig.",
        paragraph_context="Ein längerer Kontext...",
        morphological_analysis=analysis,
        philosophical_context=phil_context,
        confidence_factors=confidence_factors,
        detection_timestamp="2024-01-01T12:00:00",
        source_text_id="test_text_001",
        page_number=42,
        translation_suggestions=["reality consciousness", "awareness of reality"],
        glossary_candidates=["Realitätsbewusstsein", "Wirklichkeitswahrnehmung"],
        related_terms=["Bewusstsein", "Wirklichkeit", "Realität"],
    )

    # Verify DetectedNeologism attributes
    assert (
        detected_neologism.term == "Wirklichkeitsbewusstsein"
    ), f"Expected 'Wirklichkeitsbewusstsein', got {detected_neologism.term}"
    assert (
        detected_neologism.confidence == 0.85
    ), f"Expected 0.85, got {detected_neologism.confidence}"
    assert (
        detected_neologism.neologism_type == NeologismType.COMPOUND
    ), f"Expected NeologismType.COMPOUND, got {detected_neologism.neologism_type}"
    assert (
        detected_neologism.start_pos == 10
    ), f"Expected 10, got {detected_neologism.start_pos}"
    assert (
        detected_neologism.end_pos == 33
    ), f"Expected 33, got {detected_neologism.end_pos}"
    assert (
        detected_neologism.sentence_context
        == "Das Wirklichkeitsbewusstsein ist wichtig."
    ), f"Expected sentence context, got {detected_neologism.sentence_context}"
    assert (
        detected_neologism.page_number == 42
    ), f"Expected 42, got {detected_neologism.page_number}"
    assert (
        len(detected_neologism.translation_suggestions) == 2
    ), f"Expected 2 translation suggestions, got {len(detected_neologism.translation_suggestions)}"
    assert (
        len(detected_neologism.related_terms) == 3
    ), f"Expected 3 related terms, got {len(detected_neologism.related_terms)}"

    # Test confidence_level property
    confidence_level: ConfidenceLevel = detected_neologism.confidence_level
    assert (
        confidence_level == ConfidenceLevel.HIGH
    ), f"Expected ConfidenceLevel.HIGH for confidence 0.85, got {confidence_level}"

    # Test DetectedNeologism to_dict method
    neologism_dict: dict[str, Any] = detected_neologism.to_dict()
    assert isinstance(
        neologism_dict, dict
    ), "DetectedNeologism to_dict should return a dictionary"
    assert "term" in neologism_dict, "Dictionary should contain 'term' key"
    assert "confidence" in neologism_dict, "Dictionary should contain 'confidence' key"
    assert (
        "confidence_level" in neologism_dict
    ), "Dictionary should contain 'confidence_level' key"
    assert (
        "morphological_analysis" in neologism_dict
    ), "Dictionary should contain 'morphological_analysis' key"
    assert (
        neologism_dict["term"] == "Wirklichkeitsbewusstsein"
    ), "Dictionary should preserve term value"
    assert (
        neologism_dict["confidence_level"] == "high"
    ), "Dictionary should contain confidence level as string"

    # Test DetectedNeologism to_json method
    neologism_json: str = detected_neologism.to_json()
    assert isinstance(neologism_json, str), "to_json should return a string"
    data = json.loads(neologism_json)
    assert (
        data.get("term") == "Wirklichkeitsbewusstsein"
    ), "JSON should contain the term"
    assert "confidence" in data, "JSON should contain 'confidence' key"
    conf_val = data["confidence"]
    assert isinstance(conf_val, (int, float)) and not isinstance(
        conf_val, bool
    ), f"JSON 'confidence' should be a number (int/float) but not bool, got {conf_val!r}"
    conf_val = float(conf_val)
    assert math.isfinite(
        conf_val
    ), f"JSON 'confidence' should be finite (not NaN/Inf), got {conf_val}"
    assert (
        0.0 <= conf_val <= 1.0
    ), f"JSON 'confidence' should be between 0.0 and 1.0, got {conf_val}"
    assert math.isclose(
        conf_val, 0.85, abs_tol=1e-9
    ), f"JSON 'confidence' should be 0.85, got {conf_val}"
    print("✓ DetectedNeologism creation and validation passed")

    print("Neologism models test completed successfully")


def main() -> None:
    """Run all tests."""
    print("Starting simple test runner...")

    tests: list[tuple[str, Callable[[], None]]] = [
        ("User Choice Models", test_user_choice_models),
        ("Choice Database", test_choice_database),
        ("Neologism Models", test_neologism_models),
    ]

    passed: int = 0
    failed: int = 0

    for test_name, test_func in tests:
        if run_test(test_name, test_func):
            passed += 1
        else:
            failed += 1

    print(f"\nTest Results: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)
    else:
        print("All tests passed!")


if __name__ == "__main__":
    main()
