#!/usr/bin/env bash
# karlacommit — stage, commit, and push helper for Codebook_AIDev
set -e

# Make sure we're inside a git repo
if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "ERROR: You are not inside a git repository."
    exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "=============================================="
echo " STEP 1: Checking current branch"
echo "=============================================="
echo " You are on branch: $BRANCH"
echo ""

echo "=============================================="
echo " STEP 2: Checking for changes"
echo "=============================================="
if [ -z "$(git status --porcelain)" ]; then
    echo " Working tree is clean — nothing to commit."
    exit 0
fi
git status --short
echo ""

echo "=============================================="
echo " STEP 3: Staging changes"
echo "=============================================="
read -p " Stage ALL changes? (y = all / n = choose files): " STAGE_ALL
if [[ "$STAGE_ALL" =~ ^[Yy]$ ]]; then
    git add -A
    echo " All changes staged."
else
    read -p " Enter file(s) to stage (space-separated): " FILES
    git add $FILES
    echo " Staged: $FILES"
fi
echo ""

echo "=============================================="
echo " STEP 4: Commit message"
echo "=============================================="
read -p " Enter your commit message: " MSG
if [ -z "$MSG" ]; then
    echo " ERROR: Commit message cannot be empty. Aborting."
    exit 1
fi
git commit -m "$MSG"
echo " Committed with message: \"$MSG\""
echo ""

echo "=============================================="
echo " STEP 5: Pushing to GitHub"
echo "=============================================="
echo " Pushing branch '$BRANCH' to origin..."
git push -u origin "$BRANCH"
echo ""
echo " DONE! Your changes are on GitHub."
