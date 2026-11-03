#!/usr/bin/env python3
"""Simple test runner to check if imports work.

This script tests basic imports and functionality of the project modules.

Setup:
    For proper operation, ensure the project is installed in editable mode:
    $ pip install -e .

    Alternatively, set PYTHONPATH in your environment:
    $ export PYTHONPATH="${PYTHONPATH}:$(pwd)"
    $ python run_single_test.py

    Or run with PYTHONPATH inline:
    $ PYTHONPATH=. python run_single_test.py
"""

import sys


def test_basic_imports():
    """Verify core user-choice models import and instantiate.

    Raises:
        Exception: Re-raises any import or instantiation failure so pytest
            records a failure (tests must not return a value).
    """
    # Test models import
    from models.user_choice_models import (
        ChoiceScope,
        ChoiceType,
        TranslationContext,
        UserChoice,
    )

    print("✓ Successfully imported user choice models")

    # Test database import

    print("✓ Successfully imported choice database")

    # Test a simple model creation
    context = TranslationContext(
        sentence_context="Test sentence",
        semantic_field="test",
        philosophical_domain="test",
        author="test",
        source_language="en",
        target_language="de",
    )
    print("✓ Successfully created TranslationContext")

    # Test choice creation
    UserChoice(
        choice_id="test_id",
        neologism_term="test_term",
        choice_type=ChoiceType.TRANSLATE,
        choice_scope=ChoiceScope.SESSION,
        context=context,
        translation_result="test_translation",
    )
    print("✓ Successfully created UserChoice")


if __name__ == "__main__":
    print("🧪 Running basic import tests...")
    try:
        test_basic_imports()
    except Exception:
        import traceback

        traceback.print_exc()
        print("❌ Import tests failed!")
        sys.exit(1)
    else:
        print("✅ All import tests passed!")
        sys.exit(0)
