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

PYTHONPATH="$PROJECT_DIR/src" $PYTHON -c "
import sys
sys.path.insert(0, 'src')

from test_proposer import TestProposer
from services.analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService
from data.models import Device, init_db
from sqlalchemy.orm import sessionmaker
from loguru import logger
import os

# Configure logger to also write to stdout
logger.add(sys.stdout, format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}')

logger.info('Initializing AI Test Proposer...')

try:
    # Initialize database
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()

    # Get device
    device = session.query(Device).first()
    if not device:
        logger.error('No device found in database')
        sys.exit(1)

    logger.info(f'Using device: {device.product_name} ({device.device_id})')

    # Initialize components
    api_client = MyUplinkClient()
    analyzer = HeatPumpAnalyzer('data/nibe_autotuner.db')
    weather_service = SMHIWeatherService()

    # Create proposer
    proposer = TestProposer(
        analyzer=analyzer,
        api_client=api_client,
        weather_service=weather_service,
        device_id=device.device_id,
        anthropic_api_key=os.getenv('ANTHROPIC_API_KEY')
    )

    # Propose tests (analyzes last 24h)
    logger.info('Analyzing last 24h of system performance...')
    proposals = proposer.propose_tests(hours_back=24)

    if proposals:
        logger.success(f'✅ Generated {len(proposals)} test proposal(s):')
        for i, prop in enumerate(proposals, 1):
            logger.info(f'{i}. [{prop.priority.upper()}] {prop.parameter}: {prop.current_value} → {prop.proposed_value}')
            logger.info(f'   Hypothesis: {prop.hypothesis}')
            logger.info(f'   Expected: {prop.expected_improvement}')
            logger.info(f'   Confidence: {prop.confidence*100:.0f}%')
            logger.info('')
    else:
        logger.info('ℹ️ No test proposals generated (system may be optimal)')

    logger.success('Test proposal completed successfully')
    session.close()
    sys.exit(0)

except Exception as e:
    logger.error(f'❌ Test proposal failed: {e}')
    import traceback
    logger.error(traceback.format_exc())
    sys.exit(1)
" 2>&1 | tee -a "$LOG_FILE"

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
