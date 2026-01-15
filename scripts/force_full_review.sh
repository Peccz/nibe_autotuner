#!/bin/bash

BRANCH_NAME="review/full-logic-audit-$(date +%s)"

echo "1. Creating branch $BRANCH_NAME..."
git checkout main
git pull
git checkout -b "$BRANCH_NAME"

echo "2. Modifying smart_planner.py to force review..."
# Append a harmless log line to the init method
sed -i 's/logger.info("Starting SmartPlanner V7.0 (Granular Optimization)...")/logger.info("Starting SmartPlanner V7.0 (Granular Optimization) - Audit Build")/g' src/services/smart_planner.py

echo "3. Committing..."
git add src/services/smart_planner.py .coderabbit.yaml
git commit -m "Refactor: Update planner initialization and fix CI config"

echo "4. Pushing..."
git push origin "$BRANCH_NAME"

echo "DONE! Open PR here:"
echo "https://github.com/Peccz/nibe_autotuner/pull/new/$BRANCH_NAME"
