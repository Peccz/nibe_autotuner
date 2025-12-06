#!/bin/bash
#
# Autonomous AI Agent Runner - PORTABLE VERSION
# Auto-detects git repository root - works anywhere!
#

set -e

# Auto-detect git repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$PROJECT_ROOT"

echo "Project root: $PROJECT_ROOT"

# Load environment variables (includes GOOGLE_API_KEY for Gemini)
set -a
[ -f .env ] && . .env
set +a

# Explicitly export critical environment variables for Python subprocess
export GOOGLE_API_KEY
export TIBBER_API_TOKEN

# Check if API key is set
if [ -z "$GOOGLE_API_KEY" ]; then
    echo "ERROR: GOOGLE_API_KEY not set!"
    echo "Please set it in .env file or environment"
    exit 1
fi

# Log start
echo "=================================================="
echo "Autonomous AI Agent - $(date)"
echo "=================================================="

# Run AI agent V2 with safety guardrails (dry_run=False means it will apply changes!)
export PYTHONPATH=./src
./venv/bin/python -c "
from integrations.autonomous_ai_agent_v2 import AutonomousAIAgentV2
from services.analyzer import HeatPumpAnalyzer
from integrations.api_client import MyUplinkClient
from services.weather_service import SMHIWeatherService
from data.models import Device; from data.database import engine
from sqlalchemy.orm import sessionmaker
import sys

try:
    # Initialize database
    pass
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

    # Create AI agent V2 (with hardcoded safety guardrails)
    agent = AutonomousAIAgentV2(
        analyzer=analyzer,
        api_client=api_client,
        weather_service=weather_service,
        device_id=device.device_id
    )

    # Analyze and decide (LIVE MODE - applies changes if safe!)
    decision = agent.analyze_and_decide(hours_back=72, dry_run=False)

    print()
    print('='*80)
    print('AI AGENT COMPLETED')
    print('='*80)
    print(f'Action: {decision.action}')
    if decision.action == 'adjust':
        print(f'Parameter: {decision.parameter}')
        print(f'Change: {decision.current_value} → {decision.suggested_value}')
    print(f'Reasoning: {decision.reasoning}')
    print(f'Confidence: {decision.confidence*100:.0f}%')
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
echo "AI Agent completed at $(date)"
echo "=================================================="
