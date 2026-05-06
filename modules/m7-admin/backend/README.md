# M7 Admin Backend

Administration API: system health aggregation, audit log, and metrics endpoint.

- **Port (host)**: 8107 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run`
- **Test**: `make test`
- **Logs**: `make log`

DB driver: m7 uses SQLAlchemy async with asyncpg. The shared root `.env` provides `POSTGRES_URL` (psycopg, sync) which m7 auto-converts; if you want explicit asyncpg, set `POSTGRES_ASYNC_URL` or `POSTGRES_RO_URL` (read-only replica). Resolution order: `POSTGRES_RO_URL` → `POSTGRES_ASYNC_URL` → `POSTGRES_URL` (auto-converted to asyncpg).
