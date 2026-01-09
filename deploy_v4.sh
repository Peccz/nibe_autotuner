#!/bin/bash
# Deploy Nibe Autotuner V4.0 to Raspberry Pi

RPI_HOST="100.100.118.62"
RPI_USER="peccz"
RPI_DIR="/home/peccz/nibe_autotuner"
LOCAL_DIR="/home/peccz/AI/nibe_autotuner"

echo "════════════════════════════════════════════════════════════════"
echo "  Deploying Nibe Autotuner V4.0 to $RPI_HOST"
echo "════════════════════════════════════════════════════════════════"

# 1. Commit Local Changes
echo ""
echo "▶ [1/4] Committing local changes..."
git add .
git commit -m "Deployment V4.0: SmartPlanner, VentilationManager, Database migrations, Service updates" || echo "Nothing to commit or commit failed."

# 2. Sync Files
echo ""
echo "▶ [2/4] Syncing files to Raspberry Pi..."
# We exclude venv, logs, __pycache__, and git metadata to save time/space
rsync -avz --progress --exclude 'venv' --exclude 'logs' --exclude '__pycache__' --exclude '.git' --exclude 'data/nibe_autotuner.db' \
    $LOCAL_DIR/ $RPI_USER@$RPI_HOST:$RPI_DIR/

# 3. Setup & Migrate on Remote
echo ""
echo "▶ [3/4] Configuring Remote Environment..."
ssh $RPI_USER@$RPI_HOST << EOF
    set -e
    cd $RPI_DIR
    
    # Update .env with HA credentials if missing (simple append if not present)
    # Note: We rely on the synced .env for now, but ensure proper permissions
    chmod 600 .env

    # Update dependencies
    echo "  -> Updating Python dependencies..."
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
    pip install -r requirements.txt
    
    # Run Database Migrations
    echo "  -> Running Database Migrations..."
    # We run all migration scripts
    export PYTHONPATH=$RPI_DIR/src
    for f in src/data/migrate_*.py; do 
        echo "     Running \$f..."
        python3 "\$f"
    done
    
    # Also run upgrade_db.py to be sure
    python3 upgrade_db.py

    # Install Service Files
    echo "  -> Installing Systemd Services..."
    sudo cp nibe-autotuner.service nibe-mobile.service nibe-api.service nibe-gm-controller.service /etc/systemd/system/
    
    # Update paths in service files on remote if they differ (Remote path is /home/peccz/nibe_autotuner)
    # We used /home/peccz/AI/nibe_autotuner locally. We must sed replace them to match RPi path.
    sudo sed -i 's|/home/peccz/AI/nibe_autotuner|/home/peccz/nibe_autotuner|g' /etc/systemd/system/nibe-*.service
    
    sudo systemctl daemon-reload
    sudo systemctl enable nibe-autotuner nibe-mobile nibe-api nibe-gm-controller
EOF

# 4. Restart Services
echo ""
echo "▶ [4/4] Restarting Services..."
ssh $RPI_USER@$RPI_HOST "sudo systemctl restart nibe-autotuner nibe-mobile nibe-api nibe-gm-controller"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  ✓ Deployment Complete!"
echo "  Dashboard: http://$RPI_HOST:5001/dashboard"
echo "  API:       http://$RPI_HOST:8000/docs"
echo "════════════════════════════════════════════════════════════════"
