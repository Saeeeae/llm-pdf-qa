#!/usr/bin/env bash
# Github push instructions — sandbox cannot modify .git/, run this on your host.
# Repo: https://github.com/Saeeeae/llm-pdf-qa.git

set -euo pipefail
cd "$(dirname "$0")"

# 1. Remove stale lock (sandbox left this behind)
rm -f .git/index.lock

# 2. Set identity (skip if already set globally)
if [ -z "$(git config user.name 2>/dev/null)" ]; then
    git config user.name "sae"
    git config user.email "kangppang2@gmail.com"
fi

# 3. Stage everything (deletions + modifications + new files)
git add -A

# 4. Show summary before commit
echo "=== Changes to commit ==="
git status --short | head -50
echo "..."
echo "Total: $(git status --short | wc -l) files"
echo ""

# 5. Commit with comprehensive message
git commit -F COMMIT_MSG.txt

# 6. Push to origin
git push origin HEAD
