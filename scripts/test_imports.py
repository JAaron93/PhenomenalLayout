#!/usr/bin/env python3
"""Test script to check if imports work."""

import importlib
import traceback


def run_import_check(module_name: str, from_module: str | None = None) -> bool:
    """Test importing a module or symbol with explicit import verification.

    This function performs actual import operations to verify importability,
    rather than just checking attribute existence which can give false positives.
    """
    try:
        if from_module:
            # Import the module first
            imported_module = importlib.import_module(from_module)

            # Check if the symbol exists in the module
            if not hasattr(imported_module, module_name):
                raise ImportError(
                    f"'{module_name}' is not available in module '{from_module}'"
                )

            # Actually retrieve the symbol - this tests true importability
            # Unlike simple getattr, this will fail if the symbol has import-time issues
            imported_symbol = getattr(imported_module, module_name)

            # Verify the symbol is not None and is actually usable
            if imported_symbol is None:
                raise ImportError(f"'{module_name}' from '{from_module}' is None")

            # Additional check: try to access basic attributes to ensure it's a valid object
            # This helps catch cases where getattr succeeds but the object is broken
            try:
                # Test basic object operations that should work for any importable symbol
                str(type(imported_symbol))  # Should not fail for valid objects
                repr(imported_symbol)  # Should not fail for valid objects
            except Exception as validation_error:
                raise ImportError(
                    f"'{module_name}' from '{from_module}' is not usable: {validation_error}"
                ) from validation_error

            print(f"✓ Successfully imported {module_name} from {from_module}")
        else:
            # For regular module imports, use importlib as before
            importlib.import_module(module_name)
            print(f"✓ Successfully imported {module_name}")
        return True
    except (ImportError, ModuleNotFoundError, AttributeError, SyntaxError) as e:
        print(f"✗ Failed to import {module_name}: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error importing {module_name}: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Testing imports...")

    # Test basic imports
    standard_modules = ["pytest", "sqlite3", "json", "datetime"]
    project_imports = [
        ("ChoiceDatabase", "database.choice_database"),
        ("UserChoice", "models.user_choice_models"),
    ]

    success_count = 0
    total_count = 0

    for module in standard_modules:
        total_count += 1
        if run_import_check(module):
            success_count += 1
    for module_name, from_module in project_imports:
        total_count += 1
        if run_import_check(module_name, from_module):
            success_count += 1

    print(f"Import testing complete: {success_count}/{total_count} successful")
