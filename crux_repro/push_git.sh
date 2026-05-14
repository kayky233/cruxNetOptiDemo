#!/bin/bash
set -e
cd /Users/dkwyl/Documents/tmbProject/net

echo "=== Staging changes ==="
git add -A

echo "=== Committing ==="
git commit -m "docs: update simgrid-manual-zh.html to v2 (complete all sub-sections)"

echo "=== Pushing to GitHub ==="
git push -u origin main

echo ""
echo "=== Done ==="
echo "View at: https://github.com/kayky233/cruxNetOptiDemo"
