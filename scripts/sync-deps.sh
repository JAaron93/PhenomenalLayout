#!/bin/bash
# sync-deps.sh - Sync virtual environment with pinned dependencies
# Usage: ./scripts/sync-deps.sh [dev|prod]

set -euo pipefail

MODE="${1:-dev}"

echo "🔄 Syncing PhenomenalLayout dependencies ($MODE mode)..."
echo "======================================================"

# Ensure we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "❌ Error: Please activate your virtual environment first"
    echo "   Run: source .venv/bin/activate"
    exit 1
fi

# pip-sync requires every manifest it syncs to be a fully compiled closure:
# its desired state is exactly the set of explicit pins in the files passed
# to it, and it uninstalls every installed distribution that is not itself
# an explicit pin. requirements.txt and requirements-dev.txt are uv-compiled
# closures (sources: requirements.in / requirements-dev.in), so the union
# below is complete and repeat syncs are idempotent. Do NOT pass hand-written
# manifests to pip-sync — their transitive dependencies get orphaned.

# Ensure pip-tools is installed so first-sync bootstrap works on a fresh
# venv (keep this pin in sync with requirements-dev.in).
if ! command -v pip-sync &> /dev/null; then
    echo "📥 Installing pip-tools..."
    python -m pip install "pip-tools==7.6.2"
fi

echo ""
if [[ "$MODE" == "prod" ]]; then
    echo "⚙️  Production mode: Installing runtime dependencies only..."
    pip-sync requirements.txt
    echo "✅ Production dependencies synced!"
else
    echo "⚙️  Development mode: Installing all dependencies..."
    pip-sync requirements.txt requirements-dev.txt
    echo "✅ Development dependencies synced!"
fi

echo ""
echo "📊 Environment status:"
python -c "
import sys
print(f'  Python: {sys.version.split()[0]}')
try:
    import modal, fastapi, pypdf
    print('  ✅ Core packages: OK')
except ImportError as e:
    print(f'  ❌ Import error: {e}')
"

echo ""
echo "🎯 Ready for development!"
