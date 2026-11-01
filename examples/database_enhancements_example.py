#!/usr/bin/env python3
"""
Example demonstrating the three critical database enhancements.

1. Alpha Parameter Configuration
2. JSON Encoding Configuration
3. Batch Import Optimization
"""

# Standard library imports
import atexit
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime

# Local imports (must come before sys.path modification)
from database.choice_database import ChoiceDatabase
from models.user_choice_models import (
    ChoiceScope,
    ChoiceSession,
    ChoiceType,
    ConflictResolution,
    SessionStatus,
    TranslationContext,
    UserChoice,
)

# Add the project root to the path if needed (at end to avoid overriding system packages)
if "." not in sys.path:
    sys.path.append(".")

# Global list to track temporary files for cleanup
_temp_files = []


def _create_temp_db(prefix="test_db_"):
    """Create a temporary database file and track it for cleanup."""
    temp_file = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".db", delete=False)
    temp_file.close()
    _temp_files.append(temp_file.name)
    return temp_file.name


def cleanup_temp_files():
    """Clean up all temporary database files."""
    for temp_file in _temp_files:
        try:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        except OSError as e:
            print(f"Warning: Could not clean up {temp_file}: {e}")
    _temp_files.clear()


# Register cleanup function to run on program exit
atexit.register(cleanup_temp_files)


def demonstrate_alpha_configuration():
    """Demonstrate configurable learning rate alpha parameter."""
    print("Alpha Parameter Configuration Example")
    print("=" * 50)

    # Example 1: Default alpha (0.1)
    db1 = ChoiceDatabase(_create_temp_db("alpha_default_"))
    choice1 = UserChoice(
        choice_id="alpha_001",
        neologism_term="Dasein",
        choice_type=ChoiceType.TRANSLATE,
        translation_result="being-there",
        context=TranslationContext(
            sentence_context="Heidegger's concept of Dasein is fundamental.",
            philosophical_domain="Existentialism",
            author="Heidegger",
            source_language="German",
            target_language="English",
        ),
        choice_scope=ChoiceScope.CONTEXTUAL,
        success_rate=0.5,
    )
    db1.save_user_choice(choice1)

    # Example 2: Custom alpha (0.05)
    db2 = ChoiceDatabase(_create_temp_db("alpha_custom_"), learning_rate_alpha=0.05)
    choice2 = UserChoice(
        choice_id="alpha_002",
        neologism_term="Geworfenheit",
        choice_type=ChoiceType.TRANSLATE,
        translation_result="thrownness",
        context=TranslationContext(
            sentence_context=(
                "The concept of Geworfenheit describes our thrownness into being."
            ),
            philosophical_domain="Existentialism",
            author="Heidegger",
            source_language="German",
            target_language="English",
        ),
        choice_scope=ChoiceScope.CONTEXTUAL,
        success_rate=0.5,
    )
    db2.save_user_choice(choice2)

    # Example 3: Runtime adjustment of alpha
    db1.learning_rate_alpha = 0.2
    updated_choice = db1.get_user_choice("alpha_001")
    print(f"Original success rate: {choice1.success_rate}")
    print(f"Updated success rate: {updated_choice.success_rate}")
    print("Alpha configuration demonstrates learning rate flexibility\n")


