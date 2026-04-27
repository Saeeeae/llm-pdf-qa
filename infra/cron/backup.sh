#!/usr/bin/env bash
# Daily backup + 30-day local retention.
# Typical crontab entry (run as the user who owns docker socket):
#   0 2 * * * /path/to/repo/infra/cron/backup.sh >> /var/log/rag-backup.log 2>&1
set -euo pipefail

# Resolve repo root regardless of where cron calls this script from.
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting backup..."
make backup-all

# Prune local backups older than 30 days.
find backups/ -name 'postgres_*.sql.gz' -mtime +30 -delete
find backups/ -name 'neo4j_*.dump'      -mtime +30 -delete

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup complete. Consider syncing backups/ to S3/GCS for offsite retention."
