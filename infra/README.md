# infra — Integrated Orchestration

Compose files for the full stack. The recommended entry point is the **root
Makefile** (it sets `ROOT`/`DATA_DIR`/`LOG_DIR` env automatically). Direct
`docker compose` invocations work too if you set those envs yourself.

## Quickstart (recommended — via Makefile)

```bash
make prepare          # create data/db/* and data/logs/* with perm 777
make build            # build all module images
make migrate          # alembic upgrade head (m1, m3)
make run              # start the full stack (real mode)
make ps               # check status
make log s=m1-identity   # tail a specific service
make stop             # stop containers (volumes kept)
make remove           # stop + remove containers AND docker-managed volumes
```

For a single module:

```bash
make run-one m=m1-identity
make stop-one m=m1-identity
make log-one m=m1-identity
```

## Direct docker compose

```bash
# Full stack (real mode)
ROOT=$(pwd) DATA_DIR=$(pwd)/data/db LOG_DIR=$(pwd)/data/logs \
  docker compose --env-file=.env -f infra/docker-compose.yml up -d

# Mock overlay (no LLM/DB calls)
ROOT=$(pwd) DATA_DIR=$(pwd)/data/db LOG_DIR=$(pwd)/data/logs \
  docker compose --env-file=.env \
    -f infra/docker-compose.yml -f infra/docker-compose.mock.yml up -d

# Base infra only (postgres + neo4j + redis)
ROOT=$(pwd) DATA_DIR=$(pwd)/data/db LOG_DIR=$(pwd)/data/logs \
  docker compose --env-file=.env -f infra/docker-compose.base.yml up -d

# Tear down (also removes docker-managed volumes; bind-mounted host data persists)
docker compose --env-file=.env -f infra/docker-compose.yml down -v
```

## Compose file structure

| File | Purpose |
|---|---|
| `docker-compose.base.yml` | postgres + neo4j + redis (bind-mounted to `${DATA_DIR}/...`) |
| `docker-compose.yml` | Full stack — includes `base.yml` + each module's `docker-compose.module.yml` + service-level overrides (depends_on, healthchecks, secrets) |
| `docker-compose.mock.yml` | Overlay setting `MODULE_IMPL=mock` per service |
| `docker-compose.observability.yml` | Prometheus + Grafana + Loki + Promtail + Alertmanager |

Module compose files (`modules/<m>/docker-compose.module.yml`) read
`${ROOT}/.env` as their `env_file` — the SSOT. Don't put values in module
`.env.example`; those are documentation stubs only.

## Ports (host → container)

| Service | Host | Container |
|---------|------|-----------|
| M1 Identity | 8101 | 8000 |
| M2 Doc-to-MD | 8102 | 8000 |
| M3 Chunk/Embed | 8103 | 8000 |
| M4 RAG | 8104 | 8000 |
| M5 Gateway | 8080 | 8000 |
| M7 Admin Backend | 8107 | 8000 |
| M8 Web Search | 8108 | 8000 |
| PostgreSQL | 5432 | 5432 |
| Neo4j HTTP | 7474 | 7474 |
| Neo4j Bolt | 7687 | 7687 |
| Redis | 6379 | 6379 |

## Secrets

`infra/secrets/` holds JWT/PG/Neo4j/Grafana passwords for Docker Compose
secrets. See root [README §3.2](../README.md#32-secrets-생성) for generation.

## Volumes

All persistent data uses **host bind-mount** (not Docker named volumes):
- `${DATA_DIR}/postgres` → `/var/lib/postgresql/data`
- `${DATA_DIR}/neo4j` → `/data` in neo4j container
- `${DATA_DIR}/redis` → `/data` in redis container
- `${DATA_DIR}/m2-state` → `/app/.state` in m2 container
- `${LOG_DIR}/<m>` → `/var/log/<m>` in each module container

`make remove` removes containers but the host bind data persists. Delete
the host directories manually for a true reset.
