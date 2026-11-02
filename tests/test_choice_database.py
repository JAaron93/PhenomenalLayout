"""Tests for choice database functionality."""

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from database.choice_database import ChoiceDatabase
from models.user_choice_models import (
    ChoiceConflict,
    ChoiceScope,
    ChoiceSession,
    ChoiceType,
    ConflictResolution,
    SessionStatus,
    TranslationContext,
    UserChoice,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    yield ChoiceDatabase(db_path)

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def sample_context():
    """Create a sample translation context."""
    return TranslationContext(
        sentence_context="This is a test sentence with philosophical terms.",
        semantic_field="existentialism",
        philosophical_domain="philosophy_of_mind",
        author="Heidegger",
        source_language="de",
        target_language="en",
        surrounding_terms=["sein", "dasein", "existence"],
        related_concepts=["being", "time", "anxiety"],
    )


@pytest.fixture
def sample_choice(sample_context):
    """Create a sample user choice."""
    return UserChoice(
        choice_id="test_choice_1",
        neologism_term="Dasein",
        choice_type=ChoiceType.TRANSLATE,
        translation_result="being-there",
        context=sample_context,
        choice_scope=ChoiceScope.CONTEXTUAL,
        confidence_level=0.9,
        user_notes="Heidegger's fundamental concept",
    )


@pytest.fixture
def sample_session():
    """Create a sample choice session."""
    return ChoiceSession(
        session_id="test_session_1",
        session_name="Test Session",
        document_name="test_document.pdf",
        user_id="user123",
        source_language="de",
        target_language="en",
        status=SessionStatus.ACTIVE,
    )


class TestChoiceDatabase:
    """Test ChoiceDatabase functionality."""

    def test_database_initialization(self, temp_db):
        """Test database initialization."""
        # Database should be created and initialized
        assert temp_db.db_path.exists()

        # Test that tables are created
        with temp_db._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """
            )
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                "user_choices",
                "choice_sessions",
                "choice_conflicts",
                "choice_contexts",
                "translation_preferences",
                "database_metadata",
            ]

            for table in expected_tables:
                assert table in tables

    def test_save_and_get_user_choice(self, temp_db, sample_choice):
        """Test saving and retrieving user choices."""
        # Save choice
        assert temp_db.save_user_choice(sample_choice)

        # Retrieve choice
        retrieved_choice = temp_db.get_user_choice(sample_choice.choice_id)

        assert retrieved_choice is not None
        assert retrieved_choice.choice_id == sample_choice.choice_id
        assert retrieved_choice.neologism_term == sample_choice.neologism_term
        assert retrieved_choice.choice_type == sample_choice.choice_type
        assert retrieved_choice.translation_result == sample_choice.translation_result
        assert retrieved_choice.confidence_level == sample_choice.confidence_level
        assert retrieved_choice.user_notes == sample_choice.user_notes

        # Test context preservation
        assert (
            retrieved_choice.context.semantic_field
            == sample_choice.context.semantic_field
        )
        assert (
            retrieved_choice.context.philosophical_domain
            == sample_choice.context.philosophical_domain
        )
        assert retrieved_choice.context.author == sample_choice.context.author

    def test_get_nonexistent_choice(self, temp_db):
        """Test retrieving non-existent choice."""
        result = temp_db.get_user_choice("nonexistent_id")
        assert result is None

    def test_get_choices_by_term(self, temp_db, sample_context):
        """Test getting choices by neologism term."""
        # Create multiple choices for same term
        choice1 = UserChoice(
            choice_id="choice1",
            neologism_term="Dasein",
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            context=sample_context,
        )

        choice2 = UserChoice(
            choice_id="choice2",
            neologism_term="Dasein",
            choice_type=ChoiceType.PRESERVE,
            translation_result="",
            context=sample_context,
        )

        choice3 = UserChoice(
            choice_id="choice3",
            neologism_term="Sein",
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being",
            context=sample_context,
        )

        # Save choices
        assert temp_db.save_user_choice(choice1)
        assert temp_db.save_user_choice(choice2)
        assert temp_db.save_user_choice(choice3)

        # Get choices by term
        dasein_choices = temp_db.get_choices_by_term("Dasein")
        assert len(dasein_choices) == 2

        sein_choices = temp_db.get_choices_by_term("Sein")
        assert len(sein_choices) == 1

        nonexistent_choices = temp_db.get_choices_by_term("NonExistent")
        assert len(nonexistent_choices) == 0

    def test_update_choice_usage(self, temp_db, sample_choice):
        """Test updating choice usage statistics."""
        # Save choice
        assert temp_db.save_user_choice(sample_choice)

        # Update usage with success
        assert temp_db.update_choice_usage(sample_choice.choice_id, success=True)

        # Retrieve and check
        updated_choice = temp_db.get_user_choice(sample_choice.choice_id)
        assert updated_choice.usage_count == 1
        assert updated_choice.last_used_at is not None
        assert updated_choice.success_rate >= sample_choice.success_rate

        # Update usage with failure
        assert temp_db.update_choice_usage(sample_choice.choice_id, success=False)

        # Retrieve and check
        updated_choice = temp_db.get_user_choice(sample_choice.choice_id)
        assert updated_choice.usage_count == 2
        assert updated_choice.success_rate < sample_choice.success_rate

    def test_delete_user_choice(self, temp_db, sample_choice):
        """Test deleting user choice."""
        # Save choice
        assert temp_db.save_user_choice(sample_choice)

        # Verify it exists
        assert temp_db.get_user_choice(sample_choice.choice_id) is not None

        # Delete choice
        assert temp_db.delete_user_choice(sample_choice.choice_id)

        # Verify it's gone
        assert temp_db.get_user_choice(sample_choice.choice_id) is None

    def test_save_and_get_session(self, temp_db, sample_session):
        """Test saving and retrieving sessions."""
        # Save session
        assert temp_db.save_session(sample_session)

        # Retrieve session
        retrieved_session = temp_db.get_session(sample_session.session_id)

        assert retrieved_session is not None
        assert retrieved_session.session_id == sample_session.session_id
        assert retrieved_session.session_name == sample_session.session_name
        assert retrieved_session.document_name == sample_session.document_name
        assert retrieved_session.user_id == sample_session.user_id
        assert retrieved_session.source_language == sample_session.source_language
        assert retrieved_session.target_language == sample_session.target_language
        assert retrieved_session.status == sample_session.status

    def test_get_choices_by_session(self, temp_db, sample_context):
        """Test getting choices by session."""
        session_id = "test_session_123"

        # Create sessions first (required for foreign key constraints)
        session1 = ChoiceSession(
            session_id=session_id,
            session_name="Test Session 1",
            status=SessionStatus.ACTIVE,
            user_id="test_user",
            source_language="de",
            target_language="en",
        )
        session2 = ChoiceSession(
            session_id="different_session",
            session_name="Test Session 2",
            status=SessionStatus.ACTIVE,
            user_id="test_user",
            source_language="de",
            target_language="en",
        )

        assert temp_db.save_session(session1)
        assert temp_db.save_session(session2)

        # Create choices for session
        choice1 = UserChoice(
            choice_id="choice1",
            neologism_term="term1",
            choice_type=ChoiceType.TRANSLATE,
            context=sample_context,
            session_id=session_id,
        )

        choice2 = UserChoice(
            choice_id="choice2",
            neologism_term="term2",
            choice_type=ChoiceType.PRESERVE,
            context=sample_context,
            session_id=session_id,
        )

        choice3 = UserChoice(
            choice_id="choice3",
            neologism_term="term3",
            choice_type=ChoiceType.TRANSLATE,
            context=sample_context,
            session_id="different_session",
        )

        # Save choices
        assert temp_db.save_user_choice(choice1)
        assert temp_db.save_user_choice(choice2)
        assert temp_db.save_user_choice(choice3)

        # Get choices by session
        session_choices = temp_db.get_choices_by_session(session_id)
        assert len(session_choices) == 2

        choice_ids = [c.choice_id for c in session_choices]
        assert "choice1" in choice_ids
        assert "choice2" in choice_ids
        assert "choice3" not in choice_ids

    def test_get_active_sessions(self, temp_db):
        """Test getting active sessions."""
        # Create sessions with different statuses
        session1 = ChoiceSession(
            session_id="session1",
            session_name="Active Session 1",
            status=SessionStatus.ACTIVE,
        )

        session2 = ChoiceSession(
            session_id="session2",
            session_name="Active Session 2",
            status=SessionStatus.ACTIVE,
        )

        session3 = ChoiceSession(
            session_id="session3",
            session_name="Completed Session",
            status=SessionStatus.COMPLETED,
        )

        # Save sessions
        assert temp_db.save_session(session1)
        assert temp_db.save_session(session2)
        assert temp_db.save_session(session3)

        # Get active sessions
        active_sessions = temp_db.get_active_sessions()
        assert len(active_sessions) == 2

        session_ids = [s.session_id for s in active_sessions]
        assert "session1" in session_ids
        assert "session2" in session_ids
        assert "session3" not in session_ids

    def test_complete_session(self, temp_db, sample_session):
        """Test completing a session."""
        # Save session
        assert temp_db.save_session(sample_session)

        # Complete session
        assert temp_db.complete_session(sample_session.session_id)

        # Verify completion
        completed_session = temp_db.get_session(sample_session.session_id)
        assert completed_session.status == SessionStatus.COMPLETED
        assert completed_session.completed_at is not None

    def test_search_similar_choices(self, temp_db):
        """Test searching for similar choices."""
        # Create choices with different contexts
        context1 = TranslationContext(
            semantic_field="existentialism",
            philosophical_domain="philosophy_of_mind",
            author="Heidegger",
            source_language="de",
            target_language="en",
        )

        context2 = TranslationContext(
            semantic_field="existentialism",
            philosophical_domain="philosophy_of_mind",
            author="Sartre",
            source_language="fr",
            target_language="en",
        )

        context3 = TranslationContext(
            semantic_field="ethics",
            philosophical_domain="moral_philosophy",
            author="Kant",
            source_language="de",
            target_language="en",
        )

        choice1 = UserChoice(
            choice_id="choice1",
            neologism_term="term1",
            choice_type=ChoiceType.TRANSLATE,
            context=context1,
        )

        choice2 = UserChoice(
            choice_id="choice2",
            neologism_term="term2",
            choice_type=ChoiceType.TRANSLATE,
            context=context2,
        )

        choice3 = UserChoice(
            choice_id="choice3",
            neologism_term="term3",
            choice_type=ChoiceType.TRANSLATE,
            context=context3,
        )

        # Save choices
        assert temp_db.save_user_choice(choice1)
        assert temp_db.save_user_choice(choice2)
        assert temp_db.save_user_choice(choice3)

        # Search for similar choices
        search_context = TranslationContext(
            semantic_field="existentialism",
            philosophical_domain="philosophy_of_mind",
            author="Heidegger",
            source_language="de",
            target_language="en",
        )

        similar_choices = temp_db.search_similar_choices(search_context)

        # Should find choices with similar context attributes
        assert len(similar_choices) >= 1
        choice_ids = [c.choice_id for c in similar_choices]
        assert "choice1" in choice_ids  # Exact match

    def test_save_and_get_conflict(self, temp_db, sample_context):
        """Test saving and retrieving conflicts."""
        # Create conflicting choices
        choice_a = UserChoice(
            choice_id="choice_a",
            neologism_term="Dasein",
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            context=sample_context,
        )

        choice_b = UserChoice(
            choice_id="choice_b",
            neologism_term="Dasein",
            choice_type=ChoiceType.PRESERVE,
            translation_result="",
            context=sample_context,
        )

        # Save choices first
        assert temp_db.save_user_choice(choice_a)
        assert temp_db.save_user_choice(choice_b)

        # Create conflict
        conflict = ChoiceConflict(
            conflict_id="conflict_1",
            neologism_term="Dasein",
            choice_a=choice_a,
            choice_b=choice_b,
        )

        # Save conflict
        assert temp_db.save_conflict(conflict)

        # Get unresolved conflicts
        unresolved = temp_db.get_unresolved_conflicts()
        assert len(unresolved) == 1
        assert unresolved[0].conflict_id == "conflict_1"
        assert unresolved[0].neologism_term == "Dasein"

    def test_resolve_conflict(self, temp_db, sample_context):
        """Test resolving conflicts."""
        # Create and save conflicting choices
        choice_a = UserChoice(
            choice_id="choice_a",
            neologism_term="Dasein",
            choice_type=ChoiceType.TRANSLATE,
            translation_result="being-there",
            context=sample_context,
        )

        choice_b = UserChoice(
            choice_id="choice_b",
            neologism_term="Dasein",
            choice_type=ChoiceType.PRESERVE,
            translation_result="",
            context=sample_context,
        )

        assert temp_db.save_user_choice(choice_a)
        assert temp_db.save_user_choice(choice_b)

        # Create and save conflict
        conflict = ChoiceConflict(
            conflict_id="conflict_1",
            neologism_term="Dasein",
            choice_a=choice_a,
            choice_b=choice_b,
        )

        assert temp_db.save_conflict(conflict)

        # Resolve conflict
        assert temp_db.resolve_conflict(
            "conflict_1",
            ConflictResolution.LATEST_WINS,
            "choice_a",
            "Resolved manually",
        )

        # Check that conflict is resolved
        unresolved = temp_db.get_unresolved_conflicts()
        assert len(unresolved) == 0

    def test_cleanup_expired_sessions(self, temp_db):
        """Test cleanup of expired sessions."""
        # Create old session
        old_time = datetime.now(UTC) - timedelta(hours=25)
        old_session = ChoiceSession(
            session_id="old_session",
            session_name="Old Session",
            status=SessionStatus.ACTIVE,
            created_at=old_time.isoformat(),
        )

        # Create recent session
        recent_session = ChoiceSession(
            session_id="recent_session",
            session_name="Recent Session",
            status=SessionStatus.ACTIVE,
        )

        # Save sessions
        assert temp_db.save_session(old_session)
        assert temp_db.save_session(recent_session)

        # Cleanup expired sessions (24 hour expiry)
        expired_count = temp_db.cleanup_expired_sessions(24)
        assert expired_count == 1

        # Check that old session is marked as expired
        old_session_updated = temp_db.get_session("old_session")
        assert old_session_updated.status == SessionStatus.EXPIRED

        # Check that recent session is still active
        recent_session_updated = temp_db.get_session("recent_session")
        assert recent_session_updated.status == SessionStatus.ACTIVE

    def test_get_database_statistics(self, temp_db, sample_choice, sample_session):
        """Test getting database statistics."""
        # Add some data
        assert temp_db.save_user_choice(sample_choice)
        assert temp_db.save_session(sample_session)

        # Get statistics
        stats = temp_db.get_database_statistics()

        assert "total_choices" in stats
        assert "total_sessions" in stats
        assert "active_sessions" in stats
        assert "total_conflicts" in stats
        assert "unresolved_conflicts" in stats
        assert "choice_type_distribution" in stats
        assert "db_size_bytes" in stats

        assert stats["total_choices"] >= 1
        assert stats["total_sessions"] >= 1
        assert stats["active_sessions"] >= 1
        assert stats["db_size_bytes"] > 0

    def test_export_choices_to_json(self, temp_db, sample_choice):
        """Test exporting choices to JSON."""
        # Save choice
        assert temp_db.save_user_choice(sample_choice)

        # Export all choices
        json_data = temp_db.export_choices_to_json()
        assert json_data is not None

        # Parse and verify
        export_data = json.loads(json_data)
        assert "export_timestamp" in export_data
        assert "total_choices" in export_data
        assert "choices" in export_data
        assert export_data["total_choices"] == 1
        assert len(export_data["choices"]) == 1

        choice_data = export_data["choices"][0]
        assert choice_data["choice_id"] == sample_choice.choice_id
        assert choice_data["neologism_term"] == sample_choice.neologism_term

    def test_import_choices_from_json(self, temp_db, sample_choice):
        """Test importing choices from JSON."""
        # Create export data
        export_data = {
            "export_timestamp": datetime.now(UTC).isoformat(),
            "total_choices": 1,
            "choices": [sample_choice.to_dict()],
        }

        json_data = json.dumps(export_data)

        # Import choices
        imported_count = temp_db.import_choices_from_json(json_data)
        assert imported_count == 1

        # Verify imported choice
        imported_choice = temp_db.get_user_choice(sample_choice.choice_id)
        assert imported_choice is not None
        assert imported_choice.neologism_term == sample_choice.neologism_term
        assert imported_choice.choice_type == sample_choice.choice_type

    def test_export_import_roundtrip(self, temp_db, sample_choice):
        """Test export-import roundtrip."""
        # Save original choice
        assert temp_db.save_user_choice(sample_choice)

        # Export
        json_data = temp_db.export_choices_to_json()
        assert json_data is not None

        # Delete choice
        assert temp_db.delete_user_choice(sample_choice.choice_id)
        assert temp_db.get_user_choice(sample_choice.choice_id) is None

        # Import
        imported_count = temp_db.import_choices_from_json(json_data)
        assert imported_count == 1

        # Verify restored choice
        restored_choice = temp_db.get_user_choice(sample_choice.choice_id)
        assert restored_choice is not None
        assert restored_choice.neologism_term == sample_choice.neologism_term
        assert restored_choice.choice_type == sample_choice.choice_type
        assert restored_choice.translation_result == sample_choice.translation_result

    def test_delete_session_cascade(self, temp_db, sample_context):
        """Test cascading deletion of session and related data."""
        session_id = "test_session_cascade"

        # Create session
        session = ChoiceSession(session_id=session_id, session_name="Test Session")

        # Create choice for session
        choice = UserChoice(
            choice_id="choice_for_session",
            neologism_term="test_term",
            choice_type=ChoiceType.TRANSLATE,
            context=sample_context,
            session_id=session_id,
        )

        # Save session and choice
        assert temp_db.save_session(session)
        assert temp_db.save_user_choice(choice)

        # Verify they exist
        assert temp_db.get_session(session_id) is not None
        assert temp_db.get_user_choice("choice_for_session") is not None

        # Delete session
        assert temp_db.delete_session(session_id)

        # Verify cascade deletion
        assert temp_db.get_session(session_id) is None
        assert temp_db.get_user_choice("choice_for_session") is None

    def test_database_error_handling(self, temp_db):
        """Test database error handling."""
        # Test with invalid choice data
        with pytest.raises((AttributeError, TypeError)):
            temp_db.save_user_choice(None)

        # Test getting choice with invalid ID
        result = temp_db.get_user_choice("")
        assert result is None

        # Test updating non-existent choice
        result = temp_db.update_choice_usage("non_existent_id")
        assert result is False

        # Test completing non-existent session
        result = temp_db.complete_session("non_existent_session")
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__])
