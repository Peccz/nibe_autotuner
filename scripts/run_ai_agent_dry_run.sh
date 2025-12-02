#!/bin/bash
#
# Autonomous AI Agent Runner (DRY RUN)
# Uses Claude API to analyze system but does NOT apply changes
#
# Use this for testing and seeing what the AI would do
#

set -e  # Exit on error

# Change to project directory
cd /home/peccz/AI/nibe_autotuner

# Load environment variables (includes ANTHROPIC_API_KEY)
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if API key is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set!"
    echo "Please set it in .env file or environment"
    exit 1
fi

# Log start
echo "=================================================="
echo "Autonomous AI Agent (DRY RUN) - $(date)"
echo "=================================================="
echo "NOTE: This is a DRY RUN - no changes will be applied"
echo "=================================================="

# Run AI agent (dry_run=True means it will NOT apply changes)
PYTHONPATH=./src ./venv/bin/python -c "
from autonomous_ai_agent import AutonomousAIAgent
from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService
from models import Device, init_db
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

    # Create AI agent
    agent = AutonomousAIAgent(
        analyzer=analyzer,
        api_client=api_client,
        weather_service=weather_service,
        device_id=device.device_id
    )

    # Analyze and decide (DRY RUN - does NOT apply changes!)
    decision = agent.analyze_and_decide(hours_back=72, dry_run=True)

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
