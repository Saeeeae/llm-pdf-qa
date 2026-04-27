#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTRACTS_DIR="$REPO_ROOT/packages/contracts"
LOCK_DIR="$CONTRACTS_DIR/.lock"

mkdir -p "$LOCK_DIR"

for f in "$CONTRACTS_DIR"/*.yaml; do
  name=$(basename "$f" .yaml)
  sha256sum "$f" | awk '{print $1}' > "$LOCK_DIR/$name.sha256"
  echo "Locked: $name  ($(cat "$LOCK_DIR/$name.sha256" | cut -c1-12)...)"
done

echo ""
echo "Contract locks updated in $LOCK_DIR"
echo "Commit packages/contracts/.lock/ to baseline the current spec state."
