#!/bin/bash
# Launch Nibe Autotuner GUI

set -e

echo "🔥 Starting Nibe Autotuner GUI..."
echo "================================"
echo ""
echo "The web interface will open in your browser at:"
echo "http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run Streamlit
streamlit run src/gui.py --server.port 8501 --server.address localhost
