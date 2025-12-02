#!/bin/bash
#
# Twice-Daily Optimization Script
# Runs morning (06:00) and evening (19:00) to optimize:
# 1. Ventilation settings based on outdoor temperature
# 2. Heat pump settings based on AI analysis
#
# Morning run (06:00): Prepare for daytime
# Evening run (19:00): Prepare for nighttime
#

set -e  # Exit on error

# Change to project directory
cd /home/peccz/nibe_autotuner

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Determine time of day
HOUR=$(date +%H)
if [ "$HOUR" -ge 6 ] && [ "$HOUR" -lt 12 ]; then
    TIME_OF_DAY="morning"
    OPTIMIZATION_FOCUS="daytime"
elif [ "$HOUR" -ge 12 ] && [ "$HOUR" -lt 18 ]; then
    TIME_OF_DAY="afternoon"
    OPTIMIZATION_FOCUS="daytime"
else
    TIME_OF_DAY="evening"
    OPTIMIZATION_FOCUS="nighttime"
fi

# Log start
echo "=================================================="
echo "Twice-Daily Optimization - $(date)"
echo "Time of day: $TIME_OF_DAY"
echo "Focus: $OPTIMIZATION_FOCUS"
echo "=================================================="

# Step 1: Optimize Ventilation
echo ""
echo "Step 1: Optimizing ventilation settings..."
echo "-------------------------------------------"

PYTHONPATH=./src ./venv/bin/python -c "
from ventilation_optimizer import VentilationOptimizer
from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from models import Device, init_db
from sqlalchemy.orm import sessionmaker
import sys

try:
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()

    if not device:
        print('ERROR: No device found')
        sys.exit(1)

    analyzer = HeatPumpAnalyzer()
    api_client = MyUplinkClient()

    optimizer = VentilationOptimizer(
        api_client=api_client,
        analyzer=analyzer,
        device_id=device.device_id
    )

    # Get recommendation and apply
    result = optimizer.apply_recommended_settings(dry_run=False)

    if result['changed']:
        print(f'✓ Ventilation settings updated:')
        print(f'  Strategy: {result[\"strategy_name\"]}')
        for change in result['changes']:
            print(f'  - {change[\"parameter\"]}: {change[\"old_value\"]} → {change[\"new_value\"]}')
    else:
        print(f'✓ Ventilation settings already optimal ({result[\"strategy_name\"]})')

except Exception as e:
    print(f'ERROR in ventilation optimization: {e}')
    # Continue to heat pump optimization even if ventilation fails
"

# Step 2: Optimize Heat Pump (AI-driven or rule-based)
echo ""
echo "Step 2: Optimizing heat pump settings..."
echo "-----------------------------------------"

# Check if AI agent should run (requires ANTHROPIC_API_KEY)
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "Using AI-driven optimization..."

    PYTHONPATH=./src ./venv/bin/python -c "
from autonomous_ai_agent import AutonomousAIAgent
from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService
from models import Device, init_db
from sqlalchemy.orm import sessionmaker
import sys

try:
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()

    if not device:
        print('ERROR: No device found')
        sys.exit(1)

    api_client = MyUplinkClient()
    analyzer = HeatPumpAnalyzer()
    weather_service = SMHIWeatherService()

    agent = AutonomousAIAgent(
        analyzer=analyzer,
        api_client=api_client,
        weather_service=weather_service,
        device_id=device.device_id
    )

    # Analyze with focus based on time of day
    hours_back = 12  # Shorter window for twice-daily runs
    decision = agent.analyze_and_decide(hours_back=hours_back, dry_run=False)

    print(f'✓ AI Decision: {decision.action}')
    if decision.action == 'adjust':
        print(f'  Parameter: {decision.parameter}')
        print(f'  Change: {decision.current_value} → {decision.suggested_value}')
    print(f'  Reasoning: {decision.reasoning[:200]}...')

except Exception as e:
    print(f'ERROR in AI optimization: {e}')
"
else
    echo "Using rule-based optimization (no API key)..."

    PYTHONPATH=./src ./venv/bin/python -c "
from auto_optimizer import AutoOptimizer
from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from models import Device, init_db
from sqlalchemy.orm import sessionmaker
import sys

try:
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()

    if not device:
        print('ERROR: No device found')
        sys.exit(1)

    analyzer = HeatPumpAnalyzer()
    api_client = MyUplinkClient()

    optimizer = AutoOptimizer(
        analyzer=analyzer,
        api_client=api_client,
        device_id=device.device_id,
        dry_run=False
    )

    # Run optimizer
    actions = optimizer.optimize(max_actions=1)

    if actions:
        print(f'✓ Applied {len(actions)} optimization(s):')
        for action in actions:
            print(f'  - {action[\"parameter\"]}: {action[\"old_value\"]} → {action[\"new_value\"]}')
            print(f'    Reason: {action[\"reason\"]}')
    else:
        print('✓ System already optimal, no changes needed')

except Exception as e:
    print(f'ERROR in rule-based optimization: {e}')
"
fi

# Summary
echo ""
echo "=================================================="
echo "Optimization completed at $(date)"
echo "Next run: "
if [ "$TIME_OF_DAY" = "morning" ] || [ "$TIME_OF_DAY" = "afternoon" ]; then
    echo "  Evening (19:00) - Nighttime optimization"
else
    echo "  Morning (06:00) - Daytime optimization"
fi
echo "=================================================="
