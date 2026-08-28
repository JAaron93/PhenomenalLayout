"""services/glossary_compiler.py
================================
Track 2 — Dual-Tier Glossary Sync & Persistent User Vocabulary Store
Traceability: FR-02, NFR-04

Provides :class:`GlossaryCompiler`, compiling philosophical foundation dictionaries,
user persistent terminology, and book session overrides into RFC 4180 TSV bytes.

Design invariants:
- **Strict Precedence Hierarchy** — Book Session Overrides > User Persistent Vocabulary > Base Dictionary.
- **RFC 4180 TSV Formatting** — Header `de\\ten`, tab-separated, quotes escaped (`""`), newline-terminated.
- **Keep-Untranslated Directive** — Translates `term -> term` to instruct Google Cloud Translation to retain original German.
- **Unicode UTF-8 Preservation** — Full preservation of German umlauts, ligatures, and scholarly characters.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.settings import gcp_settings
from services.user_vocabulary_store import TermPreference, UserVocabularyStore

logger = logging.getLogger(__name__)


def _escape_rfc4180_field(val: str) -> str:
    """Format string for RFC 4180 TSV output with double-quote escaping when needed."""
    from utils.tsv_utils import escape_rfc4180_field
    return escape_rfc4180_field(val)


class GlossaryCompiler:
    """Combines base dictionaries, user vocabularies, and session overrides into RFC 4180 TSVs."""

    def __init__(
        self,
        base_dictionary_path: Path | str | None = None,
        vocab_store: UserVocabularyStore | None = None,
    ) -> None:
        """Initialize GlossaryCompiler.

        Parameters
        ----------
        base_dictionary_path:
            Path to static base terminology JSON (defaults to gcp_settings.base_dictionary_path).
        vocab_store:
            UserVocabularyStore instance for loading persistent user vocabulary.
        """
        if base_dictionary_path is not None:
            self.base_dictionary_path = Path(base_dictionary_path)
        else:
            self.base_dictionary_path = Path(gcp_settings.base_dictionary_path)

        self.vocab_store = vocab_store or UserVocabularyStore()

    def load_base_dictionary(self) -> dict[str, str]:
        """Load static foundation dictionary from disk."""
        if not self.base_dictionary_path.exists():
            logger.warning(
                "Base dictionary path not found: %s. Returning empty dictionary.",
                self.base_dictionary_path,
            )
            return {}

        try:
            content = self.base_dictionary_path.read_text(encoding="utf-8")
            raw_data = json.loads(content)
            if isinstance(raw_data, dict):
                return {str(k).strip(): str(v).strip() for k, v in raw_data.items() if str(k).strip()}
            return {}
        except Exception:
            logger.exception("Failed to load base dictionary from %s", self.base_dictionary_path)
            return {}

    @staticmethod
    def format_rfc4180_tsv(entries: dict[str, str]) -> bytes:
        """Format term mappings into RFC 4180 compliant TSV bytes with header `de\\ten`."""
        from utils.tsv_utils import format_tsv_bytes
        return format_tsv_bytes(entries, header=("de", "en"))

    def compile_entries(
        self,
        session_overrides: dict[str, Any] | None = None,
        user_id: str | None = None,
        include_base: bool = True,
        include_user_vocab: bool = True,
    ) -> dict[str, str]:
        """Compile merged terminology mapping applying the strict 3-tier precedence hierarchy.

        Precedence order (highest to lowest):
        1. Current Book Session Overrides
        2. Persistent User Vocabulary Store
        3. Regional Base Dictionary
        """
        result: dict[str, str] = {}

        # Tier 1: Base foundation dictionary
        if include_base:
            base_dict = self.load_base_dictionary()
            result.update(base_dict)

        # Tier 2: Persistent user vocabulary
        if include_user_vocab and user_id:
            user_prefs = self.vocab_store.get_user_preferences(user_id)
            for term, pref in user_prefs.items():
                if pref.keep_untranslated:
                    result[term] = term
                else:
                    result[term] = pref.preferred_translation

        # Tier 3: Current Book Session Overrides
        if session_overrides:
            for raw_term, val in session_overrides.items():
                term = str(raw_term).strip()
                if not term:
                    continue

                if isinstance(val, TermPreference):
                    result[term] = term if val.keep_untranslated else val.preferred_translation
                elif isinstance(val, dict):
                    keep_untrans = bool(val.get("keep_untranslated", False))
                    trans = str(val.get("preferred_translation", term if keep_untrans else "")).strip()
                    result[term] = term if keep_untrans else trans
                else:
                    result[term] = str(val).strip()

        return result

    def compile_tsv(
        self,
        session_overrides: dict[str, Any] | None = None,
        user_id: str | None = None,
        include_base: bool = True,
        include_user_vocab: bool = True,
    ) -> bytes:
        """Compile entries and format into RFC 4180 TSV bytes."""
        entries = self.compile_entries(
            session_overrides=session_overrides,
            user_id=user_id,
            include_base=include_base,
            include_user_vocab=include_user_vocab,
        )
        return self.format_rfc4180_tsv(entries)


def compile_glossary_tsv(
    session_overrides: dict[str, Any] | None = None,
    user_id: str | None = None,
    base_dictionary_path: Path | str | None = None,
    vocab_store: UserVocabularyStore | None = None,
    include_base: bool = True,
    include_user_vocab: bool = True,
) -> bytes:
    """Convenience function to compile terminology mappings into RFC 4180 TSV bytes."""
    compiler = GlossaryCompiler(
        base_dictionary_path=base_dictionary_path,
        vocab_store=vocab_store,
    )
    return compiler.compile_tsv(
        session_overrides=session_overrides,
        user_id=user_id,
        include_base=include_base,
        include_user_vocab=include_user_vocab,
    )
