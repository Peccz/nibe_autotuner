#!/bin/bash
# Install Nibe Autotuner systemd service

set -e

echo "Installing Nibe Autotuner Data Logger Service..."
echo "================================================"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  Don't run this script as root (with sudo)"
    echo "   The script will ask for sudo password when needed."
    exit 1
fi

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "1. Creating logs directory..."
mkdir -p "$SCRIPT_DIR/logs"

echo "2. Copying service file to systemd..."
sudo cp "$SCRIPT_DIR/nibe-autotuner.service" /etc/systemd/system/

echo "3. Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "4. Enabling service (start on boot)..."
sudo systemctl enable nibe-autotuner.service

echo ""
echo "✅ Installation complete!"
echo ""
echo "Commands to manage the service:"
echo "  sudo systemctl start nibe-autotuner    # Start the service"
echo "  sudo systemctl stop nibe-autotuner     # Stop the service"
echo "  sudo systemctl restart nibe-autotuner  # Restart the service"
echo "  sudo systemctl status nibe-autotuner   # Check status"
echo "  journalctl -u nibe-autotuner -f        # View live logs"
echo ""
echo "Logs are also saved to:"
echo "  $SCRIPT_DIR/logs/data_logger.log"
echo "  $SCRIPT_DIR/logs/data_logger_error.log"
echo ""
echo "Do you want to start the service now? (y/n)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Starting service..."
    sudo systemctl start nibe-autotuner
    sleep 2
    sudo systemctl status nibe-autotuner
fi
