#!/bin/bash
# Deploy GUI updates to Raspberry Pi

echo "==================================="
echo "GUI Update Deployment Script"
echo "==================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

RPI_HOST="peccz@100.100.118.62"
RPI_DIR="nibe_autotuner"

echo -e "${YELLOW}Step 1: Pulling latest changes from GitHub on RPi...${NC}"
ssh $RPI_HOST "cd $RPI_DIR && git pull"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Pull successful${NC}"
else
    echo -e "${RED}✗ Pull failed${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 2: Restarting mobile app service...${NC}"
ssh $RPI_HOST "sudo systemctl restart nibe-mobile-app"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Service restarted${NC}"
else
    echo -e "${RED}✗ Restart failed${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 3: Checking service status...${NC}"
sleep 2
ssh $RPI_HOST "sudo systemctl status nibe-mobile-app --no-pager | head -20"

echo ""
echo -e "${YELLOW}Step 4: Verifying web app is responding...${NC}"
sleep 3

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://100.100.118.62:8502/)

if [ "$HTTP_CODE" == "200" ]; then
    echo -e "${GREEN}✓ Web app is responding (HTTP $HTTP_CODE)${NC}"
    echo ""
    echo -e "${GREEN}==================================="
    echo "✅ Deployment successful!"
    echo "===================================${NC}"
    echo ""
    echo "📱 Dashboard: http://100.100.118.62:8502/"
    echo ""
    echo "Changes deployed:"
    echo "  • Major GUI redesign (Phase 1)"
    echo "  • Removed redundant Delta T section"
    echo "  • Enhanced Optimization Score banner"
    echo "  • Prominent AI recommendations"
    echo "  • Added trend indicators"
    echo "  • Integrated Climate & Ventilation"
    echo "  • Simplified System Overview"
    echo ""
else
    echo -e "${RED}✗ Web app not responding (HTTP $HTTP_CODE)${NC}"
    echo ""
    echo "Checking logs..."
    ssh $RPI_HOST "sudo journalctl -u nibe-mobile-app -n 50 --no-pager"
    exit 1
fi
