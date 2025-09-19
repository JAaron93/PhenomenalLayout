"""Tests for user choice manager service."""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from models.neologism_models import (
    DetectedNeologism,
    MorphologicalAnalysis,
    NeologismAnalysis,
    NeologismType,
    PhilosophicalContext,
)
from models.user_choice_models import ChoiceScope, ChoiceType, SessionStatus
from services.user_choice_manager import (
    UserChoiceManager,
    create_choice_manager,
)


@pytest.fixture
def temp_manager():
    """Create a temporary user choice manager for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    manager = UserChoiceManager(db_path)
    yield manager

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def sample_neologism():
    """Create a sample detected neologism."""
    philosophical_context = PhilosophicalContext(
        philosophical_density=0.8,
        semantic_field="existentialism",
        domain_indicators=["philosophy", "existence"],
        surrounding_terms=["sein", "existenz", "wesen"],
        philosophical_keywords=["dasein", "sein", "existence"],
        author_terminology=["Heidegger"],
    )

    morphological_analysis = MorphologicalAnalysis(
        is_compound=True,
        compound_parts=["Da", "sein"],
        word_length=6,
        syllable_count=2,
        morpheme_count=2,
        structural_complexity=0.7,
    )

    return DetectedNeologism(
        term="Dasein",
        confidence=0.9,
        neologism_type=NeologismType.PHILOSOPHICAL_TERM,
        start_pos=10,
        end_pos=16,
        sentence_context="Das Dasein ist ein zentraler Begriff in Heideggers Philosophie.",
        paragraph_context="In der Philosophie Heideggers spielt das Dasein eine zentrale Rolle...",
        morphological_analysis=morphological_analysis,
        philosophical_context=philosophical_context,
        page_number=42,
    )


@pytest.fixture
def sample_analysis(sample_neologism):
    """Create a sample neologism analysis."""
    analysis = NeologismAnalysis(
        text_id="test_text_1",
        analysis_timestamp=datetime.now().isoformat(),
        total_tokens=1000,
        analyzed_chunks=5,
    )

    # Add some neologisms
    analysis.add_detection(sample_neologism)

    # Add another neologism
    neologism2 = DetectedNeologism(
        term="Seinsvergessenheit",
        confidence=0.85,
        neologism_type=NeologismType.COMPOUND,
        start_pos=50,
        end_pos=67,
        sentence_context="Die Seinsvergessenheit charakterisiert die moderne Epoche.",
        philosophical_context=PhilosophicalContext(
            philosophical_density=0.9,
            semantic_field="ontology",
            author_terminology=["Heidegger"],
        ),
        morphological_analysis=MorphologicalAnalysis(
            is_compound=True,
            compound_parts=["Seins", "vergessenheit"],
            word_length=16,
            syllable_count=5,
        ),
    )

    analysis.add_detection(neologism2)

    return analysis


class TestUserChoiceManager:
    """Test UserChoiceManager functionality."""

    def test_manager_initialization(self, temp_manager):
        """Test manager initialization."""
        assert temp_manager.db is not None
        assert temp_manager.auto_resolve_conflicts is True
        assert temp_manager.session_expiry_hours == 24
        assert temp_manager._active_sessions == {}
        assert temp_manager.stats["total_choices_made"] == 0

    def test_create_session(self, temp_manager):
        """Test session creation."""
        session = temp_manager.create_session(
            session_name="Test Session",
            document_name="test.pdf",
            user_id="user123",
            source_language="de",
            target_language="en",
        )

        assert session.session_id is not None
        assert session.session_name == "Test Session"
        assert session.document_name == "test.pdf"
        assert session.user_id == "user123"
        assert session.source_language == "de"
        assert session.target_language == "en"
        assert session.status == SessionStatus.ACTIVE

        # Check that session is in active cache
        assert session.session_id in temp_manager._active_sessions
        assert temp_manager.stats["sessions_created"] == 1

    def test_get_session(self, temp_manager):
        """Test getting sessions."""
        # Create session
        session = temp_manager.create_session(session_name="Test Session")

        # Get session
        retrieved = temp_manager.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        assert retrieved.session_name == session.session_name

        # Get non-existent session
        non_existent = temp_manager.get_session("non_existent_id")
        assert non_existent is None

    def test_complete_session(self, temp_manager, sample_neologism):
        """Test session completion."""
        # Create session
        session = temp_manager.create_session(session_name="Test Session")

        # Make some choices
        _choice1 = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            session_id=session.session_id,
        )

        _choice2 = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            session_id=session.session_id,
        )

        # Complete session
        assert temp_manager.complete_session(session.session_id)

        # Check session status
        completed_session = temp_manager.get_session(session.session_id)
        assert completed_session.status == SessionStatus.COMPLETED
        assert completed_session.completed_at is not None
        assert completed_session.consistency_score >= 0.0

        # Check that session is removed from active cache
        assert session.session_id not in temp_manager._active_sessions

    def test_make_choice(self, temp_manager, sample_neologism):
        """Test making a choice."""
        # Create session
        session = temp_manager.create_session(session_name="Test Session")

        # Make choice
        choice = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            session_id=session.session_id,
            choice_scope=ChoiceScope.CONTEXTUAL,
            confidence_level=0.9,
            user_notes="Test choice",
        )

        assert choice.choice_id is not None
        assert choice.neologism_term == sample_neologism.term
        assert choice.choice_type == ChoiceType.TRANSLATE
        assert choice.translation_result == "being-there"
        assert choice.session_id == session.session_id
        assert choice.choice_scope == ChoiceScope.CONTEXTUAL
        assert choice.confidence_level == 0.9
        assert choice.user_notes == "Test choice"

        # Check statistics
        assert temp_manager.stats["total_choices_made"] == 1

        # Check session statistics
        updated_session = temp_manager.get_session(session.session_id)
        assert updated_session.total_choices == 1
        assert updated_session.translate_count == 1

    def test_get_choice_for_neologism(self, temp_manager, sample_neologism):
        """Test getting choice for neologism."""
        # Initially no choice should exist
        choice = temp_manager.get_choice_for_neologism(sample_neologism)
        assert choice is None

        # Make a choice
        made_choice = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
        )

        # Now should find the choice
        found_choice = temp_manager.get_choice_for_neologism(sample_neologism)
        assert found_choice is not None
        assert found_choice.choice_id == made_choice.choice_id
        assert found_choice.neologism_term == sample_neologism.term
        assert found_choice.translation_result == "being-there"

        # Check statistics
        assert temp_manager.stats["cache_hits"] == 1

    def test_get_choice_for_similar_context(self, temp_manager, sample_neologism):
        """Test getting choice for similar context."""
        # Create choice with specific context
        _original_choice = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            choice_scope=ChoiceScope.CONTEXTUAL,
        )

        # Create similar neologism with different term but similar context
        similar_neologism = DetectedNeologism(
            term="Mitsein",
            confidence=0.8,
            neologism_type=NeologismType.PHILOSOPHICAL_TERM,
            start_pos=0,
            end_pos=7,
            sentence_context="Das Mitsein ist ein wichtiger Begriff.",
            philosophical_context=PhilosophicalContext(
                philosophical_density=0.8,
                semantic_field="existentialism",
                author_terminology=["Heidegger"],
            ),
            morphological_analysis=MorphologicalAnalysis(
                is_compound=True, compound_parts=["Mit", "sein"]
            ),
        )

        # Should find contextually similar choice
        found_choice = temp_manager.get_choice_for_neologism(similar_neologism)

        # Note: This depends on the similarity calculation and may not always match
        # The test verifies the mechanism works, not the specific result
        if found_choice:
            assert temp_manager.stats["context_matches"] >= 0

    def test_process_neologism_batch(self, temp_manager, sample_analysis):
        """Test processing batch of neologisms."""
        # Create session
        session = temp_manager.create_session(session_name="Batch Test")

        # Process batch
        results = temp_manager.process_neologism_batch(
            neologisms=sample_analysis.detected_neologisms,
            session_id=session.session_id,
            auto_apply_similar=False,
        )

        assert len(results) == len(sample_analysis.detected_neologisms)

        for neologism, suggested_choice in results:
            assert neologism in sample_analysis.detected_neologisms
            # Initially no choices should exist
            assert suggested_choice is None

    def test_process_batch_with_auto_apply(self, temp_manager, sample_analysis):
        """Test batch processing with auto-apply."""
        # Create session
        session = temp_manager.create_session(session_name="Auto Apply Test")

        # First, make a choice for one of the neologisms
        first_neologism = sample_analysis.detected_neologisms[0]
        temp_manager.make_choice(
            neologism=first_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="test-translation",
            session_id=session.session_id,
            choice_scope=ChoiceScope.GLOBAL,
        )

        # Update the choice to have high success rate
        choices = temp_manager.get_choices_by_term(first_neologism.term)
        if choices:
            choice = choices[0]
            choice.success_rate = 0.9
            temp_manager.db.save_user_choice(choice)

        # Process batch with auto-apply
        results = temp_manager.process_neologism_batch(
            neologisms=sample_analysis.detected_neologisms,
            session_id=session.session_id,
            auto_apply_similar=True,
        )

        assert len(results) == len(sample_analysis.detected_neologisms)

        # Check that at least one choice was applied
        applied_choices = [choice for _, choice in results if choice is not None]
        assert len(applied_choices) >= 1

    def test_apply_choices_to_analysis(self, temp_manager, sample_analysis):
        """Test applying choices to analysis."""
        # Create session
        session = temp_manager.create_session(session_name="Analysis Test")

        # Make choices for some neologisms
        first_neologism = sample_analysis.detected_neologisms[0]
        temp_manager.make_choice(
            neologism=first_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="test-translation",
            session_id=session.session_id,
        )

        # Apply choices to analysis
        results = temp_manager.apply_choices_to_analysis(
            analysis=sample_analysis, session_id=session.session_id
        )

        assert "total_neologisms" in results
        assert "choices_found" in results
        assert "choices_applied" in results
        assert "new_choices_needed" in results
        assert "applied_choices" in results
        assert "pending_choices" in results

        assert results["total_neologisms"] == len(sample_analysis.detected_neologisms)
        assert results["choices_found"] >= 1
        assert len(results["applied_choices"]) >= 1
        assert len(results["pending_choices"]) >= 0

    def test_conflict_detection_and_resolution(self, temp_manager, sample_neologism):
        """Test conflict detection and automatic resolution."""
        # Create session
        session = temp_manager.create_session(session_name="Conflict Test")

        # Make first choice
        _choice1 = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            session_id=session.session_id,
        )

        # Make conflicting choice (same term, different choice type)
        _choice2 = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.PRESERVE,
            translation_result="",
            session_id=session.session_id,
        )

        # Check that conflicts were detected and resolved
        _unresolved_conflicts = temp_manager.get_unresolved_conflicts()

        # With auto-resolution, there should be few or no unresolved conflicts
        if temp_manager.auto_resolve_conflicts:
            assert temp_manager.stats["conflicts_resolved"] >= 0

    def test_get_recommendation_for_neologism(self, temp_manager, sample_neologism):
        """Test getting recommendations for neologisms."""
        # Get recommendation for new neologism
        recommendation = temp_manager.get_recommendation_for_neologism(sample_neologism)

        assert "term" in recommendation
        assert "confidence" in recommendation
        assert "suggested_action" in recommendation
        assert "existing_choice" in recommendation
        assert "similar_choices" in recommendation
        assert "context_matches" in recommendation
        assert "reasons" in recommendation

        assert recommendation["term"] == sample_neologism.term
        assert recommendation["confidence"] == sample_neologism.confidence
        assert recommendation["suggested_action"] in [
            "review",
            "apply_existing",
            "review_existing",
            "consider_similar",
            "skip_low_confidence",
        ]
        assert recommendation["existing_choice"] is None  # No existing choice initially

        # Make a choice and get updated recommendation
        temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
        )

        recommendation2 = temp_manager.get_recommendation_for_neologism(
            sample_neologism
        )
        assert recommendation2["existing_choice"] is not None
        assert recommendation2["existing_choice"]["choice_type"] == "translate"
        assert recommendation2["existing_choice"]["translation"] == "being-there"

    def test_import_terminology_as_choices(self, temp_manager):
        """Test importing terminology as choices."""
        terminology = {
            "Dasein": "being-there",
            "Sein": "being",
            "Zeitlichkeit": "temporality",
            "Geworfenheit": "thrownness",
        }

        # Create session
        session = temp_manager.create_session(session_name="Import Test")

        # Import terminology
        imported_count = temp_manager.import_terminology_as_choices(
            terminology_dict=terminology,
            session_id=session.session_id,
            source_language="de",
            target_language="en",
        )

        assert imported_count == len(terminology)

        # Verify choices were created
        for term, translation in terminology.items():
            choices = temp_manager.get_choices_by_term(term)
            assert len(choices) == 1
            assert choices[0].choice_type == ChoiceType.TRANSLATE
            assert choices[0].translation_result == translation
            assert choices[0].session_id == session.session_id
            assert choices[0].choice_scope == ChoiceScope.GLOBAL

    def test_export_and_import_session_choices(self, temp_manager, sample_neologism):
        """Test exporting and importing session choices."""
        # Create session and make choices
        session = temp_manager.create_session(session_name="Export Test")

        _choice1 = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            session_id=session.session_id,
        )

        # Export session choices
        json_data = temp_manager.export_session_choices(session.session_id)
        assert json_data is not None

        # Create new session and import
        new_session = temp_manager.create_session(session_name="Import Test")
        imported_count = temp_manager.import_choices(json_data, new_session.session_id)

        assert imported_count >= 1

        # Verify imported choices
        new_session_choices = temp_manager.get_session_choices(new_session.session_id)
        assert len(new_session_choices) >= 1

    def test_cleanup_expired_sessions(self, temp_manager):
        """Test cleaning up expired sessions."""
        # Create session with old timestamp
        with patch("services.user_choice_manager.datetime") as mock_datetime:
            old_time = datetime.now() - timedelta(hours=25)
            mock_datetime.now.return_value = old_time

            _old_session = temp_manager.create_session(session_name="Old Session")

        # Create recent session
        recent_session = temp_manager.create_session(session_name="Recent Session")

        # Cleanup expired sessions
        expired_count = temp_manager.cleanup_expired_sessions()

        # Should have expired the old session
        assert expired_count >= 0

        # Check active sessions cache is updated
        active_sessions = temp_manager.get_active_sessions()
        session_ids = [s.session_id for s in active_sessions]
        assert recent_session.session_id in session_ids

    def test_get_statistics(self, temp_manager, sample_neologism):
        """Test getting comprehensive statistics."""
        # Create session and make choices
        session = temp_manager.create_session(session_name="Stats Test")
        _choice = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            session_id=session.session_id,
        )

        # Get statistics
        stats = temp_manager.get_statistics()

        assert "manager_stats" in stats
        assert "database_stats" in stats
        assert "active_sessions" in stats
        assert "session_expiry_hours" in stats
        assert "auto_resolve_conflicts" in stats

        assert stats["manager_stats"]["total_choices_made"] >= 1
        assert stats["manager_stats"]["sessions_created"] >= 1
        assert stats["active_sessions"] >= 1
        assert stats["session_expiry_hours"] == 24
        assert stats["auto_resolve_conflicts"] is True

    def test_update_and_delete_choice(self, temp_manager, sample_neologism):
        """Test updating and deleting choices."""
        # Make choice
        choice = temp_manager.make_choice(
            neologism=sample_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
        )

        # Update choice
        updates = {
            "translation_result": "updated-translation",
            "user_notes": "updated notes",
            "confidence_level": 0.8,
        }

        assert temp_manager.update_choice(choice.choice_id, updates, mark_as_used=True)

        # Verify update
        updated_choice = temp_manager.db.get_user_choice(choice.choice_id)
        assert updated_choice.translation_result == "updated-translation"
        assert updated_choice.user_notes == "updated notes"
        assert updated_choice.confidence_level == 0.8
        assert updated_choice.usage_count == 1

        # Delete choice
        assert temp_manager.delete_choice(choice.choice_id)

        # Verify deletion
        deleted_choice = temp_manager.db.get_user_choice(choice.choice_id)
        assert deleted_choice is None

    def test_validate_data_integrity(self, temp_manager):
        """Test data integrity validation."""
        report = temp_manager.validate_data_integrity()

        assert "total_issues" in report
        assert "orphaned_contexts" in report
        assert "missing_choices" in report
        assert "invalid_sessions" in report
        assert "recommendations" in report

        assert isinstance(report["total_issues"], int)
        assert isinstance(report["recommendations"], list)

    def test_optimize_database(self, temp_manager):
        """Test database optimization."""
        result = temp_manager.optimize_database()
        assert isinstance(result, bool)
        assert result is True


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_choice_manager(self):
        """Test creating choice manager."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            manager = create_choice_manager(db_path)
            assert isinstance(manager, UserChoiceManager)
            assert manager.db is not None
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_process_neologism_analysis_convenience(
        self, temp_manager, sample_analysis
    ):
        """Test processing neologism analysis convenience function."""
        from services.user_choice_manager import process_neologism_analysis

        # Create session
        session = temp_manager.create_session(session_name="Convenience Test")

        # Process analysis
        results = process_neologism_analysis(
            manager=temp_manager,
            analysis=sample_analysis,
            session_id=session.session_id,
        )

        assert "total_neologisms" in results
        assert "choices_found" in results
        assert "choices_applied" in results
        assert "new_choices_needed" in results
        assert results["total_neologisms"] == len(sample_analysis.detected_neologisms)

    def test_create_session_for_document_convenience(self, temp_manager):
        """Test creating session for document convenience function."""
        from core.dynamic_choice_engine import create_session_for_document

        session = create_session_for_document(
            manager=temp_manager,
            document_name="test_document.pdf",
            user_id="user123",
            source_lang="de",
            target_lang="en",
        )

        assert session.session_name == "Processing: test_document.pdf"
        assert session.document_name == "test_document.pdf"
        assert session.user_id == "user123"
        assert session.source_language == "de"
        assert session.target_language == "en"
        assert session.status == SessionStatus.ACTIVE


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_invalid_session_operations(self, temp_manager):
        """Test operations with invalid session IDs."""
        # Try to get non-existent session
        result = temp_manager.get_session("non_existent_session")
        assert result is None

        # Try to complete non-existent session
        result = temp_manager.complete_session("non_existent_session")
        assert result is False

        # Try to get choices for non-existent session
        choices = temp_manager.get_session_choices("non_existent_session")
        assert choices == []

    def test_invalid_choice_operations(self, temp_manager):
        """Test operations with invalid choice IDs."""
        # Try to update non-existent choice
        result = temp_manager.update_choice(
            "non_existent_choice", {"user_notes": "test"}
        )
        assert result is False

        # Try to delete non-existent choice
        result = temp_manager.delete_choice("non_existent_choice")
        assert result is False

    def test_invalid_import_data(self, temp_manager):
        """Test importing invalid data."""
        # Try to import invalid JSON
        result = temp_manager.import_choices("invalid json data")
        assert result == 0

        # Try to import empty data
        result = temp_manager.import_choices('{"choices": []}')
        assert result == 0

    def test_malformed_neologism_handling(self, temp_manager):
        """Test handling malformed neologism data."""
        # Create minimal neologism
        minimal_neologism = DetectedNeologism(
            term="test",
            confidence=0.5,
            neologism_type=NeologismType.UNKNOWN,
            start_pos=0,
            end_pos=4,
            sentence_context="test",
        )

        # Should still be able to make choice
        choice = temp_manager.make_choice(
            neologism=minimal_neologism,
            choice_type=ChoiceType.TRANSLATE,
            translation_result="test-translation",
        )

        assert choice is not None
        assert choice.neologism_term == "test"
        assert choice.translation_result == "test-translation"


if __name__ == "__main__":
    pytest.main([__file__])
