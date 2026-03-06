#!/usr/bin/env python3
"""Example demonstrating flexible project root validation.

This script shows different ways to configure and use the flexible
project validation system introduced in debug_candidates.py.
"""

import json
import os
import sys
from pathlib import Path


def find_project_root(start_path: Path | None = None, max_depth: int = 10) -> Path:
    """Find the project root by searching upward for known indicators.

    Args:
        start_path: Optional starting path for the search.
            If ``None`` (default), the search starts at the current script location.
        max_depth: Maximum number of parent directories to search

    Returns:
        Path to project root

    Raises:
        RuntimeError: If project root cannot be found
    """
    if start_path is None:
        start_path = Path(__file__).resolve()

    # Project root indicators (in order of preference)
    # Use combinations to ensure we find the actual project root, not subdirectories
    primary_indicators = [
        "pyproject.toml",  # Python project configuration
        "setup.py",  # Python package setup
    ]

    secondary_indicators = [
        "app.py",  # Main application file
        "requirements.txt",  # Python dependencies
        "Pipfile",  # Pipenv configuration
        "poetry.lock",  # Poetry lock file
    ]

    tertiary_indicators = [
        ".git",  # Git repository (strong but can be in subdirs)
        ".gitignore",  # Git ignore file
    ]

    # Weak indicators (only use if combined with others or as last resort)
    weak_indicators = [
        "README.md",  # Project documentation (can be in subdirs)
        "README.rst",  # Alternative documentation
    ]

    current_path = start_path if start_path.is_dir() else start_path.parent

    for _ in range(max_depth):
        # Check for primary indicators first (strongest signals)
        for indicator in primary_indicators:
            indicator_path = current_path / indicator
            if indicator_path.exists():
                print(f"📍 Found project root at: {current_path}")
                print(f"   Primary indicator: {indicator}")
                return current_path

        # Check for secondary indicators
        for indicator in secondary_indicators:
            indicator_path = current_path / indicator
            if indicator_path.exists():
                print(f"📍 Found project root at: {current_path}")
                print(f"   Secondary indicator: {indicator}")
                return current_path

        # Check for tertiary indicators
        for indicator in tertiary_indicators:
            indicator_path = current_path / indicator
            if indicator_path.exists():
                print(f"📍 Found project root at: {current_path}")
                print(f"   Tertiary indicator: {indicator}")
                return current_path

        # Move up one directory
        parent = current_path.parent
        if parent == current_path:  # Reached filesystem root
            break
        current_path = parent

    # If no strong indicators found, try weak indicators as last resort
    current_path = start_path if start_path.is_dir() else start_path.parent
    for _ in range(max_depth):
        for indicator in weak_indicators:
            indicator_path = current_path / indicator
            if indicator_path.exists():
                print(f"📍 Found project root at: {current_path}")
                print(f"   Weak indicator: {indicator} (may not be accurate)")
                return current_path

        parent = current_path.parent
        if parent == current_path:
            break
        current_path = parent

    # Fallback: use the original fragile method with warning
    fallback_root = Path(__file__).parent.parent
    print("⚠️  Warning: Could not find project root indicators")
    print(f"   Using fallback method: {fallback_root}")
    print("   This may not work if script is moved to different location")
    return fallback_root


def add_project_root_to_path(project_root: Path | None = None) -> Path:
    """Add project root to sys.path safely.

    Args:
        project_root: Optional project root path.
            If ``None`` (default), the root is auto-detected.

    Returns:
        The project root path that was added
    """
    if project_root is None:
        project_root = find_project_root()

    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        # Add at end to avoid overriding system packages
        sys.path.append(project_root_str)
        print(f"✅ Added to sys.path: {project_root_str}")
    else:
        print(f"📋 Already in sys.path: {project_root_str}")

    return project_root


def example_default_validation(find_and_validate_project_root):
    """Example 1: Use default validation (backward compatible)."""
    print("=== Example 1: Default Validation ===")
    try:
        project_root = find_and_validate_project_root()
        print(f"✓ Project root found: {project_root}")
        return project_root
    except RuntimeError as e:
        print(f"❌ Validation failed: {e}")
        return None


def example_custom_parameters(find_and_validate_project_root):
    """Example 2: Use custom validation parameters."""
    print("\n=== Example 2: Custom Parameters ===")
    try:
        # Minimal validation - only check for essential directories
        project_root = find_and_validate_project_root(
            expected_dirs=["services", "models"],
            expected_files=["app.py"],
            critical_files=["services/neologism_detector.py"],
            strict_validation=False,  # Only warn, don't fail
        )
        print(f"✓ Project root found with custom validation: {project_root}")
        return project_root
    except RuntimeError as e:
        print(f"❌ Custom validation failed: {e}")
        return None


