#!/bin/bash
# sync-deps.sh - Sync virtual environment with pinned dependencies
# Usage: ./scripts/sync-deps.sh [dev|prod]

set -e

MODE="${1:-dev}"

echo "🔄 Syncing PhenomenalLayout dependencies ($MODE mode)..."
echo "======================================================"

# Ensure we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "❌ Error: Please activate your virtual environment first"
    echo "   Run: source .venv/bin/activate"
    exit 1
fi

# Ensure pip-tools is installed
if ! command -v pip-sync &> /dev/null; then
    echo "📥 Installing pip-tools..."
    pip install pip-tools
fi

echo ""
if [[ "$MODE" == "prod" ]]; then
    echo "⚙️  Production mode: Installing runtime dependencies only..."
    pip-sync requirements.txt
    echo "✅ Production dependencies synced!"
else
    echo "⚙️  Development mode: Installing all dependencies..."
    pip-sync dev-requirements.txt
    echo "✅ Development dependencies synced!"
fi

echo ""
echo "📊 Environment status:"
python -c "
import sys
print(f'  Python: {sys.version.split()[0]}')
import pip
try:
    import modal, fastapi, gradio
    print('  ✅ Core packages: OK')
except ImportError as e:
    print(f'  ❌ Import error: {e}')
"

echo ""
echo "🎯 Ready for development!"
