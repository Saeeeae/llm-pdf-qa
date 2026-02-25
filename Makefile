.PHONY: up down build init-db ingest sync status logs clean init download-models build-beat

# === Setup ===

init:
	@echo "Creating /data directory structure..."
	sudo mkdir -p /data/db/postgres /data/db/redis
	sudo mkdir -p /data/documents
	sudo mkdir -p /data/models/embedding /data/models/mineru /data/models/llm /data/models/vlm
	sudo chown -R $$(id -u):$$(id -g) /data
	@echo "Done. Next: make download-models"

download-models:
	./scripts/download_models.sh all

download-embedding:
	./scripts/download_models.sh embedding

download-mineru:
	./scripts/download_models.sh mineru

# === Docker Compose Commands ===

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

build-api:
	docker compose build api

build-worker:
	docker compose build celery-worker

build-beat:
	docker compose build celery-beat

build-mineru:
	docker compose build mineru-api

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
	docker compose logs -f api celery-worker celery-beat mineru-api

logs-api:
	docker compose logs -f api

logs-worker:
	docker compose logs -f celery-worker celery-beat

logs-mineru:
	docker compose logs -f mineru-api

logs-all:
	docker compose logs -f

ps:
	docker compose ps

# === Cleanup ===

clean:
	docker compose down -v
	@echo "All containers stopped. Note: /data is preserved."

clean-all:
	docker compose down -v
	@echo "WARNING: This does NOT delete /data. To remove: sudo rm -rf /data/db"