def create_sample_config_safely(config_file: Path) -> bool:
    """Create a sample config file with proper error handling and overwrite protection.

    Args:
        config_file: Path where the config file should be created

    Returns:
        True if config was created successfully, False otherwise
    """
    # Check if file already exists and warn user
    if config_file.exists():
        print(f"⚠️  Config file already exists: {config_file}")
        print("   To prevent accidental data loss, please:")
        print("   1. Review the existing file")
        print("   2. Delete it manually if you want to recreate it")
        print("   3. Or modify the existing file as needed")
        return False

    print(f"📝 Creating sample config file: {config_file}")

    # Create a sample config
    sample_config = {
        "expected_dirs": ["services", "models", "scripts"],
        "expected_files": ["app.py", "requirements.txt"],
        "critical_files": ["services/neologism_detector.py"],
    }

    try:
        # Ensure the parent directory exists
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the config file with proper error handling
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(sample_config, f, indent=2, ensure_ascii=False)
        print(f"✓ Successfully created sample config: {config_file}")
        return True

    except PermissionError as e:
        print(f"❌ Permission denied creating config file: {e}")
        print(f"   Please check write permissions for: {config_file.parent}")
        return False
    except OSError as e:
        print(f"❌ OS error creating config file: {e}")
        print(f"   Please check disk space and path validity: {config_file}")
        return False
    except (TypeError, ValueError) as e:
        print(f"❌ Error serializing config data: {e}")
        print("   This indicates a problem with the sample config structure")
        return False


def example_config_file(find_and_validate_project_root):
    """Example 3: Use configuration file."""
    print("\n=== Example 3: Configuration File ===")
    # Use the injected project root finder to get the project root
    current_project_root = find_and_validate_project_root()
    config_file = current_project_root / "scripts" / "project_validation_config.json"

    if not config_file.exists():
        print(f"⚠️  Config file not found: {config_file}")

        # Try to create a sample config file safely
        if not create_sample_config_safely(config_file):
            print("❌ Could not create sample config file")
            return None
    else:
        print(f"📋 Using existing config file: {config_file}")

    try:
        project_root = find_and_validate_project_root(config_path=config_file)
        print(f"✓ Project root found using config file: {project_root}")
        return project_root
    except RuntimeError as e:
        print(f"❌ Config file validation failed: {e}")
        return None


def example_environment_variables(
    find_and_validate_project_root, load_project_validation_config
):
    """Example 4: Use environment variables."""
    print("\n=== Example 4: Environment Variables ===")

    # Set environment variables for this example
    os.environ["PROJECT_EXPECTED_DIRS"] = "services,models,scripts"
    os.environ["PROJECT_EXPECTED_FILES"] = "app.py,requirements.txt"
    os.environ["PROJECT_CRITICAL_FILES"] = "services/neologism_detector.py"

    try:
        # Load config from environment
        config = load_project_validation_config()
        print(f"Config loaded from environment: {config}")

        project_root = find_and_validate_project_root()
        print(f"✓ Project root found using environment variables: {project_root}")
        return project_root
    except RuntimeError as e:
        print(f"❌ Environment validation failed: {e}")
        return None
    finally:
        # Clean up environment variables
        for key in [
            "PROJECT_EXPECTED_DIRS",
            "PROJECT_EXPECTED_FILES",
            "PROJECT_CRITICAL_FILES",
        ]:
            os.environ.pop(key, None)


def example_non_strict_validation(find_and_validate_project_root):
    """Example 5: Non-strict validation (warnings only)."""
    print("\n=== Example 5: Non-Strict Validation ===")
    try:
        # This will only warn about missing items instead of failing
        project_root = find_and_validate_project_root(
            expected_dirs=["services", "models", "nonexistent_dir"],
            expected_files=["app.py", "nonexistent_file.txt"],
            critical_files=["services/neologism_detector.py"],
            strict_validation=False,
        )
        print(f"✓ Project root found with warnings: {project_root}")
        return project_root
    except RuntimeError as e:
        print(f"❌ Non-strict validation failed: {e}")
        return None


def main():
    """Run all validation examples."""
    print("Flexible Project Root Validation Examples")
    print("=" * 50)

    # Set up sys.path and import required modules
    print("🔍 Searching for project root...")
    _ = add_project_root_to_path()

    # Import the flexible validation functions after path setup
    from scripts.debug_candidates import (
        find_and_validate_project_root,
        load_project_validation_config,
    )

    examples = [
        (example_default_validation, [find_and_validate_project_root]),
        (example_custom_parameters, [find_and_validate_project_root]),
        (example_config_file, [find_and_validate_project_root]),
        (
            example_environment_variables,
            [find_and_validate_project_root, load_project_validation_config],
        ),
        (example_non_strict_validation, [find_and_validate_project_root]),
    ]

    results = []
    for example_func, args in examples:
        result = example_func(*args)
        results.append(result is not None)

    print("\n=== Summary ===")
    print(f"Examples run: {len(examples)}")
    print(f"Successful: {sum(results)}")
    print(f"Failed: {len(examples) - sum(results)}")

    if all(results):
        print("✓ All validation examples completed successfully!")
    else:
        print("⚠️  Some validation examples failed (this may be expected)")


if __name__ == "__main__":
    main()
