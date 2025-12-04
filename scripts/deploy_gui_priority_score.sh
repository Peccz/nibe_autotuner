#!/bin/bash
# Deploy GUI updates with priority score feature

set -e

RPI_HOST="nibe-rpi"
RPI_DIR="/home/peccz/nibe_autotuner"

echo "🚀 Deploying GUI priority score updates to RPi..."

# Copy updated files
echo "📁 Copying files..."
scp src/models.py ${RPI_HOST}:${RPI_DIR}/src/
scp src/mobile_app.py ${RPI_HOST}:${RPI_DIR}/src/
scp src/mobile/templates/ai_agent.html ${RPI_HOST}:${RPI_DIR}/src/mobile/templates/
scp src/mobile/templates/ab_testing.html ${RPI_HOST}:${RPI_DIR}/src/mobile/templates/
scp scripts/migrate_add_priority_score.py ${RPI_HOST}:${RPI_DIR}/scripts/

# Run migration
echo "🔄 Running database migration..."
ssh ${RPI_HOST} "cd ${RPI_DIR} && PYTHONPATH=./src ./venv/bin/python3 scripts/migrate_add_priority_score.py"

# Restart Flask app
echo "🔄 Restarting Mobile PWA service..."
ssh ${RPI_HOST} "sudo systemctl restart nibe-mobile.service"

echo "✅ Deployment complete!"
echo ""
echo "🌐 Check pages:"
echo "   • AI Agent: http://192.168.86.34:8502/ai-agent"
echo "   • A/B Tests: http://192.168.86.34:8502/ab-testing"
