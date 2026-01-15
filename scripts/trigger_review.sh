#!/bin/bash

# Script to trigger a CodeRabbit review by creating a dummy PR branch

BRANCH_NAME="review/initial-audit-$(date +%s)"

echo "1. Creating new branch: $BRANCH_NAME..."
git checkout -b "$BRANCH_NAME"

echo "2. Making a dummy change to README.md..."
echo "" >> README.md
echo "<!-- AI Review Trigger: $(date) -->" >> README.md

echo "3. Committing change..."
git add README.md
git commit -m "Chore: Trigger full system audit by CodeRabbit"

echo "4. Pushing branch..."
git push origin "$BRANCH_NAME"

echo "--------------------------------------------------------"
echo "DONE! Go to this URL to open the Pull Request:"
echo "https://github.com/Peccz/nibe_autotuner/pull/new/$BRANCH_NAME"
echo "--------------------------------------------------------"
