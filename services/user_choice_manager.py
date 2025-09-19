"""User Choice Management System for neologism translation decisions."""

import logging
from datetime import datetime
from typing import Any, Optional

from database.choice_database import ChoiceDatabase
from models.neologism_models import DetectedNeologism, NeologismAnalysis
from models.user_choice_models import (
    ChoiceConflict,
    ChoiceScope,
    ChoiceSession,
    ChoiceType,
    ConflictResolution,
    SessionStatus,
    TranslationContext,
    UserChoice,
    create_choice_id,
    create_session_id,
    detect_choice_conflicts,
    filter_choices_by_context,
    find_best_matching_choice,
)

logger = logging.getLogger(__name__)


class UserChoiceManager:
    """Main service for managing user translation choices."""

    def __init__(
        self,
        db_path: str = "database/user_choices.db",
        auto_resolve_conflicts: bool = True,
        session_expiry_hours: int = 24,
    ):
        """Initialize the user choice manager.

        Args:
            db_path: Path to SQLite database file
            auto_resolve_conflicts: Whether to automatically resolve conflicts
            session_expiry_hours: Hours before sessions expire
        """
        self.db = ChoiceDatabase(db_path)
        self.auto_resolve_conflicts = auto_resolve_conflicts
        self.session_expiry_hours = session_expiry_hours

        # Active sessions cache
        self._active_sessions: dict[str, ChoiceSession] = {}

        # Load active sessions from database
        self._load_active_sessions()

        # Statistics tracking
        self.stats = {
            "total_choices_made": 0,
            "conflicts_resolved": 0,
            "sessions_created": 0,
            "cache_hits": 0,
            "context_matches": 0,
        }

        logger.info("UserChoiceManager initialized")

    def _load_active_sessions(self) -> None:
        """Load active sessions from database into cache."""
        try:
            active_sessions = self.db.get_active_sessions()
            for session in active_sessions:
                self._active_sessions[session.session_id] = session

            logger.info(f"Loaded {len(active_sessions)} active sessions")
        except Exception as e:
            logger.error(f"Error loading active sessions: {e}")

    # Session Management

    def create_session(
        self,
        session_name: str = "",
        document_id: Optional[str] = None,
        document_name: str = "",
        user_id: Optional[str] = None,
        source_language: str = "de",
        target_language: str = "en",
    ) -> ChoiceSession:
        """Create a new choice session."""
        session_id = create_session_id()

        session = ChoiceSession(
            session_id=session_id,
            session_name=session_name
            or f"Session {datetime.now().strftime('%Y%m%d_%H%M%S')}",
            document_id=document_id,
            document_name=document_name,
            user_id=user_id,
            source_language=source_language,
            target_language=target_language,
            status=SessionStatus.ACTIVE,
        )

        # Save to database
        if self.db.save_session(session):
            self._active_sessions[session_id] = session
            self.stats["sessions_created"] += 1
            logger.info(f"Created session: {session_id}")
            return session
        else:
            raise RuntimeError(f"Failed to create session: {session_id}")

    def get_session(self, session_id: str) -> Optional[ChoiceSession]:
        """Get a session by ID."""
        # Check cache first
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]

        # Load from database
        session = self.db.get_session(session_id)
        if session and session.status == SessionStatus.ACTIVE:
            self._active_sessions[session_id] = session

        return session

    def complete_session(self, session_id: str) -> bool:
        """Complete a session and calculate final statistics."""
        session = self.get_session(session_id)
        if not session:
            return False

        # Get all choices for this session
        choices = self.db.get_choices_by_session(session_id)

        # Calculate consistency score
        session.consistency_score = session.calculate_consistency_score(choices)

        # Complete the session
        session.complete_session()

        # Save to database
        if self.db.save_session(session):
            # Remove from active cache
            self._active_sessions.pop(session_id, None)
            logger.info(f"Completed session: {session_id}")
            return True

        return False

    def get_active_sessions(self) -> list[ChoiceSession]:
        """Get all active sessions."""
        return list(self._active_sessions.values())

    def get_user_sessions(self, user_id: str, limit: int = 50) -> list[ChoiceSession]:
        """Get sessions for a specific user."""
        return self.db.get_user_sessions(user_id, limit)

    # Choice Management

    def make_choice(
        self,
        neologism: DetectedNeologism,
        choice_type: ChoiceType,
        translation_result: str = "",
        session_id: Optional[str] = None,
        choice_scope: ChoiceScope = ChoiceScope.CONTEXTUAL,
        confidence_level: float = 1.0,
        user_notes: str = "",
    ) -> UserChoice:
        """Record a user choice for a detected neologism.

        Args:
            neologism: The detected neologism
            choice_type: Type of choice (translate, preserve, etc.)
            translation_result: The translation if applicable
            session_id: Session ID for this choice
            choice_scope: Scope of choice application
            confidence_level: User's confidence in this choice
            user_notes: Optional user notes

        Returns:
            UserChoice object representing the decision
        """
        # Create translation context from neologism
        context = self._create_context_from_neologism(neologism)

        # Create choice ID
        choice_id = create_choice_id(neologism.term, context.generate_context_hash())

        # Create user choice
        choice = UserChoice(
            choice_id=choice_id,
            neologism_term=neologism.term,
            choice_type=choice_type,
            translation_result=translation_result,
            context=context,
            choice_scope=choice_scope,
            confidence_level=confidence_level,
            user_notes=user_notes,
            session_id=session_id,
        )

        # Check for conflicts before saving
        existing_conflicts = self._check_for_conflicts(choice)

        # Save the choice
        if self.db.save_user_choice(choice):
            self.stats["total_choices_made"] += 1

            # Update session statistics
            if session_id and session_id in self._active_sessions:
                session = self._active_sessions[session_id]
                session.add_choice_stats(choice)
                self.db.save_session(session)

            # Handle conflicts
            if existing_conflicts and self.auto_resolve_conflicts:
                self._resolve_conflicts_automatically(existing_conflicts)

            logger.info(f"Saved user choice: {choice_id} for term '{neologism.term}'")
            return choice
        else:
            raise RuntimeError(f"Failed to save choice: {choice_id}")

    def get_choice_for_neologism(
        self, neologism: DetectedNeologism, session_id: Optional[str] = None
    ) -> Optional[UserChoice]:
        """Get the best matching choice for a detected neologism.

        Args:
            neologism: The detected neologism
            session_id: Current session ID for context

        Returns:
            Best matching UserChoice or None
        """
        # Create context from neologism
        target_context = self._create_context_from_neologism(neologism)

        # First, check for exact matches by term
        existing_choices = self.db.get_choices_by_term(neologism.term)

        if existing_choices:
            # Find best matching choice based on context
            best_match = find_best_matching_choice(existing_choices, target_context)

            if best_match:
                # Update usage statistics
                self.db.update_choice_usage(best_match.choice_id, success=True)
                self.stats["cache_hits"] += 1
                logger.debug(
                    f"Found matching choice for '{neologism.term}': {best_match.choice_id}"
                )
                return best_match

        # If no exact matches, search for similar context choices
        similar_choices = self.db.search_similar_choices(target_context)

        if similar_choices:
            # Filter by applicability
            applicable_choices = filter_choices_by_context(
                similar_choices, target_context
            )

            if applicable_choices:
                best_match = max(applicable_choices, key=lambda c: c.success_rate)
                self.stats["context_matches"] += 1
                logger.debug(
                    f"Found contextually similar choice for '{neologism.term}': {best_match.choice_id}"
                )
                return best_match

        return None

    def get_choices_by_term(self, term: str, limit: int = 100) -> list[UserChoice]:
        """Get all choices for a specific term."""
        return self.db.get_choices_by_term(term, limit)

    def get_session_choices(self, session_id: str) -> list[UserChoice]:
        """Get all choices for a session."""
        return self.db.get_choices_by_session(session_id)

    def update_choice(
        self, choice_id: str, updates: dict[str, Any], mark_as_used: bool = False
    ) -> bool:
        """Update an existing choice.

        Args:
            choice_id: ID of choice to update
            updates: Dictionary of field updates
            mark_as_used: Whether to mark as used

        Returns:
            True if successful
        """
        choice = self.db.get_user_choice(choice_id)
        if not choice:
            return False

        # Apply updates
        for field, value in updates.items():
            if hasattr(choice, field):
                setattr(choice, field, value)

        choice.updated_at = datetime.now().isoformat()

        # Mark as used if requested
        if mark_as_used:
            choice.update_usage_stats(success=True)

        return self.db.save_user_choice(choice)

    def delete_choice(self, choice_id: str) -> bool:
        """Delete a choice."""
        return self.db.delete_user_choice(choice_id)

    # Conflict Management

    def _check_for_conflicts(self, new_choice: UserChoice) -> list[ChoiceConflict]:
        """Check for conflicts with existing choices."""
        existing_choices = self.db.get_choices_by_term(new_choice.neologism_term)

        if not existing_choices:
            return []

        # Create list including the new choice
        all_choices = existing_choices + [new_choice]

        # Detect conflicts
        conflicts = detect_choice_conflicts(all_choices)

        return conflicts

    def _resolve_conflicts_automatically(self, conflicts: list[ChoiceConflict]) -> None:
        """Automatically resolve conflicts based on strategy."""
        for conflict in conflicts:
            # Analyze the conflict
            conflict.analyze_conflict()

            # Determine resolution strategy
            if conflict.context_similarity > 0.9:
                # Very similar contexts - use latest or highest confidence
                strategy = ConflictResolution.HIGHEST_CONFIDENCE
            elif conflict.context_similarity > 0.5:
                # Somewhat similar - keep both for context-specific use
                strategy = ConflictResolution.CONTEXT_SPECIFIC
            else:
                # Different contexts - latest wins
                strategy = ConflictResolution.LATEST_WINS

            # Resolve the conflict
            _ = conflict.resolve_conflict(strategy)

            # Save the conflict resolution
            if self.db.save_conflict(conflict):
                self.stats["conflicts_resolved"] += 1
                logger.info(f"Auto-resolved conflict: {conflict.conflict_id}")

    def get_unresolved_conflicts(self) -> list[ChoiceConflict]:
        """Get all unresolved conflicts."""
        return self.db.get_unresolved_conflicts()

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution_strategy: ConflictResolution,
        resolved_choice_id: Optional[str] = None,
        notes: str = "",
    ) -> bool:
        """Manually resolve a conflict."""
        return self.db.resolve_conflict(
            conflict_id, resolution_strategy, resolved_choice_id, notes
        )

    # Context Management

    def _create_context_from_neologism(
        self, neologism: DetectedNeologism
    ) -> TranslationContext:
        """Create translation context from detected neologism."""
        context = TranslationContext(
            sentence_context=neologism.sentence_context,
            paragraph_context=neologism.paragraph_context,
            semantic_field=neologism.philosophical_context.semantic_field,
            philosophical_domain=neologism.philosophical_context.semantic_field,
            author=next(
                iter(neologism.philosophical_context.author_terminology or []), ""
            ),
            page_number=neologism.page_number,
            surrounding_terms=neologism.philosophical_context.surrounding_terms[:10],
            related_concepts=neologism.philosophical_context.related_concepts[:10],
            confidence_score=neologism.confidence,
        )

        return context

    def find_similar_contexts(
        self, context: TranslationContext, similarity_threshold: float = 0.8
    ) -> list[UserChoice]:
        """Find choices with similar contexts."""
        similar_choices = self.db.search_similar_choices(context)

        # Filter by similarity threshold
        filtered_choices = []
        for choice in similar_choices:
            similarity = context.calculate_similarity(choice.context)
            if similarity >= similarity_threshold:
                filtered_choices.append(choice)

        return filtered_choices

    # Batch Operations

    def process_neologism_batch(
        self,
        neologisms: list[DetectedNeologism],
        session_id: Optional[str] = None,
        auto_apply_similar: bool = True,
    ) -> list[tuple[DetectedNeologism, Optional[UserChoice]]]:
        """Process a batch of neologisms and return suggested choices.

        Args:
            neologisms: List of detected neologisms
            session_id: Session ID for context
            auto_apply_similar: Whether to auto-apply similar choices

        Returns:
            List of (neologism, suggested_choice) tuples
        """
        results = []

        for neologism in neologisms:
            suggested_choice = self.get_choice_for_neologism(neologism, session_id)

            # If auto-applying and we have a high-confidence match
            if (
                auto_apply_similar
                and suggested_choice
                and suggested_choice.success_rate > 0.8
                and suggested_choice.choice_scope
                in [ChoiceScope.GLOBAL, ChoiceScope.CONTEXTUAL]
            ):
                # Apply the choice automatically
                new_choice = self.make_choice(
                    neologism=neologism,
                    choice_type=suggested_choice.choice_type,
                    translation_result=suggested_choice.translation_result,
                    session_id=session_id,
                    choice_scope=suggested_choice.choice_scope,
                    confidence_level=suggested_choice.confidence_level
                    * 0.9,  # Slightly lower confidence
                    user_notes=f"Auto-applied from choice {suggested_choice.choice_id}",
                )
                results.append((neologism, new_choice))
            else:
                results.append((neologism, suggested_choice))

        return results

    def apply_choices_to_analysis(
        self, analysis: NeologismAnalysis, session_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Apply user choices to a neologism analysis.

        Args:
            analysis: Neologism analysis to process
            session_id: Session ID for context

        Returns:
            Dictionary with applied choices and statistics
        """
        results = {
            "total_neologisms": len(analysis.detected_neologisms),
            "choices_found": 0,
            "choices_applied": 0,
            "new_choices_needed": 0,
            "applied_choices": [],
            "pending_choices": [],
        }

        for neologism in analysis.detected_neologisms:
            existing_choice = self.get_choice_for_neologism(neologism, session_id)

            if existing_choice:
                results["choices_found"] += 1
                results["applied_choices"].append(
                    {
                        "neologism": neologism.term,
                        "choice_type": existing_choice.choice_type.value,
                        "translation": existing_choice.translation_result,
                        "confidence": existing_choice.confidence_level,
                        "success_rate": existing_choice.success_rate,
                    }
                )
            else:
                results["new_choices_needed"] += 1
                results["pending_choices"].append(
                    {
                        "neologism": neologism.term,
                        "confidence": neologism.confidence,
                        "context": (
                            (neologism.sentence_context or "")[:100] + "..."
                            if neologism.sentence_context
                            and len(neologism.sentence_context) > 100
                            else (neologism.sentence_context or "")
                        ),
                    }
                )

        return results

    # Export/Import Operations

    def export_session_choices(
        self, session_id: str, file_path: Optional[str] = None
    ) -> Optional[str]:
        """Export choices for a session."""
        return self.db.export_choices_to_json(session_id, file_path)

    def export_all_choices(self, file_path: Optional[str] = None) -> Optional[str]:
        """Export all choices."""
        return self.db.export_choices_to_json(None, file_path)

    def import_choices(self, json_data: str, session_id: Optional[str] = None) -> int:
        """Import choices from JSON data."""
        return self.db.import_choices_from_json(json_data, session_id)

    def import_choices_from_dict(
        self, choices_dict: dict[str, Any], session_id: Optional[str] = None
    ) -> int:
        """Import choices from a dictionary.

        Args:
            choices_dict: Dictionary containing choice data
            session_id: Optional session ID to associate with imported choices

        Returns:
            Number of choices imported

        Raises:
            ValueError: If choices_dict is not a valid dictionary
            TypeError: If choices_dict contains invalid data types
        """
        if not isinstance(choices_dict, dict):
            raise ValueError("choices_dict must be a dictionary")

        if not choices_dict:
            return 0

        try:
            # Convert dictionary to JSON string for the database layer
            import json

            json_data = json.dumps(choices_dict)
            return self.db.import_choices_from_json(json_data, session_id)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid choice data format: {e!s}") from e

    def import_terminology_as_choices(
        self,
        terminology_dict: dict[str, str],
        session_id: Optional[str] = None,
        source_language: str = "de",
        target_language: str = "en",
    ) -> int:
        """Import terminology dictionary as user choices.

        Args:
            terminology_dict: Dictionary of term -> translation
            session_id: Session to associate with
            source_language: Source language code
            target_language: Target language code

        Returns:
            Number of choices imported
        """
        imported_count = 0

        for term, translation in terminology_dict.items():
            # Create a basic context
            context = TranslationContext(
                source_language=source_language,
                target_language=target_language,
                semantic_field="terminology",
                philosophical_domain="general",
            )

            # Create choice
            choice = UserChoice(
                choice_id=create_choice_id(term, context.generate_context_hash()),
                neologism_term=term,
                choice_type=ChoiceType.TRANSLATE,
                translation_result=translation,
                context=context,
                choice_scope=ChoiceScope.GLOBAL,
                confidence_level=0.8,
                session_id=session_id,
                import_source="terminology_import",
            )

            if self.db.save_user_choice(choice):
                imported_count += 1

        logger.info(f"Imported {imported_count} terminology entries as choices")
        return imported_count

    # Maintenance and Cleanup

    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        expired_count = self.db.cleanup_expired_sessions(self.session_expiry_hours)

        # Update active sessions cache
        self._load_active_sessions()

        return expired_count

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive statistics."""
        db_stats = self.db.get_database_statistics()

        return {
            "manager_stats": self.stats,
            "database_stats": db_stats,
            "active_sessions": len(self._active_sessions),
            "session_expiry_hours": self.session_expiry_hours,
            "auto_resolve_conflicts": self.auto_resolve_conflicts,
        }

    def validate_data_integrity(self) -> dict[str, Any]:
        """Validate data integrity and return report."""
        report = {
            "total_issues": 0,
            "orphaned_contexts": 0,
            "missing_choices": 0,
            "invalid_sessions": 0,
            "duplicate_choices": 0,
            "conflicting_choices": 0,
            "expired_sessions": 0,
            "recommendations": [],
        }

        try:
            logger.info("Starting data integrity validation")

            # 1. Check for orphaned contexts (contexts without corresponding choices)
            orphaned_contexts = self._check_orphaned_contexts()
            report["orphaned_contexts"] = len(orphaned_contexts)
            if orphaned_contexts:
                report["recommendations"].append(
                    f"Found {len(orphaned_contexts)} orphaned contexts that should be cleaned up"
                )

            # 2. Check for missing choice references (choices referencing non-existent sessions)
            missing_references = self._check_missing_choice_references()
            report["missing_choices"] = len(missing_references)
            if missing_references:
                report["recommendations"].append(
                    f"Found {len(missing_references)} choices with invalid session references"
                )

            # 3. Check for invalid session states
            invalid_sessions = self._check_invalid_sessions()
            report["invalid_sessions"] = len(invalid_sessions)
            if invalid_sessions:
                report["recommendations"].append(
                    f"Found {len(invalid_sessions)} sessions with invalid states"
                )

            # 4. Check for duplicate choices (same term + context hash)
            duplicate_choices = self._check_duplicate_choices()
            report["duplicate_choices"] = len(duplicate_choices)
            if duplicate_choices:
                report["recommendations"].append(
                    f"Found {len(duplicate_choices)} duplicate choices that should be merged"
                )

            # 5. Check for conflicting choices (same term, different translations)
            conflicting_choices = self._check_conflicting_choices()
            report["conflicting_choices"] = len(conflicting_choices)
            if conflicting_choices:
                report["recommendations"].append(
                    f"Found {len(conflicting_choices)} conflicting choices requiring resolution"
                )

            # 6. Check for expired sessions that should be cleaned up
            expired_sessions = self._check_expired_sessions()
            report["expired_sessions"] = len(expired_sessions)
            if expired_sessions:
                report["recommendations"].append(
                    f"Found {len(expired_sessions)} expired sessions ready for cleanup"
                )

            # Calculate total issues
            report["total_issues"] = (
                report["orphaned_contexts"]
                + report["missing_choices"]
                + report["invalid_sessions"]
                + report["duplicate_choices"]
                + report["conflicting_choices"]
            )

            # Add general recommendations
            if report["total_issues"] == 0:
                report["recommendations"].append(
                    "✓ Data integrity check completed successfully - no issues found"
                )
            else:
                report["recommendations"].append(
                    f"⚠ Found {report['total_issues']} data integrity issues requiring attention"
                )

            # Add performance recommendations
            if report["expired_sessions"] > 10:
                report["recommendations"].append(
                    "Consider running cleanup_expired_sessions() to improve performance"
                )

            if report["duplicate_choices"] > 0:
                report["recommendations"].append(
                    "Run database optimization to merge duplicate choices"
                )

            if report["conflicting_choices"] > 5:
                report["recommendations"].append(
                    "Review conflict resolution settings and resolve pending conflicts"
                )

            logger.info(
                f"Data integrity validation completed: {report['total_issues']} issues found"
            )

        except Exception as e:
            logger.error(f"Error during data integrity check: {e}")
            report["recommendations"].append(f"❌ Error during validation: {e}")
            report["total_issues"] = -1  # Indicate validation failure

        return report

    def _check_orphaned_contexts(self) -> list[str]:
        """Check for orphaned contexts (contexts without corresponding choices)."""
        try:
            # Get all context hashes from the database
            all_contexts = self.db.get_all_context_hashes()
            orphaned_contexts = []

            # Check each context to see if it has at least one choice
            for context_hash in all_contexts:
                choices_with_context = self.db.get_choices_by_context_hash(context_hash)
                if not choices_with_context:
                    orphaned_contexts.append(context_hash)

            return orphaned_contexts
        except Exception as e:
            logger.error(f"Error checking orphaned contexts: {e}")
            return []

    def _check_missing_choice_references(self) -> list[str]:
        """Check for choices referencing non-existent sessions."""
        try:
            missing_references = []

            # Get all choices that have session references
            all_choices = self.db.get_all_choices()

            # Check each choice's session reference
            for choice in all_choices:
                if choice.session_id:
                    session = self.db.get_session(choice.session_id)
                    if not session:
                        missing_references.append(choice.choice_id)

            return missing_references
        except Exception as e:
            logger.error(f"Error checking missing choice references: {e}")
            return []

    def _check_invalid_sessions(self) -> list[str]:
        """Check for sessions with invalid states."""
        try:
            invalid_sessions = []

            # Get all sessions
            all_sessions = self.db.get_all_sessions()

            for session in all_sessions:
                # Check for invalid session states
                is_invalid = False

                # Check 1: Session has no choices but is marked as completed
                if session.status == SessionStatus.COMPLETED:
                    session_choices = self.db.get_choices_by_session(session.session_id)
                    if not session_choices:
                        is_invalid = True

                # Check 2: Session has inconsistent timestamps
                if session.completed_at and session.created_at:
                    try:
                        created = datetime.fromisoformat(session.created_at)
                        completed = datetime.fromisoformat(session.completed_at)
                        if completed < created:
                            is_invalid = True
                    except ValueError:
                        is_invalid = True

                # Check 3: Session has invalid choice counts
                if session.total_choices < 0:
                    is_invalid = True

                if is_invalid:
                    invalid_sessions.append(session.session_id)

            return invalid_sessions
        except Exception as e:
            logger.error(f"Error checking invalid sessions: {e}")
            return []

    def _check_duplicate_choices(self) -> list[tuple[str, str]]:
        """Check for duplicate choices (same term + context hash)."""
        try:
            duplicates = []

            # Get all choices grouped by term
            all_choices = self.db.get_all_choices()
            term_groups = {}

            # Group choices by term
            for choice in all_choices:
                if choice.neologism_term not in term_groups:
                    term_groups[choice.neologism_term] = []
                term_groups[choice.neologism_term].append(choice)

            # Check for duplicates within each term group
            for term, choices in term_groups.items():
                if len(choices) > 1:
                    # Check for same context hash
                    context_hashes = {}
                    for choice in choices:
                        context_hash = choice.context.generate_context_hash()
                        if context_hash not in context_hashes:
                            context_hashes[context_hash] = []
                        context_hashes[context_hash].append(choice.choice_id)

                    # Report duplicates
                    for context_hash, choice_ids in context_hashes.items():
                        if len(choice_ids) > 1:
                            duplicates.append((term, context_hash))

            return duplicates
        except Exception as e:
            logger.error(f"Error checking duplicate choices: {e}")
            return []

    def _check_conflicting_choices(self) -> list[str]:
        """Check for conflicting choices (same term, different translations)."""
        try:
            conflicts = []

            # Get all choices grouped by term
            all_choices = self.db.get_all_choices()
            term_groups = {}

            # Group choices by term
            for choice in all_choices:
                if choice.neologism_term not in term_groups:
                    term_groups[choice.neologism_term] = []
                term_groups[choice.neologism_term].append(choice)

            # Check for conflicts within each term group
            for term, choices in term_groups.items():
                if len(choices) > 1:
                    # Check for different translations with similar contexts
                    for i, choice1 in enumerate(choices):
                        for choice2 in choices[i + 1 :]:
                            # Check if contexts are similar but translations differ
                            similarity = choice1.context.calculate_similarity(
                                choice2.context
                            )
                            if (
                                similarity > 0.7
                                and choice1.choice_type == ChoiceType.TRANSLATE
                                and choice2.choice_type == ChoiceType.TRANSLATE
                                and choice1.translation_result
                                != choice2.translation_result
                            ):
                                conflicts.append(term)
                                break

            return list(set(conflicts))  # Remove duplicates
        except Exception as e:
            logger.error(f"Error checking conflicting choices: {e}")
            return []

    def _check_expired_sessions(self) -> list[str]:
        """Check for expired sessions that should be cleaned up."""
        try:
            expired_sessions = []
            current_time = datetime.now()

            # Get all active sessions
            all_sessions = self.db.get_all_sessions()

            for session in all_sessions:
                if session.status == SessionStatus.ACTIVE:
                    try:
                        created_time = datetime.fromisoformat(session.created_at)
                        hours_since_created = (
                            current_time - created_time
                        ).total_seconds() / 3600

                        if hours_since_created > self.session_expiry_hours:
                            expired_sessions.append(session.session_id)
                    except (ValueError, TypeError):
                        # Invalid timestamp - consider it expired
                        expired_sessions.append(session.session_id)

            return expired_sessions
        except Exception as e:
            logger.error(f"Error checking expired sessions: {e}")
            return []

    def optimize_database(self) -> bool:
        """Optimize database performance."""
        try:
            # This would run VACUUM and other optimization commands
            # For now, just cleanup expired sessions
            self.cleanup_expired_sessions()
            logger.info("Database optimization completed")
            return True
        except Exception as e:
            logger.error(f"Database optimization failed: {e}")
            return False

    def get_recommendation_for_neologism(
        self, neologism: DetectedNeologism, session_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Get comprehensive recommendation for handling a neologism.

        Args:
            neologism: The detected neologism
            session_id: Current session ID

        Returns:
            Dictionary with recommendation details
        """
        recommendation = {
            "term": neologism.term,
            "confidence": neologism.confidence,
            "suggested_action": "review",
            "existing_choice": None,
            "similar_choices": [],
            "context_matches": [],
            "reasons": [],
        }

        # Check for existing choice
        existing_choice = self.get_choice_for_neologism(neologism, session_id)
        if existing_choice:
            recommendation["existing_choice"] = {
                "choice_type": existing_choice.choice_type.value,
                "translation": existing_choice.translation_result,
                "confidence": existing_choice.confidence_level,
                "success_rate": existing_choice.success_rate,
                "usage_count": existing_choice.usage_count,
            }

            if existing_choice.success_rate > 0.8:
                recommendation["suggested_action"] = "apply_existing"
                recommendation["reasons"].append(
                    f"High success rate choice available ({existing_choice.success_rate:.1%})"
                )
            else:
                recommendation["suggested_action"] = "review_existing"
                recommendation["reasons"].append(
                    f"Existing choice has moderate success rate ({existing_choice.success_rate:.1%})"
                )

        # Find similar context choices
        context = self._create_context_from_neologism(neologism)
        similar_choices = self.find_similar_contexts(context, similarity_threshold=0.6)

        if similar_choices:
            recommendation["similar_choices"] = [
                {
                    "term": choice.neologism_term,
                    "choice_type": choice.choice_type.value,
                    "translation": choice.translation_result,
                    "similarity": context.calculate_similarity(choice.context),
                }
                for choice in similar_choices[:5]  # Top 5 similar choices
            ]

            if not existing_choice:
                recommendation["suggested_action"] = "consider_similar"
                recommendation["reasons"].append(
                    f"Found {len(similar_choices)} similar context choices"
                )

        # Base recommendations on neologism confidence
        if neologism.confidence > 0.8:
            recommendation["reasons"].append("High confidence neologism detection")
        elif neologism.confidence < 0.5:
            recommendation["reasons"].append(
                "Low confidence detection - may not be a neologism"
            )
            recommendation["suggested_action"] = "skip_low_confidence"

        # Add contextual information
        if neologism.philosophical_context.philosophical_density > 0.7:
            recommendation["reasons"].append("High philosophical density in context")

        if neologism.morphological_analysis.is_compound:
            recommendation["reasons"].append("Compound word structure detected")

        return recommendation


# Convenience functions for integration

# NOTE: create_session_for_document has been moved to core.dynamic_choice_engine
# for API consolidation. Import from there for unified API access:
#   from core.dynamic_choice_engine import create_session_for_document


def create_choice_manager(db_path: str = "user_choices.db") -> UserChoiceManager:
    """Create a UserChoiceManager instance."""
    return UserChoiceManager(db_path)


def process_neologism_analysis(
    manager: UserChoiceManager,
    analysis: NeologismAnalysis,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Process a neologism analysis with the choice manager."""
    return manager.apply_choices_to_analysis(analysis, session_id)
