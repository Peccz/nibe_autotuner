#!/bin/bash
#
# Autonomous AI Agent Runner (DRY RUN)
# Uses Claude API to analyze system but does NOT apply changes
#
# Use this for testing and seeing what the AI would do
#

set -e  # Exit on error

# Change to project directory
cd /home/peccz/nibe_autotuner

# Load environment variables (includes ANTHROPIC_API_KEY)
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if API key is set
if [ -z "$GOOGLE_API_KEY" ]; then
    echo "ERROR: GOOGLE_API_KEY not set!"
    echo "Please set it in .env file or environment"
    exit 1
fi

# Log start
echo "=================================================="
echo "Autonomous AI Agent V2 (DRY RUN) - $(date)"
echo "=================================================="
echo "NOTE: This is a DRY RUN - no changes will be applied"
echo "=================================================="

# Run AI agent (dry_run=True means it will NOT apply changes)
PYTHONPATH=./src ./venv/bin/python -c "
from integrations.autonomous_ai_agent_v2 import AutonomousAIAgentV2
from services.analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService
from data.models import Device, init_db
from sqlalchemy.orm import sessionmaker
import sys

try:
    # Initialize database
    # init_db() handled internally usually but good to have
    from data.database import SessionLocal
    session = SessionLocal()

    # Get device
    device = session.query(Device).first()
    if not device:
        print('ERROR: No device found in database')
        sys.exit(1)

    # Create services
    api_client = MyUplinkClient()
    analyzer = HeatPumpAnalyzer()
    weather_service = SMHIWeatherService()

    # Create AI agent V2
    agent = AutonomousAIAgentV2(
        analyzer=analyzer,
        api_client=api_client,
        weather_service=weather_service,
        device_id=device.device_id
    )

    # Analyze and decide (DRY RUN - does NOT apply changes!)
    decision = agent.analyze_and_decide(hours_back=72, dry_run=True, mode='tactical')

    print()
    print('='*80)
    print('AI AGENT ANALYSIS COMPLETE (DRY RUN)')
    print('='*80)
    print(f'Action: {decision.action}')
    if decision.action == 'adjust':
        print(f'Parameter: {decision.parameter}')
        print(f'Change: {decision.current_value} → {decision.suggested_value}')
        print()
        print('⚠️  This change was NOT applied (dry run mode)')
        print('To apply changes, run: scripts/run_ai_agent.sh')
    print()
    print(f'Reasoning: {decision.reasoning}')
    print(f'Confidence: {decision.confidence*100:.0f}%')
    print(f'Expected Impact: {decision.expected_impact}')
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
echo "Dry run completed at $(date)"
echo "=================================================="
