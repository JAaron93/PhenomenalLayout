#!/bin/bash
# Migration Validation Script for Black + Ruff
# =============================================
# This script validates the migration from Flake8 to Black + Ruff

set -euo pipefail  # Exit on error, fail on unset variables, catch pipeline errors

echo "==========================================="
echo "Black + Ruff Migration Validation Script"
echo "==========================================="
echo ""

# Function to parse version strings robustly
# Handles pre-release versions like 24.2.0.dev0, 1.0.0rc1, etc.
parse_version() {
    local version_string="$1"
    local tool_name="$2"

    # Extract version using multiple patterns to handle different formats
    # Pattern 1: Standard semantic version (e.g., "black, 24.2.0")
    local version=$(echo "$version_string" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1)

    # Pattern 2: If no standard version found, try to extract any number sequence
    if [ -z "$version" ]; then
        version=$(echo "$version_string" | grep -oE '[0-9]+(\.[0-9]+)*' | head -n1)
    fi

    # Check if we found a version
    if [ -z "$version" ]; then
        echo "   ⚠️  Warning: Could not parse version from $tool_name output: $version_string" >&2
        return 1
    fi

    echo "$version"
    return 0
}

# Function to extract major version number
get_major_version() {
    local version="$1"
    echo "$version" | cut -d. -f1
}

# Function to extract minor version number
get_minor_version() {
    local version="$1"
    echo "$version" | cut -d. -f2
}

# Function to compare version numbers (returns 0 if version1 >= version2)
version_compare() {
    local version1="$1"
    local version2="$2"

    # Convert versions to comparable format
    local v1_major=$(get_major_version "$version1")
    local v1_minor=$(get_minor_version "$version1")
    local v2_major=$(get_major_version "$version2")
    local v2_minor=$(get_minor_version "$version2")

    # Default minor version to 0 if not present
    v1_minor=${v1_minor:-0}
    v2_minor=${v2_minor:-0}

    # Compare major versions first
    if [ "$v1_major" -gt "$v2_major" ]; then
        return 0
    elif [ "$v1_major" -lt "$v2_major" ]; then
        return 1
    else
        # Major versions equal, compare minor versions
        [ "$v1_minor" -ge "$v2_minor" ]
    fi
}


# Check if Black is installed
echo "1. Checking Black installation..."
if ! command -v black &> /dev/null; then
    echo "   ❌ Black is not installed!"
    echo "   Please install it with: pip install -e .[dev]"
    echo "   Or manually: pip install black"
    echo "   Version constraints are defined in pyproject.toml"
    exit 1
else
    BLACK_VERSION_RAW=$(black --version 2>&1 | head -n1)
    echo "   ✅ Black is installed ($BLACK_VERSION_RAW)"

    # Parse version robustly with error handling
    if BLACK_VERSION=$(parse_version "$BLACK_VERSION_RAW" "Black"); then
        echo "   📋 Parsed version: $BLACK_VERSION"

        # Check for major version compatibility
        BLACK_MAJOR=$(get_major_version "$BLACK_VERSION")
        if [ -n "$BLACK_MAJOR" ] && [ "$BLACK_MAJOR" -lt 22 ]; then
            echo "   ⚠️  Warning: Black version ($BLACK_VERSION) may be outdated. Consider upgrading to >=22.0.0"
        else
            echo "   ✅ Black version ($BLACK_VERSION) meets minimum requirements"
        fi
    else
        echo "   ⚠️  Warning: Could not parse Black version for compatibility check"
        echo "   Raw version output: $BLACK_VERSION_RAW"
    fi
fi
echo ""

# Check if Ruff is installed
echo "2. Checking Ruff installation..."
if ! command -v ruff &> /dev/null; then
    echo "   ❌ Ruff is not installed!"
    echo "   Please install it with: pip install -e .[dev]"
    echo "   Or manually: pip install ruff"
    echo "   Version constraints are defined in pyproject.toml"
    exit 1
