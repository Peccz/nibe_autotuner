#!/bin/bash
#
# Morning Analysis Script
# Runs every morning to:
# 1. Analyze last 24h of system data
# 2. Generate prioritized list of tests
# 3. Store test proposals in database for GUI display
#

set -e  # Exit on error

# Change to project directory
cd /home/peccz/nibe_autotuner

# Load environment variables (includes ANTHROPIC_API_KEY if configured)
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Log start
echo "=================================================="
echo "Morning Analysis - $(date)"
echo "=================================================="

# Run test proposer
PYTHONPATH=./src ./venv/bin/python -c "
from test_proposer import TestProposer
from services.analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService
from data.models import Device, init_db
from sqlalchemy.orm import sessionmaker
import sys

try:
    # Initialize database
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()

    # Get device
    device = session.query(Device).first()
    if not device:
        print('ERROR: No device found in database')
        sys.exit(1)

    # Create services
    api_client = MyUplinkClient()
    analyzer = HeatPumpAnalyzer()
    weather_service = SMHIWeatherService()

    # Create test proposer
    proposer = TestProposer(
        analyzer=analyzer,
        api_client=api_client,
        weather_service=weather_service,
        device_id=device.device_id
    )

    # Analyze last 24h and propose tests
    proposals = proposer.propose_tests(hours_back=24)

    print()
    print('='*80)
    print(f'GENERATED {len(proposals)} TEST PROPOSALS')
    print('='*80)
    for i, prop in enumerate(proposals, 1):
        print(f'{i}. [{prop.priority.upper()}] {prop.parameter}')
        print(f'   Hypothesis: {prop.hypothesis}')
        print(f'   Expected: {prop.expected_improvement}')
        print(f'   Confidence: {prop.confidence*100:.0f}%')
        print()

    print('Proposals stored in database and visible in GUI AI tab')
    print('='*80)

    sys.exit(0)

except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

# Log completion
echo "=================================================="
echo "Morning analysis completed at $(date)"
echo "=================================================="
