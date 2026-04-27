#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTRACTS_DIR="$REPO_ROOT/packages/contracts"
LOCK_DIR="$CONTRACTS_DIR/.lock"

status=0

if [ ! -d "$LOCK_DIR" ]; then
  echo "ERROR: Lock directory $LOCK_DIR does not exist."
  echo "Run 'make contracts-lock' or 'bash scripts/contracts-lock.sh' to generate locks."
  exit 1
fi

for f in "$CONTRACTS_DIR"/*.yaml; do
  name=$(basename "$f" .yaml)
  lock="$LOCK_DIR/$name.sha256"

  if [ ! -f "$lock" ]; then
    echo "MISSING lock for $name — run scripts/contracts-lock.sh after review"
    status=1
    continue
  fi

  cur=$(sha256sum "$f" | awk '{print $1}')
  exp=$(cat "$lock")

  if [ "$cur" != "$exp" ]; then
    echo "DRIFT detected: $name"
    echo "  expected: $exp"
    echo "  current:  $cur"
    echo "  -> review the change, then run scripts/contracts-lock.sh to re-baseline"
    status=1
  else
    echo "OK: $name"
  fi
done

if [ $status -eq 0 ]; then
  echo ""
  echo "All contracts match their locks."
fi

exit $status
