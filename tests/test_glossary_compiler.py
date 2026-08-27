"""Unit tests for GlossaryCompiler (TASK-2.2, FR-02, NFR-04).

Verifies:
- Loading of base philosophical terms (config/klages_terminology.json)
- RFC 4180 compliant TSV generation with de\\ten header
- Strict priority hierarchy: Book Override > User Vocabulary > Base Dictionary
- Correct escaping of quotes, tabs, and newlines per RFC 4180
- Handling of keep-untranslated directives (term -> term)
- Unicode UTF-8 fidelity for German umlauts and philosophical characters
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from services.glossary_compiler import GlossaryCompiler, compile_glossary_tsv
from services.user_vocabulary_store import TermPreference, UserVocabularyStore


@pytest.fixture
def temp_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def custom_base_dict(temp_dir: Path) -> Path:
    dict_file = temp_dir / "test_base.json"
    data = {
        "Geist": "Spirit",
        "Seele": "Soul",
        "Widersacher": "Adversary",
        "Dasein": "Being-there",
    }
    dict_file.write_text(json.dumps(data), encoding="utf-8")
    return dict_file


@pytest.fixture
def user_store(temp_dir: Path) -> UserVocabularyStore:
    return UserVocabularyStore(storage_dir=temp_dir / "vocab")


class TestGlossaryCompilerBaseLoading:
    """Test loading of foundation dictionaries."""

    def test_load_default_klages_dictionary(self) -> None:
        compiler = GlossaryCompiler()
        base = compiler.load_base_dictionary()
        assert "Geist" in base
        assert base["Geist"] == "Spirit"
        assert "Seele" in base
        assert base["Seele"] == "Soul"
        assert len(base) >= 40

    def test_load_custom_dictionary(self, custom_base_dict: Path) -> None:
        compiler = GlossaryCompiler(base_dictionary_path=custom_base_dict)
        base = compiler.load_base_dictionary()
        assert len(base) == 4
        assert base["Widersacher"] == "Adversary"

    def test_load_nonexistent_dictionary_returns_empty(self, temp_dir: Path) -> None:
        compiler = GlossaryCompiler(base_dictionary_path=temp_dir / "nonexistent.json")
        base = compiler.load_base_dictionary()
        assert base == {}


class TestRFC4180TSVFormatting:
    """Test strict RFC 4180 TSV compliance."""

    def test_format_rfc4180_tsv_header_and_sorting(self) -> None:
        compiler = GlossaryCompiler()
        entries = {
            "Seele": "Soul",
            "Ausdruck": "Expression",
            "Geist": "Spirit",
        }
        tsv_bytes = compiler.format_rfc4180_tsv(entries)
        tsv_text = tsv_bytes.decode("utf-8")
        lines = tsv_text.splitlines()

        assert lines[0] == "de\ten"
        # Alphabetical sorting
        assert lines[1] == "Ausdruck\tExpression"
        assert lines[2] == "Geist\tSpirit"
        assert lines[3] == "Seele\tSoul"

    def test_format_rfc4180_tsv_escaping_quotes_and_delimiters(self) -> None:
        compiler = GlossaryCompiler()
        entries = {
            'Term "with" quotes': 'Translation "quoted"',
            "Term\twith\ttab": "Trans with\ttab",
            "Term\nwith\nnewline": "Trans\nnewline",
        }
        tsv_bytes = compiler.format_rfc4180_tsv(entries)
        tsv_text = tsv_bytes.decode("utf-8")

        assert 'de\ten' in tsv_text
        assert '"Term ""with"" quotes"\t"Translation ""quoted"""' in tsv_text
        assert '"Term\twith\ttab"\t"Trans with\ttab"' in tsv_text
        assert '"Term\nwith\nnewline"\t"Trans\nnewline"' in tsv_text

    def test_unicode_preservation(self) -> None:
        compiler = GlossaryCompiler()
        entries = {
            "Bewußtsein": "Consciousness",
            "Spontaneität": "Spontaneity",
            "Schauung": "Vision/Intuition",
            "Urſprung": "Origin",
        }
        tsv_bytes = compiler.format_rfc4180_tsv(entries)
        decoded = tsv_bytes.decode("utf-8")
        assert "Bewußtsein\tConsciousness" in decoded
        assert "Spontaneität\tSpontaneity" in decoded
        assert "Urſprung\tOrigin" in decoded


