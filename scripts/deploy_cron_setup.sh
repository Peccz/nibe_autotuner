#!/bin/bash
#
# Generic Cron Deployment Script
# Works on any machine by detecting git repository root
#
# NO HARDCODED PATHS - Everything is auto-detected!
#

set -e

# Configuration
RPI_HOST="peccz@100.100.118.62"

echo "=================================================="
echo "Generic Cron Deployment to RPi"
echo "=================================================="

# Step 1: Detect local git root
echo "✓ Step 1: Detecting local git repository root..."
LOCAL_GIT_ROOT=$(git rev-parse --show-toplevel)
echo "  Local:  $LOCAL_GIT_ROOT"

# Step 2: Detect remote git root (on RPi)
echo "✓ Step 2: Detecting RPi git repository root..."
RPI_GIT_ROOT=$(ssh "$RPI_HOST" "cd ~ && find . -maxdepth 3 -name '.git' -type d 2>/dev/null | head -1 | xargs dirname")
if [ -z "$RPI_GIT_ROOT" ]; then
    echo "ERROR: Could not find git repository on RPi!"
    exit 1
fi
# Convert relative to absolute path
RPI_GIT_ROOT=$(ssh "$RPI_HOST" "cd ~/$RPI_GIT_ROOT && pwd")
echo "  RPi:    $RPI_GIT_ROOT"

# Step 3: Create portable run_ai_agent.sh
echo "✓ Step 3: Creating portable run_ai_agent.sh..."
cat > /tmp/run_ai_agent_portable.sh << 'ENDSCRIPT'
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
from autonomous_ai_agent_v2 import AutonomousAIAgentV2
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
ENDSCRIPT

chmod +x /tmp/run_ai_agent_portable.sh

# Step 4: Deploy portable script to RPi
echo "✓ Step 4: Deploying portable script to RPi..."
scp /tmp/run_ai_agent_portable.sh "$RPI_HOST:$RPI_GIT_ROOT/scripts/run_ai_agent.sh"

# Step 5: Update crontab on RPi with auto-detected path
echo "✓ Step 5: Updating crontab on RPi..."
ssh "$RPI_HOST" bash << ENDSSH
# Backup current crontab
crontab -l > /tmp/crontab.backup 2>/dev/null || echo "# New crontab" > /tmp/crontab.backup

# Create new crontab with auto-detected paths
cat > /tmp/crontab.new << 'EOF'
# Nibe Autotuner - Autonomous AI Agent (every hour)
0 * * * * $RPI_GIT_ROOT/scripts/run_ai_agent.sh >> ~/nibe-ai-agent.log 2>&1

# Nibe Autotuner - Twice Daily Optimization
0 6 * * * $RPI_GIT_ROOT/scripts/run_twice_daily_optimization.sh >> ~/nibe-optimization.log 2>&1
0 19 * * * $RPI_GIT_ROOT/scripts/run_twice_daily_optimization.sh >> ~/nibe-optimization.log 2>&1

# AB Testing - Daily Evaluation
0 6 * * * $RPI_GIT_ROOT/scripts/evaluate_ab_tests.sh >> ~/ab-testing.log 2>&1

# Test Proposer - Weekly (Mondays at 07:00)
0 7 * * 1 $RPI_GIT_ROOT/scripts/propose_tests.sh >> ~/test-proposer.log 2>&1

# Morning Analysis - Daily at 05:00
0 5 * * * $RPI_GIT_ROOT/scripts/run_morning_analysis.sh >> ~/nibe-morning-analysis.log 2>&1
EOF

# Replace placeholder with actual path
sed -i "s|\\\$RPI_GIT_ROOT|$RPI_GIT_ROOT|g" /tmp/crontab.new

# Install new crontab
crontab /tmp/crontab.new

echo "Crontab updated successfully!"
ENDSSH

# Step 6: Verify installation
echo "✓ Step 6: Verifying crontab on RPi..."
echo ""
echo "=== Current Crontab on RPi ==="
ssh "$RPI_HOST" "crontab -l | grep -v '^#' | grep -v '^$'"
echo ""

# Step 7: Create log files in home directory (no sudo needed!)
echo "✓ Step 7: Creating log files on RPi (in home directory)..."
ssh "$RPI_HOST" bash << 'ENDSSH'
# Create log files in home directory (always writable!)
touch ~/nibe-ai-agent.log
touch ~/nibe-optimization.log
touch ~/ab-testing.log
touch ~/test-proposer.log
touch ~/nibe-morning-analysis.log
echo "Log files created successfully in ~/"
ENDSSH

echo ""
echo "=================================================="
echo "✓ Deployment Complete!"
echo "=================================================="
echo ""
echo "PATH CONFIGURATION:"
echo "  Local:  $LOCAL_GIT_ROOT"
echo "  RPi:    $RPI_GIT_ROOT"
echo ""
echo "LOG LOCATIONS (RPi):"
echo "  ~/nibe-ai-agent.log"
echo "  ~/nibe-optimization.log"
echo "  ~/ab-testing.log"
echo ""
echo "Next AI run will be at the top of the next hour."
echo ""
echo "To test manually on RPi:"
echo "  ssh $RPI_HOST"
echo "  cd $RPI_GIT_ROOT"
echo "  ./scripts/run_ai_agent.sh"
echo ""
echo "To monitor logs:"
echo "  ssh $RPI_HOST tail -f ~/nibe-ai-agent.log"
echo ""
