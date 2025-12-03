#!/bin/bash
#
# Deploy A/B Testing to Raspberry Pi
#
# This script:
# 1. Commits changes to git
# 2. Pushes to remote
# 3. SSHs to RPi and pulls updates
# 4. Installs cron jobs
# 5. Restarts mobile app service
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
RPI_HOST="nibe-rpi"
RPI_USER="peccz"
RPI_DIR="/home/peccz/nibe_autotuner"

echo -e "${BLUE}========================================"
echo "Deploy A/B Testing to RPi"
echo -e "========================================${NC}\n"

# Step 1: Commit and push changes
echo -e "${YELLOW}Step 1: Committing changes to git...${NC}"

git add -A

if git diff --cached --quiet; then
    echo -e "${GREEN}✓ No changes to commit${NC}"
else
    read -p "Enter commit message: " COMMIT_MSG
    if [ -z "$COMMIT_MSG" ]; then
        COMMIT_MSG="Enable A/B testing: database logging and cron jobs"
    fi

    git commit -m "$COMMIT_MSG"
    echo -e "${GREEN}✓ Changes committed${NC}"
fi

echo -e "\n${YELLOW}Step 2: Pushing to remote...${NC}"
git push origin main
echo -e "${GREEN}✓ Pushed to remote${NC}"

# Step 2: Deploy to RPi
echo -e "\n${YELLOW}Step 3: Deploying to RPi...${NC}"

ssh $RPI_HOST << 'ENDSSH'
set -e

echo "📡 Connected to RPi"
echo ""

# Navigate to project directory
cd /home/peccz/nibe_autotuner || exit 1

echo "📥 Pulling latest changes..."
git pull origin main

echo "✓ Code updated"
echo ""

# Make scripts executable
echo "🔧 Setting script permissions..."
chmod +x scripts/evaluate_ab_tests.sh
chmod +x scripts/propose_tests.sh
echo "✓ Scripts are executable"
echo ""

# Install cron jobs
echo "⏰ Installing cron jobs..."

# Remove existing cron jobs for these scripts (if any)
crontab -l 2>/dev/null | grep -v "evaluate_ab_tests.sh" | grep -v "propose_tests.sh" > /tmp/crontab.new || true

# Add new cron jobs
cat >> /tmp/crontab.new << 'EOF'

# A/B Testing - Evaluate pending changes daily at 06:00
0 6 * * * /home/peccz/nibe_autotuner/scripts/evaluate_ab_tests.sh >> /var/log/ab-testing.log 2>&1

# AI Test Proposer - Propose new tests weekly on Monday at 07:00
0 7 * * 1 /home/peccz/nibe_autotuner/scripts/propose_tests.sh >> /var/log/test-proposer.log 2>&1
EOF

# Install new crontab
crontab /tmp/crontab.new
rm /tmp/crontab.new

echo "✓ Cron jobs installed:"
echo "  - A/B evaluation: Daily at 06:00"
echo "  - Test proposer: Weekly (Monday) at 07:00"
echo ""

# Show installed cron jobs
echo "📋 Current crontab:"
crontab -l | tail -n 10
echo ""

# Restart mobile app service
echo "🔄 Restarting nibe-mobile service..."
sudo systemctl restart nibe-mobile.service

# Wait a moment
sleep 2

# Check service status
echo ""
echo "📊 Service status:"
sudo systemctl status nibe-mobile.service --no-pager -l | head -n 15

echo ""
echo "✅ Deployment completed successfully!"
echo ""
echo "🎯 Next steps:"
echo "  1. Check logs: tail -f /var/log/nibe-mobile.log"
echo "  2. Test A/B page: http://192.168.86.34:8502/ab-testing"
echo "  3. Make a parameter change to test logging"
echo "  4. Wait 48h and check A/B results"
echo ""

ENDSSH

# Final message
echo -e "\n${GREEN}========================================"
echo "✅ Deployment Completed!"
echo -e "========================================${NC}\n"

echo -e "${BLUE}📱 Dashboard:${NC} http://192.168.86.34:8502"
echo -e "${BLUE}🧪 A/B Testing:${NC} http://192.168.86.34:8502/ab-testing"
echo -e "${BLUE}🤖 AI Agent:${NC} http://192.168.86.34:8502/ai-agent"
echo ""

echo -e "${YELLOW}📝 Test the system:${NC}"
echo "  1. Go to Dashboard → Click 'Höj temp' or 'Sänk temp'"
echo "  2. Check logs: ssh $RPI_HOST 'tail -n 50 /var/log/nibe-mobile.log'"
echo "  3. You should see: '✅ Parameter change logged to database: ID=...'"
echo "  4. After 48h, check /ab-testing for results"
echo ""

echo -e "${YELLOW}⏰ Cron schedule:${NC}"
echo "  • 06:00 daily - A/B test evaluation"
echo "  • 07:00 Monday - AI test proposals"
echo ""

exit 0
