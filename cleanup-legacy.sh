#!/usr/bin/env bash
# Delete legacy directories/files after 7-module restructure.
# Run this ONCE from the repo root, then delete this script.
# All content is replaced by packages/, modules/, infra/, Makefile, README.md.
set -euo pipefail
cd "$(dirname "$0")"

LEGACY_DIRS=(
  mineru
  rag-pipeline
  rag-serving
  rag-sync-monitor
  rag_pipeline
  rag_serving
  rag_sync_monitor
  shared
  frontend
  tests
  scripts
  eval
)

LEGACY_FILES=(
  Dockerfile.mineru
  CHECK.md
  docker-compose.yml
  docker-compose.base.yml
  docker-compose.local.yml
  .dockerignore
)
# Note: Makefile and README.md already replaced with new 7-module versions.
# Only delete Makefile.v2 / README.v2.md if they still exist (leftover).

echo "=== Deleting legacy directories ==="
for d in "${LEGACY_DIRS[@]}"; do
  [ -d "$d" ] && rm -rf "$d" && echo "  rm -rf $d" || echo "  skip $d (not present)"
done

echo ""
echo "=== Deleting legacy files ==="
for f in "${LEGACY_FILES[@]}"; do
  [ -f "$f" ] && rm -f "$f" && echo "  rm $f" || echo "  skip $f (not present)"
done

echo ""
echo "=== Cleaning up any leftover v2 files ==="
[ -f Makefile.v2 ] && rm -f Makefile.v2 && echo "  rm Makefile.v2 (already active as Makefile)"
[ -f README.v2.md ] && rm -f README.v2.md && echo "  rm README.v2.md (already active as README.md)"

echo ""
echo "=== Done ==="
echo "Remaining top-level entries:"
ls -1
