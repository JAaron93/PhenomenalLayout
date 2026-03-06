"""SQLite database management for user choices."""

import itertools
import json
import logging
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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

logger = logging.getLogger(__name__)


class ChoiceDatabase:
    """SQLite database manager for user choices."""

    def __init__(
        self,
        db_path: str = "database/user_choices.db",
        learning_rate_alpha: float = 0.1,
        ensure_ascii: bool = False,
        batch_size: int = 1000,
    ) -> None:
        """Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file
            learning_rate_alpha: Learning rate for choice success rate updates (0.001-1.0)
            ensure_ascii: Whether to ensure ASCII-only JSON encoding (False preserves international characters)
            batch_size: Size of batches for bulk operations (1000-5000 recommended)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Validate and set configurable parameters
        self._learning_rate_alpha = self._validate_alpha(learning_rate_alpha)
        self._ensure_ascii = self._validate_boolean(ensure_ascii, "ensure_ascii")
        self._batch_size = self._validate_batch_size(batch_size)

        # Create database and tables
        self._initialize_database()

        logger.info(f"ChoiceDatabase initialized at {self.db_path}")
        logger.info(
            f"Configuration: alpha={self._learning_rate_alpha}, ensure_ascii={self._ensure_ascii}, batch_size={self._batch_size}"
        )

    def _validate_alpha(self, alpha: float) -> float:
        """Validate learning rate alpha parameter.

        Args:
            alpha: Learning rate value to validate

        Returns:
            Validated alpha value

        Raises:
            ValueError: If alpha is not within valid range (0.001-1.0)
        """
        if not isinstance(alpha, (int, float)):
            raise ValueError(f"Learning rate alpha must be a number, got {type(alpha)}")

        if not (0.001 <= alpha <= 1.0):
            raise ValueError(
                f"Learning rate alpha must be between 0.001 and 1.0, got {alpha}"
            )

        return float(alpha)

    def _validate_boolean(self, value: bool, param_name: str) -> bool:
        """Validate boolean parameter.

        Args:
            value: Boolean value to validate
            param_name: Name of the parameter for error messages

        Returns:
            Validated boolean value

        Raises:
            ValueError: If value is not a boolean
        """
        if not isinstance(value, bool):
            raise ValueError(f"{param_name} must be a boolean, got {type(value)}")

        return value

    def _validate_batch_size(self, batch_size: int) -> int:
        """Validate batch size parameter.

        Args:
            batch_size: Batch size value to validate

        Returns:
            Validated batch size value

        Raises:
            ValueError: If batch_size is not within valid range (1-10000)
        """
        if not isinstance(batch_size, int):
            raise ValueError(f"Batch size must be an integer, got {type(batch_size)}")

        if not (1 <= batch_size <= 10000):
            raise ValueError(
                f"Batch size must be between 1 and 10000, got {batch_size}"
            )

        return batch_size

    @property
    def learning_rate_alpha(self) -> float:
        """Get the current learning rate alpha value."""
        return self._learning_rate_alpha

    @learning_rate_alpha.setter
    def learning_rate_alpha(self, value: float) -> None:
        """Set the learning rate alpha value with validation."""
        self._learning_rate_alpha = self._validate_alpha(value)
        logger.info(f"Learning rate alpha updated to {self._learning_rate_alpha}")

    @property
    def ensure_ascii(self) -> bool:
        """Get the current ensure_ascii setting."""
        return self._ensure_ascii

    @ensure_ascii.setter
    def ensure_ascii(self, value: bool) -> None:
        """Set the ensure_ascii setting with validation."""
        self._ensure_ascii = self._validate_boolean(value, "ensure_ascii")
        logger.info(f"ensure_ascii updated to {self._ensure_ascii}")

    @property
    def batch_size(self) -> int:
        """Get the current batch size."""
        return self._batch_size

    @batch_size.setter
    def batch_size(self, value: int) -> None:
        """Set the batch size with validation."""
        self._batch_size = self._validate_batch_size(value)
        logger.info(f"Batch size updated to {self._batch_size}")

    def _initialize_database(self) -> None:
        """Initialize database schema."""
        try:
            with self._get_connection() as conn:
                self._create_tables(conn)
                self._create_indexes(conn)
                conn.commit()
                logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Create database tables."""
        # User choices table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_choices (
                choice_id TEXT PRIMARY KEY,
                neologism_term TEXT NOT NULL,
                choice_type TEXT NOT NULL,
                translation_result TEXT DEFAULT '',
                choice_scope TEXT NOT NULL,
                confidence_level REAL DEFAULT 1.0,
                user_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_used_at TEXT,
                usage_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 1.0,
                session_id TEXT,
                document_id TEXT,
                parent_choice_id TEXT,
                is_validated BOOLEAN DEFAULT 0,
                validation_source TEXT DEFAULT '',
                quality_score REAL DEFAULT 0.0,
                export_tags TEXT DEFAULT '[]',
                import_source TEXT DEFAULT '',
                context_data TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES choice_sessions(session_id),
                FOREIGN KEY (parent_choice_id) REFERENCES user_choices(choice_id)
            )
        """
        )

        # Choice sessions table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS choice_sessions (
                session_id TEXT PRIMARY KEY,
                session_name TEXT DEFAULT '',
                status TEXT NOT NULL,
                document_id TEXT,
                document_name TEXT DEFAULT '',
                user_id TEXT,
                source_language TEXT DEFAULT '',
                target_language TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                total_choices INTEGER DEFAULT 0,
                translate_count INTEGER DEFAULT 0,
                preserve_count INTEGER DEFAULT 0,
                custom_count INTEGER DEFAULT 0,
                skip_count INTEGER DEFAULT 0,
                average_confidence REAL DEFAULT 0.0,
                consistency_score REAL DEFAULT 0.0,
                auto_apply_choices BOOLEAN DEFAULT 1,
                conflict_resolution_strategy TEXT DEFAULT 'context_specific',
                session_notes TEXT DEFAULT '',
                session_tags TEXT DEFAULT '[]'
            )
        """
        )

        # Choice conflicts table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS choice_conflicts (
                conflict_id TEXT PRIMARY KEY,
                neologism_term TEXT NOT NULL,
                choice_a_id TEXT NOT NULL,
                choice_b_id TEXT NOT NULL,
                conflict_type TEXT DEFAULT 'translation_mismatch',
                severity REAL DEFAULT 0.5,
                context_similarity REAL DEFAULT 0.0,
                resolution_strategy TEXT DEFAULT 'latest_wins',
                resolved_choice_id TEXT,
                resolution_notes TEXT DEFAULT '',
                detected_at TEXT NOT NULL,
                resolved_at TEXT,
                session_id TEXT,
                auto_resolved BOOLEAN DEFAULT 0,
                FOREIGN KEY (choice_a_id) REFERENCES user_choices(choice_id),
                FOREIGN KEY (choice_b_id) REFERENCES user_choices(choice_id),
                FOREIGN KEY (session_id) REFERENCES choice_sessions(session_id)
            )
        """
        )

        # Choice contexts table (for efficient context matching)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS choice_contexts (
                context_id TEXT PRIMARY KEY,
                choice_id TEXT NOT NULL,
                context_hash TEXT NOT NULL,
                semantic_field TEXT DEFAULT '',
                philosophical_domain TEXT DEFAULT '',
                author TEXT DEFAULT '',
                source_language TEXT DEFAULT '',
                target_language TEXT DEFAULT '',
                surrounding_terms TEXT DEFAULT '[]',
                related_concepts TEXT DEFAULT '[]',
                similarity_threshold REAL DEFAULT 0.8,
                FOREIGN KEY (choice_id) REFERENCES user_choices(choice_id)
            )
        """
        )

        # Translation preferences table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS translation_preferences (
                preference_id TEXT PRIMARY KEY,
                user_id TEXT,
                default_choice_scope TEXT DEFAULT 'contextual',
                default_conflict_resolution TEXT DEFAULT 'context_specific',
                context_similarity_threshold REAL DEFAULT 0.8,
                auto_apply_similar_choices BOOLEAN DEFAULT 1,
                min_confidence_threshold REAL DEFAULT 0.5,
                require_validation BOOLEAN DEFAULT 0,
                language_pair_preferences TEXT DEFAULT '{}',
                domain_preferences TEXT DEFAULT '{}',
                export_format TEXT DEFAULT 'json',
                include_context BOOLEAN DEFAULT 1,
                include_statistics BOOLEAN DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )

        # Database metadata table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS database_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )

        # Insert schema version
        conn.execute(
            """
            INSERT OR REPLACE INTO database_metadata (key, value, updated_at)
            VALUES ('schema_version', '1.0', ?)
        """,
            (datetime.now().isoformat(),),
        )

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create database indexes for performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_user_choices_term ON user_choices(neologism_term)",
            "CREATE INDEX IF NOT EXISTS idx_user_choices_session ON user_choices(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_choices_type ON user_choices(choice_type)",
            "CREATE INDEX IF NOT EXISTS idx_user_choices_created ON user_choices(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_user_choices_updated ON user_choices(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_status ON choice_sessions(status)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON choice_sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_created ON choice_sessions(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_conflicts_term ON choice_conflicts(neologism_term)",
            "CREATE INDEX IF NOT EXISTS idx_conflicts_session ON choice_conflicts(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_conflicts_resolved ON choice_conflicts(resolved_at)",
            "CREATE INDEX IF NOT EXISTS idx_contexts_hash ON choice_contexts(context_hash)",
            "CREATE INDEX IF NOT EXISTS idx_contexts_semantic ON choice_contexts(semantic_field)",
            "CREATE INDEX IF NOT EXISTS idx_contexts_domain ON choice_contexts(philosophical_domain)",
            "CREATE INDEX IF NOT EXISTS idx_preferences_user ON translation_preferences(user_id)",
        ]

        for index_sql in indexes:
            conn.execute(index_sql)

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    # User Choice CRUD operations

    def save_user_choice(self, choice: UserChoice) -> bool:
        """Save a user choice to the database."""
        if choice is None:
            raise TypeError("choice must be a UserChoice, got None")
        try:
            with self._get_connection() as conn:
                # Insert or update user choice
                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_choices (
                        choice_id, neologism_term, choice_type, translation_result,
                        choice_scope, confidence_level, user_notes, created_at,
                        updated_at, last_used_at, usage_count, success_rate,
                        session_id, document_id, parent_choice_id, is_validated,
                        validation_source, quality_score, export_tags,
                        import_source, context_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        choice.choice_id,
                        choice.neologism_term,
                        choice.choice_type.value,
                        choice.translation_result,
                        choice.choice_scope.value,
                        choice.confidence_level,
                        choice.user_notes,
                        choice.created_at,
                        choice.updated_at,
                        choice.last_used_at,
                        choice.usage_count,
                        choice.success_rate,
                        choice.session_id,
                        choice.document_id,
                        choice.parent_choice_id,
                        choice.is_validated,
                        choice.validation_source,
                        choice.quality_score,
                        json.dumps(list(choice.export_tags)),
                        choice.import_source,
                        json.dumps(choice.context.to_dict()),
                    ),
                )

                # Save context data
                self._save_choice_context(conn, choice)

                conn.commit()
                logger.debug(f"Saved user choice: {choice.choice_id}")
                return True

        except Exception as e:
            logger.error(f"Error saving user choice: {e}")
            return False

    def _save_choice_context(
        self, conn: sqlite3.Connection, choice: UserChoice
    ) -> None:
        """Save choice context data for efficient matching."""
        context_id = f"ctx_{choice.choice_id}"

        conn.execute(
            """
            INSERT OR REPLACE INTO choice_contexts (
                context_id, choice_id, context_hash, semantic_field,
                philosophical_domain, author, source_language, target_language,
                surrounding_terms, related_concepts, similarity_threshold
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                context_id,
                choice.choice_id,
                choice.context.generate_context_hash(),
                choice.context.semantic_field,
                choice.context.philosophical_domain,
                choice.context.author,
                choice.context.source_language,
                choice.context.target_language,
                json.dumps(choice.context.surrounding_terms),
                json.dumps(choice.context.related_concepts),
                choice.context.context_similarity_threshold,
            ),
        )

    def get_user_choice(self, choice_id: str) -> UserChoice | None:
        """Get a user choice by ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM user_choices WHERE choice_id = ?
                """,
                    (choice_id,),
                )

                row = cursor.fetchone()
                if row:
                    return self._row_to_user_choice(row)
                return None

        except Exception as e:
            logger.error(f"Error getting user choice: {e}")
            return None

    def get_choices_by_term(
        self, neologism_term: str, limit: int = 100
    ) -> list[UserChoice]:
        """Get all choices for a specific neologism term."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM user_choices
                    WHERE neologism_term = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """,
                    (neologism_term, limit),
                )

                return [self._row_to_user_choice(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Error getting choices by term: {e}")
            return []

    def get_choices_by_session(self, session_id: str) -> list[UserChoice]:
        """Get all choices for a specific session."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM user_choices
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                """,
                    (session_id,),
                )

                return [self._row_to_user_choice(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Error getting choices by session: {e}")
            return []

    def search_similar_choices(
        self, context: TranslationContext, limit: int = 10
    ) -> list[UserChoice]:
        """Search for choices with similar contexts."""
        try:
            with self._get_connection() as conn:
                # Search by context components
                cursor = conn.execute(
                    """
                    SELECT uc.* FROM user_choices uc
                    JOIN choice_contexts cc ON uc.choice_id = cc.choice_id
                    WHERE cc.semantic_field = ? OR cc.philosophical_domain = ?
                    OR cc.author = ? OR (cc.source_language = ? AND cc.target_language = ?)
                    ORDER BY uc.updated_at DESC
                    LIMIT ?
                """,
                    (
                        context.semantic_field,
                        context.philosophical_domain,
                        context.author,
                        context.source_language,
                        context.target_language,
                        limit,
                    ),
                )

                return [self._row_to_user_choice(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Error searching similar choices: {e}")
            return []

    def update_choice_usage(self, choice_id: str, success: bool = True) -> bool:
        """Update choice usage statistics."""
        try:
            with self._get_connection() as conn:
                # Get current stats
                cursor = conn.execute(
                    """
                    SELECT usage_count, success_rate FROM user_choices WHERE choice_id = ?
                """,
                    (choice_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return False

                current_count = row["usage_count"]
                current_rate = row["success_rate"]

                # Update stats
                new_count = current_count + 1
                alpha = self._learning_rate_alpha  # Configurable learning rate
                if success:
                    new_rate = current_rate * (1 - alpha) + alpha
                else:
                    new_rate = current_rate * (1 - alpha)

                # Update database
                conn.execute(
                    """
                    UPDATE user_choices
                    SET usage_count = ?, success_rate = ?,
                        last_used_at = ?, updated_at = ?
                    WHERE choice_id = ?
                """,
                    (
                        new_count,
                        new_rate,
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                        choice_id,
                    ),
                )

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error updating choice usage: {e}")
            return False

    def delete_user_choice(self, choice_id: str) -> bool:
        """Delete a user choice."""
        try:
            with self._get_connection() as conn:
                # Delete from contexts first (foreign key constraint)
                conn.execute(
                    "DELETE FROM choice_contexts WHERE choice_id = ?", (choice_id,)
                )

                # Delete the choice
                cursor = conn.execute(
                    "DELETE FROM user_choices WHERE choice_id = ?", (choice_id,)
                )

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Error deleting user choice: {e}")
            return False

    # Session CRUD operations

    def save_session(self, session: ChoiceSession) -> bool:
        """Save a choice session."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO choice_sessions (
                        session_id, session_name, status, document_id, document_name,
                        user_id, source_language, target_language, created_at,
                        updated_at, completed_at, total_choices, translate_count,
                        preserve_count, custom_count, skip_count, average_confidence,
                        consistency_score, auto_apply_choices, conflict_resolution_strategy,
                        session_notes, session_tags
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        session.session_id,
                        session.session_name,
                        session.status.value,
                        session.document_id,
                        session.document_name,
                        session.user_id,
                        session.source_language,
                        session.target_language,
                        session.created_at,
                        session.updated_at,
                        session.completed_at,
                        session.total_choices,
                        session.translate_count,
                        session.preserve_count,
                        session.custom_count,
                        session.skip_count,
                        session.average_confidence,
                        session.consistency_score,
                        session.auto_apply_choices,
                        session.conflict_resolution_strategy.value,
                        session.session_notes,
                        json.dumps(list(session.session_tags)),
                    ),
                )

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return False

    def get_session(self, session_id: str) -> ChoiceSession | None:
        """Get a choice session by ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM choice_sessions WHERE session_id = ?
                """,
                    (session_id,),
                )

                row = cursor.fetchone()
                if row:
                    return self._row_to_choice_session(row)
                return None

        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None

    def get_active_sessions(self) -> list[ChoiceSession]:
        """Get all active sessions."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM choice_sessions
                    WHERE status = 'active'
                    ORDER BY updated_at DESC
                """
                )

                return [self._row_to_choice_session(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return []

    def get_user_sessions(self, user_id: str, limit: int = 50) -> list[ChoiceSession]:
        """Get sessions for a specific user."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM choice_sessions
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (user_id, limit),
                )

                return [self._row_to_choice_session(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            return []

    def complete_session(self, session_id: str) -> bool:
        """Mark a session as completed."""
        try:
            with self._get_connection() as conn:
                now = datetime.now().isoformat()
                cursor = conn.execute(
                    """
                    UPDATE choice_sessions
                    SET status = 'completed', completed_at = ?, updated_at = ?
                    WHERE session_id = ?
                """,
                    (now, now, session_id),
                )

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Error completing session: {e}")
            return False

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all associated choices."""
        try:
            with self._get_connection() as conn:
                # Delete associated contexts first
                conn.execute(
                    """
                    DELETE FROM choice_contexts
                    WHERE choice_id IN (
                        SELECT choice_id FROM user_choices WHERE session_id = ?
                    )
                """,
                    (session_id,),
                )

                # Delete associated choices
                conn.execute(
                    "DELETE FROM user_choices WHERE session_id = ?", (session_id,)
                )

                # Delete conflicts
                conn.execute(
                    "DELETE FROM choice_conflicts WHERE session_id = ?", (session_id,)
                )

                # Delete the session
                cursor = conn.execute(
                    "DELETE FROM choice_sessions WHERE session_id = ?", (session_id,)
                )

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    # Conflict management

    def save_conflict(self, conflict: ChoiceConflict) -> bool:
        """Save a choice conflict."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO choice_conflicts (
                        conflict_id, neologism_term, choice_a_id, choice_b_id,
                        conflict_type, severity, context_similarity, resolution_strategy,
                        resolved_choice_id, resolution_notes, detected_at, resolved_at,
                        session_id, auto_resolved
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        conflict.conflict_id,
                        conflict.neologism_term,
                        conflict.choice_a.choice_id,
                        conflict.choice_b.choice_id,
                        conflict.conflict_type,
                        conflict.severity,
                        conflict.context_similarity,
                        conflict.resolution_strategy.value,
                        conflict.resolved_choice_id,
                        conflict.resolution_notes,
                        conflict.detected_at,
                        conflict.resolved_at,
                        conflict.session_id,
                        conflict.auto_resolved,
                    ),
                )

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Error saving conflict: {e}")
            return False

    def get_unresolved_conflicts(self) -> list[ChoiceConflict]:
        """Get all unresolved conflicts."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM choice_conflicts
                    WHERE resolved_at IS NULL
                    ORDER BY detected_at DESC
                """
                )

                conflicts = []
                for row in cursor.fetchall():
                    conflict = self._row_to_choice_conflict(row)
                    if conflict:
                        conflicts.append(conflict)

                return conflicts

        except Exception as e:
            logger.error(f"Error getting unresolved conflicts: {e}")
            return []

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution_strategy: ConflictResolution,
        resolved_choice_id: str | None = None,
        notes: str = "",
    ) -> bool:
        """Resolve a conflict."""
        try:
            with self._get_connection() as conn:
                now = datetime.now().isoformat()
                cursor = conn.execute(
                    """
                    UPDATE choice_conflicts
                    SET resolution_strategy = ?, resolved_choice_id = ?,
                        resolution_notes = ?, resolved_at = ?, auto_resolved = 1
                    WHERE conflict_id = ?
                """,
                    (
                        resolution_strategy.value,
                        resolved_choice_id,
                        notes,
                        now,
                        conflict_id,
                    ),
                )

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Error resolving conflict: {e}")
            return False

    # Utility methods

    def _row_to_user_choice(self, row: sqlite3.Row) -> UserChoice:
        """Convert database row to UserChoice object."""
        context_data = json.loads(row["context_data"])
        context = TranslationContext(
            sentence_context=context_data.get("sentence_context", ""),
            paragraph_context=context_data.get("paragraph_context", ""),
            document_context=context_data.get("document_context", ""),
            semantic_field=context_data.get("semantic_field", ""),
            philosophical_domain=context_data.get("philosophical_domain", ""),
            author=context_data.get("author", ""),
            source_language=context_data.get("source_language", ""),
            target_language=context_data.get("target_language", ""),
            page_number=context_data.get("page_number"),
            chapter=context_data.get("chapter"),
            section=context_data.get("section"),
            surrounding_terms=context_data.get("surrounding_terms", []),
            related_concepts=context_data.get("related_concepts", []),
            context_similarity_threshold=context_data.get(
                "context_similarity_threshold", 0.8
            ),
            confidence_score=context_data.get("confidence_score", 0.0),
        )

        return UserChoice(
            choice_id=row["choice_id"],
            neologism_term=row["neologism_term"],
            choice_type=ChoiceType(row["choice_type"]),
            translation_result=row["translation_result"],
            context=context,
            choice_scope=ChoiceScope(row["choice_scope"]),
            confidence_level=row["confidence_level"],
            user_notes=row["user_notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_used_at=row["last_used_at"],
            usage_count=row["usage_count"],
            success_rate=row["success_rate"],
            session_id=row["session_id"],
            document_id=row["document_id"],
            parent_choice_id=row["parent_choice_id"],
            is_validated=bool(row["is_validated"]),
            validation_source=row["validation_source"],
            quality_score=row["quality_score"],
            export_tags=set(json.loads(row["export_tags"])),
            import_source=row["import_source"],
        )

    def _row_to_choice_session(self, row: sqlite3.Row) -> ChoiceSession:
        """Convert database row to ChoiceSession object."""
        return ChoiceSession(
            session_id=row["session_id"],
            session_name=row["session_name"],
            status=SessionStatus(row["status"]),
            document_id=row["document_id"],
            document_name=row["document_name"],
            user_id=row["user_id"],
            source_language=row["source_language"],
            target_language=row["target_language"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            total_choices=row["total_choices"],
            translate_count=row["translate_count"],
            preserve_count=row["preserve_count"],
            custom_count=row["custom_count"],
            skip_count=row["skip_count"],
            average_confidence=row["average_confidence"],
            consistency_score=row["consistency_score"],
            auto_apply_choices=bool(row["auto_apply_choices"]),
            conflict_resolution_strategy=ConflictResolution(
                row["conflict_resolution_strategy"]
            ),
            session_notes=row["session_notes"],
            session_tags=set(json.loads(row["session_tags"])),
        )

    def _row_to_choice_conflict(self, row: sqlite3.Row) -> ChoiceConflict | None:
        """Convert database row to ChoiceConflict object."""
        try:
            choice_a = self.get_user_choice(row["choice_a_id"])
            choice_b = self.get_user_choice(row["choice_b_id"])

            if not choice_a or not choice_b:
                return None

            return ChoiceConflict(
                conflict_id=row["conflict_id"],
                neologism_term=row["neologism_term"],
                choice_a=choice_a,
                choice_b=choice_b,
                conflict_type=row["conflict_type"],
                severity=row["severity"],
                context_similarity=row["context_similarity"],
                resolution_strategy=ConflictResolution(row["resolution_strategy"]),
                resolved_choice_id=row["resolved_choice_id"],
                resolution_notes=row["resolution_notes"],
                detected_at=row["detected_at"],
                resolved_at=row["resolved_at"],
                session_id=row["session_id"],
                auto_resolved=bool(row["auto_resolved"]),
            )

        except Exception as e:
            logger.error(f"Error converting conflict row: {e}")
            return None

    def cleanup_expired_sessions(self, expiry_hours: int = 24) -> int:
        """Clean up expired sessions."""
        try:
            expiry_time = datetime.now() - timedelta(hours=expiry_hours)
            expiry_iso = expiry_time.isoformat()

            with self._get_connection() as conn:
                # Mark sessions as expired
                cursor = conn.execute(
                    """
                    UPDATE choice_sessions
                    SET status = 'expired', updated_at = ?
                    WHERE status = 'active' AND created_at < ?
                """,
                    (datetime.now().isoformat(), expiry_iso),
                )

                expired_count = cursor.rowcount
                conn.commit()

                logger.info(f"Marked {expired_count} sessions as expired")
                return expired_count

        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0

    def get_database_statistics(self) -> dict[str, Any]:
        """Get database statistics."""
        try:
            with self._get_connection() as conn:
                stats = {}

                # Choice counts
                cursor = conn.execute("SELECT COUNT(*) FROM user_choices")
                stats["total_choices"] = cursor.fetchone()[0]

                # Session counts
                cursor = conn.execute("SELECT COUNT(*) FROM choice_sessions")
                stats["total_sessions"] = cursor.fetchone()[0]

                cursor = conn.execute(
                    "SELECT COUNT(*) FROM choice_sessions WHERE status = 'active'"
                )
                stats["active_sessions"] = cursor.fetchone()[0]

                # Conflict counts
                cursor = conn.execute("SELECT COUNT(*) FROM choice_conflicts")
                stats["total_conflicts"] = cursor.fetchone()[0]

                cursor = conn.execute(
                    "SELECT COUNT(*) FROM choice_conflicts WHERE resolved_at IS NULL"
                )
                stats["unresolved_conflicts"] = cursor.fetchone()[0]

                # Choice type distribution
                cursor = conn.execute(
                    """
                    SELECT choice_type, COUNT(*) as count
                    FROM user_choices
                    GROUP BY choice_type
                """
                )
                stats["choice_type_distribution"] = dict(cursor.fetchall())

                # Database size
                stats["db_size_bytes"] = self.db_path.stat().st_size

                return stats

        except Exception as e:
            logger.error(f"Error getting database statistics: {e}")
            return {}

    def export_choices_to_json(
        self, session_id: str | None = None, file_path: str | None = None
    ) -> str | None:
        """Export choices to JSON format."""
        try:
            choices = []

            if session_id:
                choices = self.get_choices_by_session(session_id)
            else:
                # Export all choices
                with self._get_connection() as conn:
                    cursor = conn.execute(
                        "SELECT * FROM user_choices ORDER BY created_at"
                    )
                    choices = [
                        self._row_to_user_choice(row) for row in cursor.fetchall()
                    ]

            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "total_choices": len(choices),
                "choices": [choice.to_dict() for choice in choices],
            }

            json_data = json.dumps(
                export_data, indent=2, ensure_ascii=self._ensure_ascii
            )

            if file_path:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(json_data)
                logger.info(f"Exported {len(choices)} choices to {file_path}")

            return json_data

        except Exception as e:
            logger.error(f"Error exporting choices: {e}")
            return None

    def import_choices_from_json(
        self, json_data: str, session_id: str | None = None
    ) -> int:
        """Import choices from JSON format using high-performance batch operations.

        Args:
            json_data: JSON string containing choices data
            session_id: Optional session ID to assign to imported choices

        Returns:
            Number of successfully imported choices
        """
        try:
            import_data = json.loads(json_data)
            choices_data = import_data.get("choices", [])

            if not choices_data:
                logger.info("No choices found in JSON data")
                return 0

            # Phase 1: Collect and validate all UserChoice objects in memory
            logger.info(f"Starting batch import of {len(choices_data)} choices...")
            start_time = datetime.now()

            validated_choices = []
            validation_errors = []

            for i, choice_data in enumerate(choices_data):
                try:
                    choice = self._validate_and_reconstruct_choice(
                        choice_data, session_id
                    )
                    validated_choices.append(choice)

                    # Log progress for large imports
                    if (i + 1) % 100 == 0:
                        logger.info(f"Validated {i + 1}/{len(choices_data)} choices...")

                except Exception as e:
                    error_msg = f"Choice {choice_data.get('choice_id', 'unknown')} validation failed: {e}"
                    validation_errors.append(error_msg)
                    logger.warning(error_msg)
                    continue

            if not validated_choices:
                logger.warning("No valid choices found after validation")
                return 0

            # Phase 2: Execute bulk database operations in batches
            imported_count = self._bulk_import_choices(validated_choices)

            # Log performance metrics
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info(
                f"Batch import completed: {imported_count}/{len(choices_data)} choices imported in {duration:.2f}s"
            )
            logger.info(f"Performance: {imported_count / duration:.1f} choices/second")

            if validation_errors:
                logger.warning(
                    f"Import completed with {len(validation_errors)} validation errors"
                )

            return imported_count

        except Exception as e:
            logger.error(f"Error importing choices: {e}")
            return 0

    def _validate_and_reconstruct_choice(
        self, choice_data: Mapping[str, Any], session_id: str | None = None
    ) -> UserChoice:
        """Validate and reconstruct a UserChoice object from JSON data.

        Args:
            choice_data: Mapping containing choice data
            session_id: Optional session ID to assign

        Returns:
            Validated UserChoice object

        Raises:
            ValueError: If validation fails
        """
        # Validate required fields
        required_fields = ["choice_id", "neologism_term", "choice_type"]
        for field in required_fields:
            if field not in choice_data:
                raise ValueError(f"Missing required field: {field}")

        # Validate choice_type
        try:
            choice_type = ChoiceType(choice_data["choice_type"])
        except ValueError as e:
            raise ValueError(f"Invalid choice_type: {e}") from e

        # Validate choice_scope
        choice_scope_value = choice_data.get("choice_scope", "contextual")
        try:
            choice_scope = ChoiceScope(choice_scope_value)
        except ValueError as e:
            raise ValueError(f"Invalid choice_scope: {e}") from e

        # Validate numeric fields
        confidence_level = choice_data.get("confidence_level", 1.0)
        if not isinstance(confidence_level, (int, float)) or not (
            0.0 <= confidence_level <= 1.0
        ):
            raise ValueError(
                f"Invalid confidence_level: must be between 0.0 and 1.0, got {confidence_level}"
            )

        usage_count = choice_data.get("usage_count", 0)
        if not isinstance(usage_count, int) or usage_count < 0:
            raise ValueError(
                f"Invalid usage_count: must be non-negative integer, got {usage_count}"
            )

        success_rate = choice_data.get("success_rate", 1.0)
        if not isinstance(success_rate, (int, float)) or not (
            0.0 <= success_rate <= 1.0
        ):
            raise ValueError(
                f"Invalid success_rate: must be between 0.0 and 1.0, got {success_rate}"
            )

        quality_score = choice_data.get("quality_score", 0.0)
        if not isinstance(quality_score, (int, float)):
            raise ValueError(
                f"Invalid quality_score: must be numeric, got {quality_score}"
            )

        # Reconstruct context
        context_data = choice_data.get("context", {})
        context = TranslationContext(
            sentence_context=context_data.get("sentence_context", ""),
            paragraph_context=context_data.get("paragraph_context", ""),
            document_context=context_data.get("document_context", ""),
            semantic_field=context_data.get("semantic_field", ""),
            philosophical_domain=context_data.get("philosophical_domain", ""),
            author=context_data.get("author", ""),
            source_language=context_data.get("source_language", ""),
            target_language=context_data.get("target_language", ""),
            page_number=context_data.get("page_number"),
            chapter=context_data.get("chapter"),
            section=context_data.get("section"),
            surrounding_terms=context_data.get("surrounding_terms", []),
            related_concepts=context_data.get("related_concepts", []),
            context_similarity_threshold=context_data.get(
                "context_similarity_threshold", 0.8
            ),
            confidence_score=context_data.get("confidence_score", 0.0),
        )

        # Create UserChoice object
        choice = UserChoice(
            choice_id=choice_data["choice_id"],
            neologism_term=choice_data["neologism_term"],
            choice_type=choice_type,
            translation_result=choice_data.get("translation_result", ""),
            context=context,
            choice_scope=choice_scope,
            confidence_level=confidence_level,
            user_notes=choice_data.get("user_notes", ""),
            created_at=choice_data.get("created_at", datetime.now().isoformat()),
            updated_at=choice_data.get("updated_at", datetime.now().isoformat()),
            last_used_at=choice_data.get("last_used_at"),
            usage_count=usage_count,
            success_rate=success_rate,
            session_id=session_id or choice_data.get("session_id"),
            document_id=choice_data.get("document_id"),
            parent_choice_id=choice_data.get("parent_choice_id"),
            is_validated=choice_data.get("is_validated", False),
            validation_source=choice_data.get("validation_source", ""),
            quality_score=quality_score,
            export_tags=set(choice_data.get("export_tags", [])),
            import_source=choice_data.get("import_source", ""),
        )

        return choice

    def _bulk_import_choices(self, choices: Iterable[UserChoice]) -> int:
        """Perform bulk import of validated choices using high-performance database operations.

        Args:
            choices: Iterable of validated UserChoice objects (processed in streaming batches)

        Returns:
            Number of successfully imported choices
        """
        # Create an iterator to process choices in streaming batches
        choices_iter = iter(choices)

        # Check if there are any choices to process
        try:
            first_choice = next(choices_iter)
        except StopIteration:
            return 0

        # Put the first choice back at the beginning of the iterator
        choices_iter = itertools.chain([first_choice], choices_iter)

        try:
            with self._get_connection() as conn:
                imported_count = 0
                failed_count = 0
                batch_number = 1

                # Process in streaming batches using islice to avoid loading everything into memory
                while True:
                    # Take the next batch from the iterator
                    batch = list(itertools.islice(choices_iter, self._batch_size))
                    if not batch:
                        break  # No more items

                    try:
                        batch_imported = self._import_choice_batch(conn, batch)
                        imported_count += batch_imported
                    except Exception as e:
                        logger.error(f"Error importing batch {batch_number}: {e}")
                        failed_count += len(batch)

                    batch_number += 1

                    # Log progress for large imports (every 10 batches or so)
                    if batch_number % 10 == 0:
                        logger.info(
                            f"Processing batch {batch_number}: {imported_count} total choices imported"
                        )

                conn.commit()
                if failed_count > 0:
                    logger.warning(
                        f"Bulk import completed with errors: {imported_count} succeeded, {failed_count} failed"
                    )
                else:
                    logger.info(
                        f"Bulk import transaction committed: {imported_count} choices"
                    )
                return imported_count

        except Exception as e:
            logger.error(f"Error during bulk import: {e}")
            return 0

    def _import_choice_batch(
        self, conn: sqlite3.Connection, batch: Sequence[UserChoice]
    ) -> int:
        """Import a batch of choices using executemany for optimal performance.

        Args:
            conn: Database connection
            batch: Sequence[UserChoice] to import

        Returns:
            Number of successfully imported choices in this batch
        """
        try:
            # Start savepoint transaction for the batch
            conn.execute("SAVEPOINT sp_batch")
            
            # Prepare batch data for user_choices table
            choice_rows = []
            context_rows = []

            for choice in batch:
                choice_row = (
                    choice.choice_id,
                    choice.neologism_term,
                    choice.choice_type.value,
                    choice.translation_result,
                    choice.choice_scope.value,
                    choice.confidence_level,
                    choice.user_notes,
                    choice.created_at,
                    choice.updated_at,
                    choice.last_used_at,
                    choice.usage_count,
                    choice.success_rate,
                    choice.session_id,
                    choice.document_id,
                    choice.parent_choice_id,
                    choice.is_validated,
                    choice.validation_source,
                    choice.quality_score,
                    json.dumps(list(choice.export_tags)),
                    choice.import_source,
                    json.dumps(choice.context.to_dict()),
                )
                choice_rows.append(choice_row)

                # Prepare context data
                context_id = f"ctx_{choice.choice_id}"
                context_row = (
                    context_id,
                    choice.choice_id,
                    choice.context.generate_context_hash(),
                    choice.context.semantic_field,
                    choice.context.philosophical_domain,
                    choice.context.author,
                    choice.context.source_language,
                    choice.context.target_language,
                    json.dumps(choice.context.surrounding_terms),
                    json.dumps(choice.context.related_concepts),
                    choice.context.context_similarity_threshold,
                )
                context_rows.append(context_row)

            # Execute batch insert for user_choices
            conn.executemany(
                """
                INSERT OR REPLACE INTO user_choices (
                    choice_id, neologism_term, choice_type, translation_result,
                    choice_scope, confidence_level, user_notes, created_at,
                    updated_at, last_used_at, usage_count, success_rate,
                    session_id, document_id, parent_choice_id, is_validated,
                    validation_source, quality_score, export_tags,
                    import_source, context_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                choice_rows,
            )

            # Execute batch insert for choice_contexts
            conn.executemany(
                """
                INSERT OR REPLACE INTO choice_contexts (
                    context_id, choice_id, context_hash, semantic_field,
                    philosophical_domain, author, source_language, target_language,
                    surrounding_terms, related_concepts, similarity_threshold
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                context_rows,
            )

            # Commit the batch transaction
            conn.execute("RELEASE SAVEPOINT sp_batch")
            return len(batch)

        except Exception as e:
            # Rollback to savepoint on error
            conn.execute("ROLLBACK TO SAVEPOINT sp_batch")
            conn.execute("RELEASE SAVEPOINT sp_batch")
            logger.error(f"Error importing choice batch: {e}")
            raise

    # Additional methods for data integrity validation

    def get_all_choices(self) -> list[UserChoice]:
        """Get all choices from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM user_choices ORDER BY created_at")
                return [self._row_to_user_choice(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all choices: {e}")
            return []

    def get_all_sessions(self) -> list[ChoiceSession]:
        """Get all sessions from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM choice_sessions ORDER BY created_at"
                )
                return [self._row_to_choice_session(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all sessions: {e}")
            return []

    def get_all_context_hashes(self) -> list[str]:
        """Get all unique context hashes from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT DISTINCT context_hash FROM choice_contexts"
                )
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all context hashes: {e}")
            return []

    def get_choices_by_context_hash(self, context_hash: str) -> list[UserChoice]:
        """Get choices by context hash."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT uc.* FROM user_choices uc
                    JOIN choice_contexts cc ON uc.choice_id = cc.choice_id
                    WHERE cc.context_hash = ?
                """,
                    (context_hash,),
                )
                return [self._row_to_user_choice(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting choices by context hash: {e}")
            return []