class TestPrecedenceHierarchy:
    """Test 3-tier hierarchy: Book Overrides > User Vocab > Base Dictionary."""

    def test_full_precedence_resolution(
        self, custom_base_dict: Path, user_store: UserVocabularyStore
    ) -> None:
        # Base dictionary has: Geist=Spirit, Seele=Soul, Widersacher=Adversary, Dasein=Being-there
        user_id = "scholar_1"
        user_store.save_preference(user_id, "Geist", "Mind", notes="User preference")
        user_store.save_preference(user_id, "Seele", "Psyche", notes="User preference")
        user_store.save_preference(user_id, "Schauung", "Intuitive Vision")

        # Book session overrides
        book_overrides = {
            "Geist": "Intellect/Spirit",  # Overrides both User and Base
            "Biozentrik": "Biocentrism",  # New book-specific coined term
        }

        compiler = GlossaryCompiler(
            base_dictionary_path=custom_base_dict,
            vocab_store=user_store,
        )
        compiled = compiler.compile_entries(
            session_overrides=book_overrides,
            user_id=user_id,
        )

        # 1. Book override takes precedence over User and Base
        assert compiled["Geist"] == "Intellect/Spirit"
        # 2. Book override introduces new terms
        assert compiled["Biozentrik"] == "Biocentrism"
        # 3. User vocab takes precedence over Base where no book override exists
        assert compiled["Seele"] == "Psyche"
        # 4. User vocab introduces user-specific persistent terms
        assert compiled["Schauung"] == "Intuitive Vision"
        # 5. Base terms remain for untouched keys
        assert compiled["Widersacher"] == "Adversary"
        assert compiled["Dasein"] == "Being-there"

    def test_keep_untranslated_directive_in_compilation(
        self, custom_base_dict: Path, user_store: UserVocabularyStore
    ) -> None:
        user_id = "scholar_2"
        # User marks Dasein as keep_untranslated
        user_store.save_preference(
            user_id,
            "Dasein",
            "Dasein",
            keep_untranslated=True,
        )

        compiler = GlossaryCompiler(
            base_dictionary_path=custom_base_dict,
            vocab_store=user_store,
        )
        compiled = compiler.compile_entries(user_id=user_id)
        # Should map to original German term so Cloud Translation preserves it
        assert compiled["Dasein"] == "Dasein"

    def test_book_override_with_term_preference_object(
        self, custom_base_dict: Path, user_store: UserVocabularyStore
    ) -> None:
        compiler = GlossaryCompiler(base_dictionary_path=custom_base_dict, vocab_store=user_store)
        overrides = {
            "Widersacher": TermPreference(
                german_term="Widersacher",
                preferred_translation="Antagonist",
                notes="Book specific translation",
            )
        }
        compiled = compiler.compile_entries(session_overrides=overrides)
        assert compiled["Widersacher"] == "Antagonist"

    def test_convenience_compile_glossary_tsv(
        self, custom_base_dict: Path, user_store: UserVocabularyStore
    ) -> None:
        user_id = "scholar_3"
        user_store.save_preference(user_id, "Symbol", "Emblem")

        tsv_bytes = compile_glossary_tsv(
            session_overrides={"Symbol": "Token"},
            user_id=user_id,
            base_dictionary_path=custom_base_dict,
            vocab_store=user_store,
        )
        tsv_text = tsv_bytes.decode("utf-8")
        assert "de\ten" in tsv_text
        assert "Symbol\tToken" in tsv_text
        assert "Geist\tSpirit" in tsv_text


class TestEdgeCasesAndErrorHandling:
    """Test error conditions, malformed files, and blank keys."""

    def test_load_malformed_json_returns_empty(self, temp_dir: Path) -> None:
        bad_json = temp_dir / "bad.json"
        bad_json.write_text("not json at all {", encoding="utf-8")
        compiler = GlossaryCompiler(base_dictionary_path=bad_json)
        assert compiler.load_base_dictionary() == {}

    def test_load_non_dict_json_returns_empty(self, temp_dir: Path) -> None:
        list_json = temp_dir / "list.json"
        list_json.write_text('["item1", "item2"]', encoding="utf-8")
        compiler = GlossaryCompiler(base_dictionary_path=list_json)
        assert compiler.load_base_dictionary() == {}

    def test_session_overrides_with_dict_and_empty_terms(self) -> None:
        compiler = GlossaryCompiler()
        overrides = {
            "": "Should be skipped",
            "   ": "Also skipped",
            "TermUntrans": {
                "keep_untranslated": True,
            },
            "TermNormal": {
                "preferred_translation": "Normal Translation",
            },
        }
        res = compiler.compile_entries(session_overrides=overrides, include_base=False)
        assert "" not in res
        assert "TermUntrans" in res
        assert res["TermUntrans"] == "TermUntrans"
        assert res["TermNormal"] == "Normal Translation"
