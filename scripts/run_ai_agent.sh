#!/bin/bash
#
# Deterministic Planner Runner V8.0
# Runs the Control System to update heating plan every hour.
#

set -e

# Auto-detect git repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$PROJECT_ROOT"

# Log start
echo "=================================================="
echo "Deterministic Control V8.0 - $(date)"
echo "=================================================="

export PYTHONPATH=./src

# Run the deterministic planner
./venv/bin/python src/services/smart_planner.py

# Log completion
if [ $? -eq 0 ]; then
    echo "✓ Control Loop Success"
else
    echo "❌ Control Loop Failed"
fi
echo "=================================================="