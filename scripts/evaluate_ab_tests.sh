#!/bin/bash
#
# A/B Test Evaluator - Runs daily to evaluate pending parameter changes
#
# This script evaluates all parameter changes that have been made and
# have waited at least 48h for "after" metrics to be collected.
#
# Schedule: Run daily at 06:00
# Crontab: 0 6 * * * /home/peccz/nibe_autotuner/scripts/evaluate_ab_tests.sh
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
LOG_FILE="/var/log/ab-testing.log"

# Ensure log file exists and is writable
touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/ab-testing.log"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "========================================"
log "A/B Test Evaluation - Starting"
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

# Run A/B test evaluation
log "Running A/B test evaluation..."

$PYTHON -c "
import sys
sys.path.insert(0, 'src')

from ab_tester import ABTester
from analyzer import HeatPumpAnalyzer
from loguru import logger

# Configure logger to also write to stdout
import sys
logger.add(sys.stdout, format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}')

logger.info('Initializing A/B Tester...')

try:
    # Initialize analyzer and tester
    analyzer = HeatPumpAnalyzer('data/nibe_autotuner.db')
    ab_tester = ABTester(analyzer)

    # Evaluate all pending changes
    logger.info('Evaluating all pending parameter changes...')
    results = ab_tester.evaluate_all_pending()

    if results:
        logger.success(f'✅ Evaluated {len(results)} parameter change(s)')
        for result in results:
            logger.info(f'  - Change ID {result.parameter_change_id}: Score={result.success_score:.1f}, {result.recommendation}')
    else:
        logger.info('ℹ️ No pending changes to evaluate (need to wait 48h after change)')

    logger.success('A/B test evaluation completed successfully')
    sys.exit(0)

except Exception as e:
    logger.error(f'❌ A/B test evaluation failed: {e}')
    import traceback
    logger.error(traceback.format_exc())
    sys.exit(1)
" 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -eq 0 ]; then
    log "✅ A/B test evaluation completed successfully"
else
    log "❌ A/B test evaluation failed with exit code: $EXIT_CODE"
fi

log "========================================"
log "A/B Test Evaluation - Finished"
log "========================================"
log ""

exit $EXIT_CODE
