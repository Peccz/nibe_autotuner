#!/bin/bash
# Auto-Optimizer Daily Run Script
# Runs every day at 03:00 to optimize heating parameters

cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python src/auto_optimizer.py --auto-apply --max-actions 1
