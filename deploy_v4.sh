#!/bin/bash

# Configuration
REMOTE_USER="peccz"
REMOTE_HOST="100.100.118.62"
REMOTE_DIR="/home/peccz/nibe_autotuner"
BRANCH="main"

echo "════════════════════════════════════════════════════════════════"
echo "  Deploying Nibe Autotuner V7.0 (Robust Edition)"
echo "════════════════════════════════════════════════════════════════"

# 1. Commit Local Changes
echo ""
echo "▶ [1/4] Committing local changes..."
git add .
if git diff-index --quiet HEAD --; then
    echo "    No changes to commit."
else
    echo "    Enter commit message (or press Enter for default):"
    read -r user_msg
    if [ -z "$user_msg" ]; then
        user_msg="Deploy: Auto-update $(date +'%Y-%m-%d %H:%M')"
    fi
    git commit -m "$user_msg"
    
    echo "    Pushing to GitHub..."
    git push origin $BRANCH || echo "⚠️  Push failed (Auth error or Conflict). Please push manually later."
fi

# 2. Sync Files
echo ""
echo "▶ [2/4] Syncing files to Raspberry Pi ($REMOTE_HOST)..."
rsync -avz --exclude 'venv' --exclude '__pycache__' --exclude 'data/nibe_autotuner.db' --exclude '.git' \
    ./ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/

if [ $? -eq 0 ]; then
    echo "    ✓ Sync successful."
else
    echo "    ❌ Sync failed!"
    exit 1
fi

# 3. Remote Setup
echo ""
echo "▶ [3/4] Configuring Remote Environment..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
    cd $REMOTE_DIR
    
    echo "  -> Updating Python dependencies..."
    source venv/bin/activate
    pip install -r requirements.txt --quiet
    
    echo "  -> Running Database Migrations..."
    # Add migration commands here if needed
    # python src/data/migrate_db.py
EOF

# 4. Restart Services
echo ""
echo "▶ [4/4] Restarting Services..."
ssh $REMOTE_USER@$REMOTE_HOST "sudo systemctl restart nibe-autotuner nibe-api nibe-gm-controller"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  ✓ Deployment Complete!"
echo "  Dashboard: http://$REMOTE_HOST:8000/dashboard"
echo "════════════════════════════════════════════════════════════════"