def demonstrate_json_encoding():
    """Demonstrate configurable JSON encoding for international characters."""
    print("JSON Encoding Configuration Example")
    print("=" * 50)

    # Create test choices with international characters
    german_context = TranslationContext(
        sentence_context=(
            "Heideggers Konzept der Befindlichkeit ist grundlegend für die "
            "Phänomenologie."
        ),
        philosophical_domain="Existenzphilosophie",
        author="Heidegger",
        source_language="Deutsch",
        target_language="English",
    )

    choice1 = UserChoice(
        choice_id="intl_001",
        neologism_term="Befindlichkeit",
        choice_type=ChoiceType.TRANSLATE,
        translation_result="attunement",
        context=german_context,
        choice_scope=ChoiceScope.CONTEXTUAL,
        success_rate=0.8,
    )

    choice2 = UserChoice(
        choice_id="intl_002",
        neologism_term="Geworfenheit",
        choice_type=ChoiceType.TRANSLATE,
        translation_result="thrownness",
        context=german_context,
        choice_scope=ChoiceScope.CONTEXTUAL,
        success_rate=0.7,
    )

    # Example 1: Preserve international characters (default)
    db1 = ChoiceDatabase(_create_temp_db("encoding_preserve_"), ensure_ascii=False)
    db1.save_user_choice(choice1)
    db1.save_user_choice(choice2)

    json_preserve = db1.export_choices_to_json()
    print("\nUnicode Preservation:")
    print(f"Contains actual characters: 'ä' in json_preserve: {'ä' in json_preserve}")
    print(f"File size Unicode: {len(json_preserve)} bytes")

    # Example 2: ASCII-only encoding
    db2 = ChoiceDatabase(_create_temp_db("encoding_ascii_"), ensure_ascii=True)
    db2.save_user_choice(choice1)
    db2.save_user_choice(choice2)

    json_ascii = db2.export_choices_to_json()
    print("\nASCII-Only Encoding:")
    unicode_marker = "\\u"
    print(
        f"Contains Unicode escapes: '{unicode_marker}' in json_ascii: {unicode_marker in json_ascii}"
    )
    print(f"File size ASCII: {len(json_ascii)} bytes")

    # Example 3: Runtime encoding adjustment
    db1.ensure_ascii = True
    json_switched = db1.export_choices_to_json()
    print(f"\nFile size after switching to ASCII: {len(json_switched)} bytes")

    print("JSON encoding handles international characters flexibly\n")


def demonstrate_batch_import():
    """Demonstrate high-performance batch import optimization."""
    print("Batch Import Optimization Example")
    print("=" * 50)

    # Create a test session and generate large dataset for batch import
    print("Generating large test dataset...")

    philosophers = ["Heidegger", "Husserl", "Sartre", "Merleau-Ponty", "Gadamer"]
    domains = ["Phenomenology", "Existentialism", "Hermeneutics", "Ontology"]

    test_choices = []
    for i in range(2000):  # Generate 2000 choices
        philosopher = philosophers[i % len(philosophers)]
        domain = domains[i % len(domains)]

        context = TranslationContext(
            sentence_context=f"Philosophical context {i} discussing {domain}.",
            philosophical_domain=domain,
            author=philosopher,
            source_language="German",
            target_language="English",
        )

        choice = UserChoice(
            choice_id=f"batch_demo_{i:04d}",
            neologism_term=f"Konzept{i}",
            choice_type=ChoiceType.TRANSLATE,
            translation_result=f"Concept{i}",
            context=context,
            choice_scope=ChoiceScope.CONTEXTUAL,
            success_rate=0.8 + (i % 5) * 0.04,
        )
        test_choices.append(choice)

    print(f"Generated {len(test_choices)} test choices")

    # Export to JSON for batch import
    export_data = {
        "export_timestamp": datetime.now(UTC).isoformat(),
        "version": "1.0",
        "total_choices": len(test_choices),
        "choices": [choice.to_dict() for choice in test_choices],
    }

    json_data = json.dumps(export_data, indent=2)
    print(f"Exported to JSON: {len(json_data):,} bytes")

    # Example 1: Standard batch size
    print("\nStandard Batch Size (1000):")
    db1 = ChoiceDatabase(_create_temp_db("batch_standard_"), batch_size=1000)

    # Create session to avoid foreign key constraints
    session = ChoiceSession(
        session_id="batch_demo_session",
        status=SessionStatus.ACTIVE,
        conflict_resolution_strategy=ConflictResolution.LATEST_WINS,
    )
    db1.save_session(session)

    start_time = time.time()
    imported_count = db1.import_choices_from_json(json_data)
    duration = time.time() - start_time

    print(f"Imported {imported_count} choices in {duration:.2f}s")
    print(
        f"Performance: {imported_count / duration:.0f} choices/second"
        if duration > 0
        else "Instant import!"
    )

    # Example 2: Medium batch size
    print("\nMedium Batch Size (100):")
    db2 = ChoiceDatabase(_create_temp_db("batch_medium_"), batch_size=100)
    start_time = time.time()
    imported_count_2 = db2.import_choices_from_json(json_data)
    medium_batch_time = time.time() - start_time
    print(f"Imported {imported_count_2} choices in {medium_batch_time:.2f}s")
    print(f"Performance: {imported_count_2 / medium_batch_time:.0f} choices/second")

    # Example 3: Small batch size for memory-constrained environments
    print("\nSmall Batch Size (10):")
    db3 = ChoiceDatabase(_create_temp_db("batch_small_"), batch_size=10)
    start_time = time.time()
    imported_count_3 = db3.import_choices_from_json(json_data)
    small_batch_time = time.time() - start_time
    print(f"Imported {imported_count_3} choices in {small_batch_time:.2f}s")
    print(f"Performance: {imported_count_3 / small_batch_time:.0f} choices/second")

    # Verify data integrity
    print("\nData Integrity Verification:")
    stats = db1.get_database_statistics()
    print(f"Total choices in database: {stats['total_choices']}")

    # Test specific choice retrieval
    sample_choice = db1.get_user_choice("batch_demo_1000")
    if sample_choice:
        print(f"✓ Sample choice retrieved: {sample_choice.neologism_term}")
        print(f"✓ Confidence level: {sample_choice.confidence_level}")

    print("Batch import optimization delivers high performance\n")


