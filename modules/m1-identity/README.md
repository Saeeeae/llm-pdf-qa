# M1 Identity

JWT-based authentication service. Issues and validates tokens for all other modules.

- **Port (host)**: 8101 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run` (starts service + postgres + redis dependencies)
- **Test**: `make test` (pytest in a one-shot container)
- **Migrate**: `make migrate` (alembic upgrade head — required before first run)
- **Logs**: `make log` (tails container stdout). Persistent JSON logs at `data/logs/m1-identity/m1-identity.log` on host.

Module-only invocation (`cd modules/m1-identity && make run`) is identical to the root delegation (`make run-one m=m1-identity`) — both call the same docker compose with absolute `${ROOT}` paths.

## First-time admin (chicken-and-egg)

The user-create endpoint is RBAC-gated, so a fresh deployment has no admin to create the first admin. Two paths bypass this:

### Auto-bootstrap on startup

Set in root `.env`:
```
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
BOOTSTRAP_ADMIN_PASSWORD=<strong-secret-32+chars>
BOOTSTRAP_ADMIN_NAME=Initial Admin   # optional
```

On startup, if no admin user exists, m1 creates one (idempotent — re-deploys won't reset the user).

### CLI

```bash
make create-admin EMAIL=admin@example.com PASSWORD='strong-secret-32+chars'
make create-admin EMAIL=admin@example.com PASSWORD='new-pw' OVERWRITE=1   # rotate
```

## Operational visibility

```bash
make admin-health TOKEN=<jwt>
```

Returns row counts (users / roles / departments), per-role user distribution, and the most recent SyncRun summary. Useful for "did the bootstrap fire?" / "is the MySQL pull still landing?".

## MySQL Sync

Periodic read-only pull from the in-house HR DB (MySQL) into m1's Postgres. The HR DB is external and **not** managed by docker-compose — operator provides connection details.

### Source schema

The source-of-truth table is `USER_INFO` with the following columns (case-insensitive in MySQL but quoted exactly here):

```
USER_INFO(USER_ID, USER_NAME, LOGIN_PWD, LOGIN_DENY_YN,
          DEPT_ID, DEPT_NAME, CMP_EMAIL,
          POS_ID, POS_NAME, EMP_STATUS)
```

Roles (직급) and departments (부서) are denormalized inside `USER_INFO` — m1 derives them via `SELECT DISTINCT POS_ID/POS_NAME` and `DISTINCT DEPT_ID/DEPT_NAME` rather than querying separate tables. SQL `AS` aliases translate the in-house column names (`USER_ID → id`, `CMP_EMAIL → email`, etc.) to the internal contract consumed by `source_rows.py` / `syncer.py`.

Filters applied at pull time:
- `WHERE EMP_STATUS = 'W'` (재직 중)
- `WHERE POS_ID <> '0'` (정식 직급)
- `LOGIN_DENY_YN = 'Y'` is folded to `is_active = 0`

### Env vars (set in root `.env`)

| Variable | Default | Notes |
|---|---|---|
| `MYSQL_URL` | _(required)_ | `mysql+asyncmy://user:pass@hr-host:3306/hr` |
| `MYSQL_TABLE_USERS` | `USER_INFO` | Override only if your in-house table name differs |
| `MYSQL_SYNC_INTERVAL_MINUTES` | `60` | APScheduler cadence |
| `MYSQL_SYNC_ON_STARTUP` | `0` | `1` triggers one sync at boot |
| `MYSQL_SYNC_BATCH_SIZE` | `1000` | Users fetched per SQL page |
| `MYSQL_POOL_SIZE` | `5` | Connection pool size |
| `MYSQL_POOL_RECYCLE_SECONDS` | `1800` | < MySQL idle timeout (default 8h) |
| `SYNC_LOCK_TTL_SECONDS` | `1800` | Redis SETNX TTL across replicas |

### Password hashing

In-house `LOGIN_PWD` is raw SHA1 hex. m1 verifies SHA1 directly and rotates the hash to argon2 on the user's next successful login (auto-upgrade). Argon2 / bcrypt / sha256_crypt / pbkdf2_sha256 hashes are accepted as-is from any source and auto-upgraded the same way.

### m1 → m2 ordered trigger

After a successful sync (and after the SyncRun row is committed as `success`), m1 POSTs to `${M2_INTERNAL_SYNC_URL}` with `X-Internal-Token: ${INTERNAL_SYNC_TOKEN}`. m2 then runs its own DB pull. Trigger failure is logged but does not change m1's outcome — m2 has its own retry path.

### Manual trigger / status

```bash
# Manual full sync (RBAC-gated: admin.write)
curl -X POST http://localhost:8101/admin/sync/mysql \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Last run + next scheduled time (RBAC-gated: admin.read)
curl http://localhost:8101/admin/sync/mysql/status \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Identity-data snapshot (counts + last sync summary)
curl http://localhost:8101/admin/health \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Fields synced vs preserved

- **Synced**: name, role_id (from POS_ID), department_id (from DEPT_ID), is_active, password_hash, external_id (USER_ID), last_synced_at
- **Preserved** (never overwritten): id, created_at, last_login_at, user_preference rows