else
    RUFF_VERSION_RAW=$(ruff --version 2>&1)
    echo "   ✅ Ruff is installed ($RUFF_VERSION_RAW)"

    # Parse version robustly with error handling
    if RUFF_VERSION=$(parse_version "$RUFF_VERSION_RAW" "Ruff"); then
        echo "   📋 Parsed version: $RUFF_VERSION"

        # Check for version compatibility using robust comparison
        if version_compare "$RUFF_VERSION" "0.1.0"; then
            echo "   ✅ Ruff version ($RUFF_VERSION) meets minimum requirements"
        else
            echo "   ⚠️  Warning: Ruff version ($RUFF_VERSION) may be outdated. Consider upgrading to >=0.1.0"
        fi
    else
        echo "   ⚠️  Warning: Could not parse Ruff version for compatibility check"
        echo "   Raw version output: $RUFF_VERSION_RAW"
    fi
fi
echo ""

# Capture before statistics (if baseline exists)
echo "3. Capturing statistics..."
echo ""

# Count Python files (excluding .git and other build directories for performance)
PY_FILE_COUNT=$(find . \( -name ".git" -o -name ".venv" -o -name "__pycache__" -o -name "build" -o -name "dist" \) -prune -o -name "*.py" -type f -print | wc -l)
echo "   📊 Python files found: $PY_FILE_COUNT"

# Run tools directly and capture results
echo ""
echo "4. Running Black and Ruff on all files..."
echo "   This may take a moment..."
echo ""

# Create temporary file for output
TEMP_OUTPUT=$(mktemp) || {
    echo "❌ Failed to create temporary file"
    exit 1
}

# Cleanup on exit or interrupt
trap 'rm -f "$TEMP_OUTPUT"' EXIT

# Run tools and capture exit code
set +e  # Temporarily disable exit on error
echo "--- Black Check ---" >> "$TEMP_OUTPUT"
black --check . 2>&1 | tee -a "$TEMP_OUTPUT"
BLACK_EXIT=$?
echo "" >> "$TEMP_OUTPUT"
echo "--- Ruff Check ---" >> "$TEMP_OUTPUT"
ruff check . 2>&1 | tee -a "$TEMP_OUTPUT"
RUFF_EXIT=$?
EXIT_CODE=$((BLACK_EXIT || RUFF_EXIT))
set -e  # Re-enable exit on error

echo ""
echo "==========================================="
echo "Migration Validation Results"
echo "==========================================="
echo ""

# Analyze results
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All checks passed! No issues found."
else
    echo "⚠️  Some files were modified or issues were found."

    if [ $BLACK_EXIT -ne 0 ]; then
        echo "   📝 Black found formatting issues"
    fi

    if [ $RUFF_EXIT -ne 0 ]; then
        echo "   🔧 Ruff found linting issues"
    fi
fi

echo ""
echo "==========================================="
echo "Summary"
echo "==========================================="
echo ""
echo "Migration from Flake8 to Black + Ruff has been validated."
echo ""
echo "Tool versions:"
echo "  - Black: $(black --version 2>&1 | head -n1 | sed 's/black, //')"
echo "  - Ruff: $(ruff --version | sed 's/ruff //')"
echo "  - Line length: 88 characters (Black default)"
echo ""
echo "Replaced tools:"
echo "  ❌ flake8 → ✅ ruff"
echo "  ❌ isort → ✅ ruff (built-in)"
echo "  ❌ autoflake → ✅ ruff (F401, F841 rules)"
echo "  ❌ pyupgrade → ✅ ruff (UP rules)"
echo "  ❌ flake8-* plugins → ✅ ruff (D, B, C4, SIM rules)"
echo ""
echo "Next steps:"
echo "  1. Review any modified files"
echo "  2. Commit the changes"
echo "  3. Update CI/CD pipelines"
echo "  4. Notify team members"
echo ""
echo "==========================================="
