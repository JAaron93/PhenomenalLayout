#!/bin/bash
# update-deps.sh - Update runtime dependencies via uv (requirements.in -> requirements.txt)
# Usage: ./scripts/update-deps.sh

set -euo pipefail

echo "📦 Updating PhenomenalLayout dependencies..."
echo "============================================="

# Ensure we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "❌ Error: Please activate your virtual environment first"
    echo "   Run: source .venv/bin/activate"
    exit 1
fi

# Ensure uv is available (requirements.txt is a uv pip compile artifact)
if ! command -v uv &> /dev/null; then
    echo "❌ Error: uv is not installed"
    echo "   Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo ""
echo "🔄 Updating runtime dependencies..."
# --upgrade is mandatory: without it, uv pins resolver preference to the
# versions installed in the active venv and silently reproduces the stale lock.
uv pip compile requirements.in -o requirements.txt --upgrade

echo ""
echo "🔄 Updating development dependencies..."
# Compiled against the freshly updated runtime closure so transitive pins
# shared between the tiers stay on the same versions — pip-sync merges both
# manifests and rejects conflicting pins for one package.
uv pip compile requirements-dev.in --constraint requirements.txt -o requirements-dev.txt --upgrade

echo ""
echo "📋 Summary of changes:"
echo "  - requirements.txt: Updated from requirements.in"
echo "  - requirements-dev.txt: Updated from requirements-dev.in (constrained by requirements.txt)"
echo ""
echo "🎯 Next steps:"
echo "  1. Review the updated requirements.txt and requirements-dev.txt"
echo "  2. Run: ./scripts/sync-deps.sh dev (or: pip-sync requirements.txt requirements-dev.txt)"
echo "  3. Test that everything works: python -c 'import app; print(\"✅ OK\")'"

echo ""
echo "✅ Dependency update complete!"
