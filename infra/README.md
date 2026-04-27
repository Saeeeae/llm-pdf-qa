# infra — Integrated Orchestration

## Quickstart

```bash
# Start full system (real mode)
docker compose -f infra/docker-compose.yml up

# Start with mock modules (no LLM/DB calls)
docker compose -f infra/docker-compose.yml -f infra/docker-compose.mock.yml up

# Start only base infra (postgres, neo4j, redis)
docker compose -f infra/docker-compose.base.yml up

# Tear down
docker compose -f infra/docker-compose.yml down -v
```

## Ports

| Service | Port |
|---------|------|
| M1 Identity | 8101 |
| M2 Doc-to-MD | 8102 |
| M3 Chunk/Embed | 8103 |
| M4 RAG | 8104 |
| M5 Gateway | 8080 |
| M7 Admin Backend | 8107 |
| PostgreSQL | 5432 |
| Neo4j HTTP | 7474 |
| Neo4j Bolt | 7687 |
| Redis | 6379 |
