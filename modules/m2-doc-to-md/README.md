# M2 Doc-to-MD

Document ingestion service: scans source directories, converts documents to Markdown via kordoc, and stores state for downstream chunk/embed (M3). Also pulls in-house file metadata (`F0_00001_F`) and folder ACL (`PDiskFolderPermission2`) from MySQL when m1 triggers it.

- **Port (host)**: 8102 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run`
- **Test**: `make test`
- **Pipeline (one-shot)**: `make pipeline` (filesystem scan + convert)
- **Logs**: `make log`. Persistent JSON logs at `data/logs/m2-doc-to-md/`.

## In-house DB sync

Triggered by m1-identity after a successful identity sync (token-gated `POST /internal/sync/mysql`). Pulls:
- `F0_00001_F` from the search server (file metadata + per-file ACL columns)
- `PDiskFolderPermission2` from the HR DB (folder → user-list ACL)

State is persisted to a JSON file at `${M2_STATE_DIR}/sync_state.json`, bind-mounted to `data/db/m2-state/` on host.

Required env (set in root `.env`):
- `INTERNAL_SYNC_TOKEN` (shared with m1)
- `M2_MYSQL_FILE_URL`, `M2_MYSQL_HR_URL`
- `M2_MYSQL_TABLE_FILES`, `M2_MYSQL_TABLE_FOLDER_PERMS` (defaults match in-house tables)

Manual trigger / status:
```bash
curl -X POST http://localhost:8102/internal/sync/mysql \
  -H "X-Internal-Token: $INTERNAL_SYNC_TOKEN"

curl http://localhost:8102/internal/sync/mysql/status \
  -H "X-Internal-Token: $INTERNAL_SYNC_TOKEN"
```
