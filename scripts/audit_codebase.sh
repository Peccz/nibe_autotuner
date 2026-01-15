#!/bin/bash

BRANCH_NAME="audit/full-codebase-$(date +%s)"

echo "1. Creating branch $BRANCH_NAME..."
git checkout main
git pull
git checkout -b "$BRANCH_NAME"

echo "2. Touching all Python files to force deep review..."
# Appends a newline to all .py files in src/ to force git to see them as changed
find src -name "*.py" -type f -exec sh -c 'echo "" >> "$1"' _ {} \;

echo "3. Committing massive changeset..."
git add src
git commit -m "Chore: Whitespace bump to trigger full codebase audit"

echo "4. Pushing..."
git push origin "$BRANCH_NAME"

echo "DONE! Prepare for a massive review here:"
echo "https://github.com/Peccz/nibe_autotuner/pull/new/$BRANCH_NAME"