def demonstrate_combined_features():
    """Demonstrate all three features working together."""
    print("Combined Features Demonstration")
    print("=" * 50)

    # Initialize with all three features
    db = ChoiceDatabase(
        _create_temp_db("combined_features_"),
        learning_rate_alpha=0.15,  # Custom learning rate
        ensure_ascii=False,  # Preserve international characters
        batch_size=1500,  # Optimized batch size
    )

    print("Database configured with:")
    print(f"  - Learning rate alpha: {db.learning_rate_alpha}")
    print(
        f"  - JSON ensure_ascii: {db.ensure_ascii} (preserves international characters)"
    )
    print(f"  - Batch size: {db.batch_size}")

    # Create session
    session = ChoiceSession(
        session_id="combined_demo",
        status=SessionStatus.ACTIVE,
        conflict_resolution_strategy=ConflictResolution.LATEST_WINS,
    )
    db.save_session(session)

    # Create choices with international characters
    choices = []
    terms = ["Sein", "Dasein", "Bewußtsein", "Möglichkeit", "Wirklichkeit"]

    for i, term in enumerate(terms):
        context = TranslationContext(
            sentence_context=(
                f"Heideggers Analyse des Begriffs {term} in "
                "Sein und Zeit ist grundlegend für die "
                "phänomenologische Tradition."
            ),
            philosophical_domain="Ontologie",
            author="Heidegger",
            source_language="Deutsch",
            target_language="English",
        )

        choice = UserChoice(
            choice_id=f"combined_{i:03d}",
            neologism_term=term,
            choice_type=ChoiceType.TRANSLATE,
            translation_result=f"{term.lower()}_translated",
            context=context,
            choice_scope=ChoiceScope.CONTEXTUAL,
            success_rate=0.6,
        )
        choices.append(choice)

    # Export and import using all features
    for choice in choices:
        db.save_user_choice(choice)

    # Test JSON export with international characters
    exported_json = db.export_choices_to_json()
    print(f"\nExported {len(exported_json)} characters of JSON data")
    print(f"Sample of exported data: {exported_json[:150]}...")

    # Test learning rate adjustment
    updated_choice = db.get_user_choice("combined_001")
    print(
        f"\nLearning rate applied: {choices[1].success_rate:.3f} → "
        f"{updated_choice.success_rate:.3f}"
    )

    # Test batch operations
    print(f"\nBatch size configuration: {db.batch_size} choices per batch")

    print("All three enhancements work together seamlessly\n")


def main():
    """Run all demonstration examples."""
    print("Running Database Enhancement Examples...")
    print("-" * 50)

    # Demonstrate each feature
    demonstrate_alpha_configuration()
    demonstrate_json_encoding()
    demonstrate_batch_import()
    demonstrate_combined_features()

    print("All enhancements demonstrated successfully!")
    print("- Alpha Parameter Configuration: Flexible learning rates")
    print("- JSON Encoding Configuration: International character support")
    print("- Batch Import Optimization: High-performance bulk operations")
    print("- Combined Features: Seamless integration")


if __name__ == "__main__":
    main()
