# Scripts Directory

Dolphin OCR Translate is a toolkit for OCR-based multilingual translation of scanned documents with advanced formatting preservation and philosophy-enhanced neologism detection.

This directory contains utility scripts, test runners, and debugging tools for Dolphin OCR Translate.

## Test Scripts

### `simple_test_runner.py`
Lightweight test runner that doesn't require pytest. Runs basic functionality tests for core components.

**Usage:**
```bash
python scripts/simple_test_runner.py
```

### `run_single_test.py`
Basic import test runner that validates core module imports and functionality.
Tests basic imports and model creation to ensure the project is properly configured.

**Features:**
- Tests import of user-chosen models and database components
- Validates model creation and basic functionality
- Provides clear success/failure feedback for debugging setup issues
- Useful for verifying project installation and PYTHONPATH configuration

**Usage:**
```bash
# Basic import test
python scripts/run_single_test.py

# With explicit PYTHONPATH (if not installed in editable mode)
PYTHONPATH=. python scripts/run_single_test.py
```

**Note:** This script tests basic imports rather than running arbitrary test files.
For running specific test files or functions, use pytest directly:
```bash
# Run specific test file
pytest tests/test_core.py

# Run specific test function
pytest tests/test_core.py::TestFoo::test_bar
```

### `run_tests_with_env.py`
Test runner that sets up environment variables before running tests.

**Usage:**
```bash
python scripts/run_tests_with_env.py
```

## Debug Scripts

### `debug_candidates.py`
Debug script for neologism candidate detection using public NeologismDetector API.
Helps troubleshoot the neologism detection engine with safe, maintainable access to candidate extraction.

**Features:**
- Uses public `debug_extract_candidates()` method instead of private APIs
- Robust error handling and graceful degradation
- Detailed candidate information including position and context
- Safe access to internal candidate extraction logic

**Improvements:**
- Enhanced error handling for missing methods or API changes
- Better output formatting with candidate context information
- Maintainable code that won't break with internal API changes

**Usage:**
```bash
python scripts/debug_candidates.py
```

**Output includes:**
- Manual regex pattern testing for debugging
- Candidate extraction results with positions and context
- Error handling for API compatibility issues

### `debug_compound.py`
Comprehensive debug script for compound word analysis using public NeologismDetector API.
Provides detailed analysis of morphological structure, philosophical context, and confidence factors.

**Features:**
- Uses only public APIs (no internal structure access)
- Configurable test words via JSON configuration
- Command line argument support
- Detailed and compact output modes
- Category filtering (compound_words, simple_words, neologisms)
- Graceful error handling

**Usage:**
```bash
# Default analysis with all configured words
python scripts/debug_compound.py

# Analyze specific words
python scripts/debug_compound.py --words Bewusstsein Weltanschauung

# Filter by category
python scripts/debug_compound.py --category compound_words

# Compact output
python scripts/debug_compound.py --compact

# Custom configuration file
python scripts/debug_compound.py --config custom_words.json
```

**Configuration:**
Test words are loaded from `config/debug_test_words.json` and include:
- Compound words with morphological complexity
- Simple philosophical terms
- Known neologisms with context
- Descriptions and example contexts for each word

### `debug_keywords.py`
Debug script for keyword extraction and philosophical term detection.

## Database Scripts

### `test_database_enhancements.py`
Tests database functionality and enhancements for user choice management.

**Features:**
- Comprehensive testing of database enhancements
- Safe temporary file handling with guaranteed cleanup
- Alpha parameter configuration testing
- JSON encoding configuration testing
- Batch import optimization testing
- Backward compatibility verification

**Improvements:**
- Uses context manager for temporary file cleanup
- Ensures files are cleaned up even if exceptions occur
- Prevents temporary file leaks during testing
- Robust error handling for database operations

**Usage:**
```bash
python scripts/test_database_enhancements.py
```

**Tests Included:**
- Alpha parameter configuration and validation
- JSON encoding with international character support
- High-performance batch import functionality
- Backward compatibility with existing code

## Import Testing

### `test_imports.py`
Verifies that all project imports work correctly. Useful after refactoring or moving files.

**Usage:**
```bash
python scripts/test_imports.py
```

## Linting and Code Quality

### `test_linting_setup.py`
Tests the linting configuration and code quality setup with intentional formatting issues.

**Features:**
- Comprehensive test file for Black and Ruff linting validation
- Contains intentional code quality issues for testing linters
- Validates that linting tools properly detect and flag issues
- Tests various Python constructs and formatting problems

**Intentional Issues Included:**
- Inconsistent indentation (6 vs 8 spaces)
- Long lines exceeding 88 characters
- Unused variables and imports
- Deprecated syntax patterns
- Poor spacing and formatting
- Complex conditionals that can be simplified
- Mutable default arguments
- Bare except clauses
- Type comparison issues

**Improvements:**
- Fixed mismatch between comment and actual indentation
- Comment now accurately describes the inconsistent indentation
- Test scenario is now valid and clear for linting validation

**Usage:**
```bash
# Test with Black
black --check scripts/test_linting_setup.py

# Test with Ruff
ruff check scripts/test_linting_setup.py
```

## Basic Testing

### `basic_test.py`
Basic functionality test for core translation features.

## Migration Validation

### `validate_migration.sh`
Shell script to validate file migrations and project structure changes.
Validates the migration from Flake8 to Black + Ruff tooling.

**Features:**
- Validates Black and Ruff installation and configuration
- Validates Black and Ruff setup and formatting
- Tests code formatting and linting on project files
- Provides detailed reporting of any issues found
- Robust error handling with proper shell syntax

**Improvements:**
- Fixed missing `fi` terminators in nested if statements
- Proper shell script syntax for reliable execution
- Enhanced error reporting and validation logic

**Usage:**
```bash
bash scripts/validate_migration.sh
```

**Output includes:**
- Tool installation verification
- Code formatting and linting results
- Summary of migration validation status

## Running Scripts

All scripts should be run from the project root directory:

```bash
# From project root
python scripts/<script_name>.py
```

Or for shell scripts:

```bash
# From project root
bash scripts/<script_name>.sh
```

## Notes

- These scripts are development utilities and are not part of the main application
- Some scripts may require specific environment variables to be set
- Debug scripts are primarily for development and troubleshooting
- Test scripts provide alternative testing methods to the main test suite
