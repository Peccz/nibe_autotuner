#!/bin/bash
# Run AI Evaluation Service
# Should be run once daily (e.g. 05:00)

cd "$(dirname "$0")/.."

# Activate virtual environment
source venv/bin/activate

# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Run evaluator
python src/services/ai_evaluator.py
