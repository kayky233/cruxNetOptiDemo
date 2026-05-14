#!/bin/bash
# Git initialization script for net project
set -e

cd /Users/dkwyl/Documents/tmbProject/net

# Initialize git repo
git init

# Create .gitignore
cat > .gitignore << 'GITIGNORE'
# Build artifacts
.build/

# Environment and package managers
.mamba/
.simgrid_env/
.simgrid_install/
.tools/

# macOS
.DS_Store
.AppleDouble
.LSOverride

# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
.eggs/

# Compiled binary
test_stackgrowth

# IDE
.vscode/
.idea/
*.swp
*.swo

# SimGrid build artifacts in crux_repro
crux_repro/simgrid_real/build/
crux_repro/simgrid_real/*.o
crux_repro/simgrid_real/collective_sim

# Results CSVs (large, auto-generated)
# Uncomment to exclude:
# results/*.csv

# Shell snapshot artifacts
shell_snapshots/
GITIGNORE

echo ".gitignore created"

# Stage all files
git add -A

# Show what will be committed
git status

echo ""
echo "=== Ready for commit ==="
echo "Run: cd /Users/dkwyl/Documents/tmbProject/net && git commit -m 'Initial commit'"
