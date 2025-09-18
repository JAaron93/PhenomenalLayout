#!/bin/bash
# update-deps.sh - Update all dependencies using pip-tools
# Usage: ./scripts/update-deps.sh

set -e

echo "📦 Updating PhenomenalLayout dependencies..."
echo "============================================="

# Ensure we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "❌ Error: Please activate your virtual environment first"
    echo "   Run: source .venv/bin/activate"
    exit 1
fi

# Ensure pip-tools is installed
if ! command -v pip-compile &> /dev/null; then
    echo "📥 Installing pip-tools..."
    pip install pip-tools
fi

echo ""
echo "🔄 Updating runtime dependencies..."
pip-compile requirements.in --upgrade --strip-extras

echo ""
echo "🔄 Updating development dependencies..."
pip-compile dev-requirements.in --upgrade --strip-extras

echo ""
echo "📋 Summary of changes:"
echo "  - requirements.txt: Updated from requirements.in"
echo "  - dev-requirements.txt: Updated from dev-requirements.in"

echo ""
echo "🎯 Next steps:"
echo "  1. Review the updated .txt files"
echo "  2. Run: pip-sync dev-requirements.txt"
echo "  3. Test that everything works: python -c 'import app; print(\"✅ OK\")'"

echo ""
echo "✅ Dependency update complete!"
