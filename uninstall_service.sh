#!/bin/bash
# Uninstall Nibe Autotuner systemd service

set -e

echo "Uninstalling Nibe Autotuner Data Logger Service..."
echo "==================================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  Don't run this script as root (with sudo)"
    echo "   The script will ask for sudo password when needed."
    exit 1
fi

echo "1. Stopping service..."
sudo systemctl stop nibe-autotuner.service || true

echo "2. Disabling service..."
sudo systemctl disable nibe-autotuner.service || true

echo "3. Removing service file..."
sudo rm -f /etc/systemd/system/nibe-autotuner.service

echo "4. Reloading systemd daemon..."
sudo systemctl daemon-reload

echo ""
echo "✅ Uninstallation complete!"
echo ""
echo "Note: Log files in logs/ directory have NOT been deleted."
echo "      Database file has NOT been deleted."
