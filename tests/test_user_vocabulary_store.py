"""Unit tests for UserVocabularyStore (TASK-2.1, FR-06, NFR-03, NFR-09).

Verifies:
- Persistent SQLite storage per user on Modal Volume path
- Single preference save and retrieval
- Keep-untranslated flag handling
- Bulk save and atomic batch updates
- Delete and clear operations
- User isolation across independent SQLite files
- Persistence across instance re-initialization
- RFC 4180 TSV export format (de\\ten)
- Multi-threaded concurrent write and read safety
"""

from __future__ import annotations

import concurrent.futures
import tempfile
import time
from pathlib import Path

import pytest

from services.user_vocabulary_store import TermPreference, UserVocabularyStore


@pytest.fixture
def temp_store_dir() -> Path:
    """Provide a clean temporary directory for user vocabulary storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def store(temp_store_dir: Path) -> UserVocabularyStore:
    """Create a UserVocabularyStore using the temporary directory."""
    return UserVocabularyStore(storage_dir=temp_store_dir)


class TestTermPreferenceDataclass:
    """Test TermPreference data model behaviors."""

    def test_term_preference_defaults(self) -> None:
        pref = TermPreference(
            german_term="Dasein",
            preferred_translation="Being-there",
        )
        assert pref.german_term == "Dasein"
        assert pref.preferred_translation == "Being-there"
        assert pref.notes == ""
        assert pref.keep_untranslated is False
        assert pref.confidence == 1.0
        assert pref.created_at > 0
        assert pref.updated_at >= pref.created_at

    def test_to_dict_and_from_dict(self) -> None:
        pref = TermPreference(
            german_term="Schauung",
            preferred_translation="Intuitive Vision",
            notes="Klages chapter 3",
            keep_untranslated=False,
            confidence=0.95,
        )
        data = pref.to_dict()
        assert data["german_term"] == "Schauung"
        assert data["preferred_translation"] == "Intuitive Vision"
        assert data["notes"] == "Klages chapter 3"
        assert data["confidence"] == 0.95

        restored = TermPreference.from_dict(data)
        assert restored.german_term == pref.german_term
        assert restored.preferred_translation == pref.preferred_translation
        assert restored.notes == pref.notes
        assert restored.keep_untranslated == pref.keep_untranslated
        assert restored.confidence == pref.confidence


class TestUserVocabularyCRUD:
    """Test standard CRUD operations for user vocabulary."""

    def test_save_and_get_preference(self, store: UserVocabularyStore) -> None:
        pref = store.save_preference(
            user_id="user_123",
            german_term="Seele",
            preferred_translation="Soul",
            notes="Core Klagesian duality",
        )
        assert pref.german_term == "Seele"
        assert pref.preferred_translation == "Soul"

        retrieved = store.get_preference("user_123", "Seele")
        assert retrieved is not None
        assert retrieved.german_term == "Seele"
        assert retrieved.preferred_translation == "Soul"
        assert retrieved.notes == "Core Klagesian duality"

    def test_get_nonexistent_preference_returns_none(
        self, store: UserVocabularyStore
    ) -> None:
        assert store.get_preference("user_123", "NonExistentTerm") is None

    def test_update_existing_preference(self, store: UserVocabularyStore) -> None:
        store.save_preference(
            user_id="user_123",
            german_term="Geist",
            preferred_translation="Mind",
        )
        time.sleep(0.01)
        updated = store.save_preference(
            user_id="user_123",
            german_term="Geist",
            preferred_translation="Spirit",
            notes="Revised to align with Klages terminology",
        )
        assert updated.preferred_translation == "Spirit"
        assert updated.notes == "Revised to align with Klages terminology"
        assert updated.updated_at > updated.created_at

        # Verify all preferences retrieval reflects update
        prefs = store.get_user_preferences("user_123")
        assert len(prefs) == 1
        assert prefs["Geist"].preferred_translation == "Spirit"

    def test_keep_untranslated_preference(self, store: UserVocabularyStore) -> None:
        pref = store.save_preference(
            user_id="user_123",
            german_term="Dasein",
            preferred_translation="Dasein",
            keep_untranslated=True,
            notes="Leave untranslated in philosophical contexts",
        )
        assert pref.keep_untranslated is True
        retrieved = store.get_preference("user_123", "Dasein")
        assert retrieved is not None
        assert retrieved.keep_untranslated is True

    def test_delete_preference(self, store: UserVocabularyStore) -> None:
        store.save_preference("user_123", "Term1", "Trans1")
        assert store.delete_preference("user_123", "Term1") is True
        assert store.get_preference("user_123", "Term1") is None
        assert store.delete_preference("user_123", "Term1") is False

    def test_clear_user_preferences(self, store: UserVocabularyStore) -> None:
        store.save_preference("user_123", "TermA", "TransA")
        store.save_preference("user_123", "TermB", "TransB")
        assert len(store.get_user_preferences("user_123")) == 2

        store.clear_user_preferences("user_123")
        assert len(store.get_user_preferences("user_123")) == 0


class TestBulkSaveAndUserIsolation:
    """Test batch operations and user profile isolation."""

    def test_bulk_save_dict(self, store: UserVocabularyStore) -> None:
        items = {
            "Widersacher": "Adversary",
            "Lebenswirklichkeit": {
                "preferred_translation": "Life-reality",
                "notes": "Vitalist term",
                "keep_untranslated": False,
            },
            "Biozentrik": TermPreference(
                german_term="Biozentrik",
                preferred_translation="Biocentrism",
            ),
        }
        saved_count = store.bulk_save_preferences("user_123", items)
        assert saved_count == 3

        prefs = store.get_user_preferences("user_123")
        assert len(prefs) == 3
        assert prefs["Widersacher"].preferred_translation == "Adversary"
        assert prefs["Lebenswirklichkeit"].preferred_translation == "Life-reality"
        assert prefs["Lebenswirklichkeit"].notes == "Vitalist term"
        assert prefs["Biozentrik"].preferred_translation == "Biocentrism"

    def test_bulk_save_list(self, store: UserVocabularyStore) -> None:
        items = [
            TermPreference("Trieb", "Drive"),
            TermPreference("Rhythmus", "Rhythm"),
        ]
        saved_count = store.bulk_save_preferences("user_123", items)
        assert saved_count == 2
        prefs = store.get_user_preferences("user_123")
        assert "Trieb" in prefs
        assert "Rhythmus" in prefs

    def test_user_isolation(self, store: UserVocabularyStore) -> None:
        store.save_preference("user_A", "TermCommon", "TranslationA")
        store.save_preference("user_B", "TermCommon", "TranslationB")

        pref_a = store.get_preference("user_A", "TermCommon")
        pref_b = store.get_preference("user_B", "TermCommon")

        assert pref_a is not None and pref_a.preferred_translation == "TranslationA"
        assert pref_b is not None and pref_b.preferred_translation == "TranslationB"

        # Clearing user A does not affect user B
        store.clear_user_preferences("user_A")
        assert len(store.get_user_preferences("user_A")) == 0
        assert len(store.get_user_preferences("user_B")) == 1


class TestPersistenceAndTSVExport:
    """Test SQLite file persistence and RFC 4180 TSV export."""

    def test_persistence_across_instances(self, temp_store_dir: Path) -> None:
        store1 = UserVocabularyStore(storage_dir=temp_store_dir)
        store1.save_preference("user_42", "Schauung", "Intuitive Vision", notes="Saved in store1")

        # Create brand new store instance pointing to same storage_dir
        store2 = UserVocabularyStore(storage_dir=temp_store_dir)
        pref = store2.get_preference("user_42", "Schauung")
        assert pref is not None
        assert pref.preferred_translation == "Intuitive Vision"
        assert pref.notes == "Saved in store1"

    def test_export_tsv_empty(self, store: UserVocabularyStore) -> None:
        tsv_bytes = store.export_tsv("user_empty")
        tsv_text = tsv_bytes.decode("utf-8")
        assert tsv_text == "de\ten\n"

    def test_export_tsv_content_rfc4180(self, store: UserVocabularyStore) -> None:
        store.save_preference("user_1", "Geist", "Spirit")
        store.save_preference("user_1", "Seele", "Soul")
        store.save_preference("user_1", "Complex \"Quote\" Term", "Translation with\ttab and \"quotes\"")

        tsv_bytes = store.export_tsv("user_1")
        tsv_text = tsv_bytes.decode("utf-8")
        lines = tsv_text.splitlines()

        assert lines[0] == "de\ten"
        assert "Geist\tSpirit" in lines
        assert "Seele\tSoul" in lines
        assert any('"Complex ""Quote"" Term"\t"Translation with\ttab and ""quotes"""' in line for line in lines)


class TestValidationAndConcurrency:
    """Test input validations and multi-threaded safety."""

    def test_invalid_user_id_or_term_raises(self, store: UserVocabularyStore) -> None:
        with pytest.raises(ValueError, match="user_id cannot be empty"):
            store.save_preference("", "term", "trans")

        with pytest.raises(ValueError, match="german_term cannot be empty"):
            store.save_preference("user_1", "   ", "trans")

    def test_concurrent_writes_thread_safety(self, store: UserVocabularyStore) -> None:
        """Simulate concurrent threads writing preferences simultaneously to the same user."""
        user_id = "concurrent_user"
        term_count = 50

        def worker(idx: int) -> None:
            store.save_preference(
                user_id=user_id,
                german_term=f"Term_{idx:03d}",
                preferred_translation=f"Translation_{idx:03d}",
                notes=f"Note from thread {idx}",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(term_count)]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        prefs = store.get_user_preferences(user_id)
        assert len(prefs) == term_count
        for i in range(term_count):
            term_key = f"Term_{i:03d}"
            assert term_key in prefs
            assert prefs[term_key].preferred_translation == f"Translation_{i:03d}"
