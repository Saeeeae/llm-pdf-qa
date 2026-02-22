.PHONY: up down build init-db ingest sync status logs clean

# === Docker Compose Commands ===

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

# === Database ===

init-db:
	docker compose exec postgres psql -U $${POSTGRES_USER:-admin} -d $${POSTGRES_DB:-rag_system} \
		-f /docker-entrypoint-initdb.d/01_schema.sql

# === Pipeline Commands ===

ingest:
	docker compose exec celery-worker python -m app.main ingest

ingest-file:
	@test -n "$(FILE)" || (echo "Usage: make ingest-file FILE=/data/documents/example.pdf" && exit 1)
	docker compose exec celery-worker python -m app.main ingest --file $(FILE)

sync:
	docker compose exec celery-worker python -m app.main sync

scan:
	docker compose exec celery-worker python -m app.main scan

scan-pdf:
	docker compose exec celery-worker python -m app.main scan --pattern "**/*.pdf"

scan-ingest:
	docker compose exec celery-worker python -m app.main scan --ingest

status:
	docker compose exec celery-worker python -m app.main status

# === Monitoring ===

logs:
	docker compose logs -f api celery-worker celery-beat

logs-api:
	docker compose logs -f api

logs-worker:
	docker compose logs -f celery-worker celery-beat

logs-all:
	docker compose logs -f

ps:
	docker compose ps

# === Cleanup ===

clean:
	docker compose down -v
	@echo "All volumes removed."
