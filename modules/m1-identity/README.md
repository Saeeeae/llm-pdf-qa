# M1 Identity

JWT-based authentication service. Issues and validates tokens for all other modules.

- **Port**: 8101
- **Run**: `uvicorn app.main:app --reload --port 8101`
- **Mock**: `MODULE_IMPL=mock uvicorn mocks.mock_server:app --port 8101`
- **Test**: `pytest -q`

## MySQL Sync

Periodic read-only pull from an external MySQL HR system into M1's Postgres. MySQL is **not** managed by docker-compose — provide your own.

### Env vars

| Variable | Default | Description |
|---|---|---|
| `MYSQL_URL` | _(required)_ | `mysql+asyncmy://user:pass@host:3306/db` |
| `MYSQL_TABLE_USERS` | `hr_users` | Override source table name |
| `MYSQL_TABLE_ROLES` | `hr_roles` | Override source table name |
| `MYSQL_TABLE_DEPARTMENTS` | `hr_departments` | Override source table name |
| `MYSQL_SYNC_INTERVAL_MINUTES` | `60` | Sync cadence |
| `MYSQL_SYNC_ON_STARTUP` | `0` | Set `1` to run one sync at boot |
| `MYSQL_SYNC_BATCH_SIZE` | `1000` | Users fetched per SQL page |

### Default schema assumed

`hr_users(id, email, name, department_id, role_id, is_active, password_hash, updated_at)`, `hr_roles(id, name, permissions JSON, description)`, `hr_departments(id, name, parent_id)`. Override table names via env above.

### Fields synced vs preserved

- **Synced**: name, role_id, department_id, is_active, password_hash, external_id, last_synced_at
- **Preserved** (never overwritten): id, created_at, last_login_at, user_preference rows

### Manual trigger

```bash
curl -X POST http://localhost:8101/admin/sync/mysql \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Monitoring

```bash
curl http://localhost:8101/admin/sync/mysql/status \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Password hashes from MySQL (argon2/bcrypt/sha256_crypt/pbkdf2_sha256) are stored verbatim and auto-upgraded to argon2 on next successful login.
