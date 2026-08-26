"""services/user_vocabulary_store.py
====================================
Track 2 — Dual-Tier Glossary Sync & Persistent User Vocabulary Store
Traceability: FR-06, NFR-03, NFR-09

Provides :class:`UserVocabularyStore`, managing user-specific terminology dictionaries
stored persistently on the Modal Volume (e.g. `/data/user_vocabularies/{user_id}.sqlite`).

Design invariants:
- **Persistent storage on Modal Volume** — isolated SQLite database per user.
- **ACID atomicity and thread-safety** — WAL mode enabled, per-file locking, safe concurrent writes.
- **RFC 4180 TSV export** — exports personal dictionaries with strict escaping and `de\\ten` header.
- **Deterministic File Handle Cleanup** — all SQLite connections closed deterministically in try...finally.
- **Zero host PDF leakage** — only stores lightweight terminology strings (<= 5MB).
"""

from __future__ import annotations

import contextlib
import logging
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.settings import gcp_settings

logger = logging.getLogger(__name__)


@dataclass
class TermPreference:
    """Represents a translator's saved terminology decision for a philosophical term or neologism.

    Attributes
    ----------
    german_term:
        The source German term or coined compound (e.g. "Schauung", "Dasein").
    preferred_translation:
        The translator's selected English equivalent (e.g. "Intuitive Vision").
    notes:
        Optional contextual or scholarly notes explaining the translation rationale.
    keep_untranslated:
        When True, signifies that the term should remain in its original German form
        in the translated English manuscript.
    confidence:
        Confidence score between 0.0 and 1.0 associated with this preference.
    created_at:
        Unix timestamp when the preference was first recorded.
    updated_at:
        Unix timestamp when the preference was last updated.
    """

    german_term: str
    preferred_translation: str
    notes: str = ""
    keep_untranslated: bool = False
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize term preference to a dictionary."""
        return {
            "german_term": self.german_term,
            "preferred_translation": self.preferred_translation,
            "notes": self.notes,
            "keep_untranslated": self.keep_untranslated,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TermPreference:
        """Construct a TermPreference from a dictionary."""
        return cls(
            german_term=data["german_term"],
            preferred_translation=data["preferred_translation"],
            notes=data.get("notes", ""),
            keep_untranslated=bool(data.get("keep_untranslated", False)),
            confidence=float(data.get("confidence", 1.0)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


def _escape_rfc4180_field(field_value: str) -> str:
    """Format a string field for RFC 4180 TSV output.

    If the value contains a tab, newline, carriage return, or double quote,
    it must be enclosed in double quotes with existing quotes doubled.
    """
    if any(c in field_value for c in ('\t', '\n', '\r', '"')):
        escaped = field_value.replace('"', '""')
        return f'"{escaped}"'
    return field_value


class UserVocabularyStore:
    """Manages persistent user vocabulary dictionaries on the Modal Volume."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        """Initialize UserVocabularyStore.

        Parameters
        ----------
        storage_dir:
            Directory where per-user SQLite database files are stored.
            Defaults to `{gcp_settings.modal_volume_path}/user_vocabularies`.
        """
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir)
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        else:
            default_path = Path(gcp_settings.modal_volume_path) / "user_vocabularies"
            try:
                default_path.mkdir(parents=True, exist_ok=True)
                self.storage_dir = default_path
            except (OSError, PermissionError):
                fallback_path = Path("data/user_vocabularies")
                fallback_path.mkdir(parents=True, exist_ok=True)
                self.storage_dir = fallback_path

        self._lock = threading.RLock()
        logger.debug("UserVocabularyStore initialized at %s", self.storage_dir)

    def _get_db_path(self, user_id: str) -> Path:
        """Sanitize user_id and return path to its SQLite database."""
        clean_user_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id.strip())
        if not clean_user_id:
            raise ValueError("user_id cannot be empty")
        return self.storage_dir / f"{clean_user_id}.sqlite"

    @contextlib.contextmanager
    def _connection(self, db_path: Path) -> Iterator[sqlite3.Connection]:
        """Open a connection with deterministic cleanup, configure pragmas and schema."""
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_term_preferences (
                    german_term TEXT PRIMARY KEY,
                    preferred_translation TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    keep_untranslated INTEGER DEFAULT 0,
                    confidence REAL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_term ON user_term_preferences(german_term);"
            )
            yield conn
        finally:
            conn.close()

    def save_preference(
        self,
        user_id: str,
        german_term: str,
        preferred_translation: str,
        notes: str = "",
        keep_untranslated: bool = False,
        confidence: float = 1.0,
    ) -> TermPreference:
        """Save or update a single terminology preference for *user_id*."""
        if not user_id or not user_id.strip():
            raise ValueError("user_id cannot be empty")
        clean_term = german_term.strip()
        if not clean_term:
            raise ValueError("german_term cannot be empty")

        clean_translation = preferred_translation.strip()
        db_path = self._get_db_path(user_id)
        now = time.time()

        with self._lock, self._connection(db_path) as conn:
            cursor = conn.execute(
                "SELECT created_at FROM user_term_preferences WHERE german_term = ?",
                (clean_term,),
            )
            row = cursor.fetchone()
            created_at = row["created_at"] if row else now

            conn.execute(
                """
                INSERT INTO user_term_preferences (
                    german_term, preferred_translation, notes, keep_untranslated,
                    confidence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(german_term) DO UPDATE SET
                    preferred_translation = excluded.preferred_translation,
                    notes = excluded.notes,
                    keep_untranslated = excluded.keep_untranslated,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at;
                """,
                (
                    clean_term,
                    clean_translation,
                    notes,
                    1 if keep_untranslated else 0,
                    confidence,
                    created_at,
                    now,
                ),
            )
            conn.commit()

        return TermPreference(
            german_term=clean_term,
            preferred_translation=clean_translation,
            notes=notes,
            keep_untranslated=keep_untranslated,
            confidence=confidence,
            created_at=created_at,
            updated_at=now,
        )

    def get_preference(self, user_id: str, german_term: str) -> TermPreference | None:
        """Retrieve a specific term preference for *user_id*."""
        if not user_id or not user_id.strip() or not german_term or not german_term.strip():
            return None

        clean_term = german_term.strip()
        db_path = self._get_db_path(user_id)
        if not db_path.exists():
            return None

        with self._lock, self._connection(db_path) as conn:
            cursor = conn.execute(
                """
                SELECT german_term, preferred_translation, notes,
                       keep_untranslated, confidence, created_at, updated_at
                FROM user_term_preferences
                WHERE german_term = ?;
                """,
                (clean_term,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return TermPreference(
                german_term=row["german_term"],
                preferred_translation=row["preferred_translation"],
                notes=row["notes"] or "",
                keep_untranslated=bool(row["keep_untranslated"]),
                confidence=float(row["confidence"]),
                created_at=float(row["created_at"]),
                updated_at=float(row["updated_at"]),
            )

    def get_user_preferences(self, user_id: str) -> dict[str, TermPreference]:
        """Load all saved terminology preferences for *user_id*."""
        if not user_id or not user_id.strip():
            return {}

        db_path = self._get_db_path(user_id)
        if not db_path.exists():
            return {}

        with self._lock, self._connection(db_path) as conn:
            cursor = conn.execute(
                """
                SELECT german_term, preferred_translation, notes,
                       keep_untranslated, confidence, created_at, updated_at
                FROM user_term_preferences
                ORDER BY german_term ASC;
                """
            )
            rows = cursor.fetchall()
            results: dict[str, TermPreference] = {}
            for row in rows:
                pref = TermPreference(
                    german_term=row["german_term"],
                    preferred_translation=row["preferred_translation"],
                    notes=row["notes"] or "",
                    keep_untranslated=bool(row["keep_untranslated"]),
                    confidence=float(row["confidence"]),
                    created_at=float(row["created_at"]),
                    updated_at=float(row["updated_at"]),
                )
                results[pref.german_term] = pref
            return results

    def bulk_save_preferences(
        self,
        user_id: str,
        preferences: list[TermPreference] | dict[str, Any],
    ) -> int:
        """Batch insert or update preferences for *user_id* in a single transaction."""
        if not user_id or not user_id.strip():
            raise ValueError("user_id cannot be empty")

        records: list[TermPreference] = []
        if isinstance(preferences, dict):
            for term, val in preferences.items():
                if isinstance(val, TermPreference):
                    records.append(val)
                elif isinstance(val, dict):
                    data = dict(val)
                    data.setdefault("german_term", term)
                    records.append(TermPreference.from_dict(data))
                elif isinstance(val, str):
                    records.append(TermPreference(german_term=term, preferred_translation=val))
        elif isinstance(preferences, list):
            for item in preferences:
                if isinstance(item, TermPreference):
                    records.append(item)
                elif isinstance(item, dict):
                    records.append(TermPreference.from_dict(item))

        if not records:
            return 0

        now = time.time()
        db_path = self._get_db_path(user_id)

        with self._lock, self._connection(db_path) as conn:
            for pref in records:
                clean_term = pref.german_term.strip()
                if not clean_term:
                    continue
                clean_trans = pref.preferred_translation.strip()
                cursor = conn.execute(
                    "SELECT created_at FROM user_term_preferences WHERE german_term = ?",
                    (clean_term,),
                )
                row = cursor.fetchone()
                created_at = row["created_at"] if row else (pref.created_at or now)

                conn.execute(
                    """
                    INSERT INTO user_term_preferences (
                        german_term, preferred_translation, notes, keep_untranslated,
                        confidence, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(german_term) DO UPDATE SET
                        preferred_translation = excluded.preferred_translation,
                        notes = excluded.notes,
                        keep_untranslated = excluded.keep_untranslated,
                        confidence = excluded.confidence,
                        updated_at = excluded.updated_at;
                    """,
                    (
                        clean_term,
                        clean_trans,
                        pref.notes or "",
                        1 if pref.keep_untranslated else 0,
                        pref.confidence,
                        created_at,
                        now,
                    ),
                )
            conn.commit()

        return len(records)

    def delete_preference(self, user_id: str, german_term: str) -> bool:
        """Delete a terminology preference for *user_id*."""
        if not user_id or not user_id.strip() or not german_term or not german_term.strip():
            return False

        clean_term = german_term.strip()
        db_path = self._get_db_path(user_id)
        if not db_path.exists():
            return False

        with self._lock, self._connection(db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM user_term_preferences WHERE german_term = ?",
                (clean_term,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_user_preferences(self, user_id: str) -> None:
        """Clear all terminology preferences for *user_id*."""
        if not user_id or not user_id.strip():
            return

        db_path = self._get_db_path(user_id)
        if not db_path.exists():
            return

        with self._lock, self._connection(db_path) as conn:
            conn.execute("DELETE FROM user_term_preferences;")
            conn.commit()

    def export_tsv(self, user_id: str) -> bytes:
        """Export user vocabulary as RFC 4180 compliant TSV bytes with header `de\\ten`."""
        preferences = self.get_user_preferences(user_id)
        lines: list[str] = ["de\ten"]

        for term in sorted(preferences.keys()):
            pref = preferences[term]
            translation = pref.german_term if pref.keep_untranslated else pref.preferred_translation
            esc_term = _escape_rfc4180_field(pref.german_term)
            esc_trans = _escape_rfc4180_field(translation)
            lines.append(f"{esc_term}\t{esc_trans}")

        tsv_content = "\n".join(lines) + "\n"
        return tsv_content.encode("utf-8")
