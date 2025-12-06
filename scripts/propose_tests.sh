#!/bin/bash
#
# AI Test Proposer - Analyzes system and proposes new optimization tests
#
# This script uses AI (Claude Sonnet 3.5) or rule-based logic to analyze
# recent system performance and propose specific tests to improve efficiency.
#
# Schedule: Run weekly on Monday at 07:00
# Crontab: 0 7 * * 1 /home/peccz/nibe_autotuner/scripts/propose_tests.sh
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
LOG_FILE="/var/log/test-proposer.log"

# Ensure log file exists and is writable
touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/test-proposer.log"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "========================================"
log "AI Test Proposer - Starting"
log "========================================"

# Change to project directory
cd "$PROJECT_DIR" || {
    log "ERROR: Could not change to project directory: $PROJECT_DIR"
    exit 1
}

# Check if virtual environment exists
if [ ! -f "$PYTHON" ]; then
    log "ERROR: Python virtual environment not found at: $PYTHON"
    exit 1
fi

# Run test proposer
log "Analyzing system and proposing tests..."

# Using module execution to leverage the main() function in test_proposer.py
PYTHONPATH="$PROJECT_DIR/src" $PYTHON -m integrations.test_proposer 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -eq 0 ]; then
    log "✅ Test proposal completed successfully"
else
    log "❌ Test proposal failed with exit code: $EXIT_CODE"
fi

log "========================================"
log "AI Test Proposer - Finished"
log "========================================"
log ""

exit $EXIT_CODE
