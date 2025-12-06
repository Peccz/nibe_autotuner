#!/bin/bash
# Nibe Autotuner Cron Setup
# Deploys the crontab configuration for autonomous operation

CRON_FILE="/tmp/nibe_crontab"

echo "Generating crontab configuration..."

cat << EOF > $CRON_FILE
# Nibe Autotuner - Autonomous AI Agent (Hourly Tactical Optimization)
0 * * * * /home/peccz/nibe_autotuner/scripts/run_ai_agent.sh >> ~/nibe-ai-agent.log 2>&1

# AI Evaluator - Daily Performance Review (05:30)
30 5 * * * /home/peccz/nibe_autotuner/scripts/run_ai_evaluation.sh >> ~/nibe-evaluation.log 2>&1

# AI Scientist - Autonomous Test Proposer & Scheduler (Daily at 07:00)
0 7 * * * /home/peccz/nibe_autotuner/scripts/propose_tests.sh >> ~/nibe-scientist.log 2>&1

# Data Maintenance (Weekly)
0 4 * * 1 /home/peccz/nibe_autotuner/venv/bin/python /home/peccz/nibe_autotuner/src/services/db_maintenance.py >> ~/nibe-maintenance.log 2>&1
EOF

echo "Deploying crontab..."
crontab $CRON_FILE
rm $CRON_FILE

echo "✅ Crontab updated successfully!"
crontab -l
