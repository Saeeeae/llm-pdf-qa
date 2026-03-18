# =============================================================================
# On-Premise RAG-LLM System v2 — Makefile
# =============================================================================

.PHONY: help up up-local up-local-ui down restart ps ps-local logs build clean \
        up-gpu up-infra up-pipeline up-serving up-sync up-frontend \
        logs-pipeline logs-serving logs-sync logs-vllm logs-mineru \
        shell-pipeline shell-serving shell-sync shell-db \
        db-psql db-reset init test lint

# Default
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Docker Compose ──────────────────────────────────────────────────────────

up: ## Start all services (CPU mode)
	docker compose up -d

up-local: ## Start local smoke stack for macOS/Apple Silicon
	docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build \
		postgres redis neo4j pipeline-api pipeline-worker serving-api sync-scheduler frontend

up-local-ui: ## Start minimal local UI/admin stack without MinerU
	docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build \
		postgres redis serving-api frontend

up-gpu: ## Start all services including vLLM (GPU mode)
	docker compose --profile gpu up -d

up-infra: ## Start infrastructure only (PostgreSQL, Neo4j, Redis)
	docker compose -f docker-compose.base.yml up -d

up-pipeline: ## Start pipeline services
	docker compose up -d pipeline-api pipeline-worker mineru-api

up-serving: ## Start serving services
	docker compose up -d serving-api

up-sync: ## Start sync/monitor services
	docker compose up -d sync-scheduler sync-dashboard

up-frontend: ## Start frontend
	docker compose up -d frontend

down: ## Stop all services
	docker compose --profile gpu down

restart: ## Restart all services
	docker compose --profile gpu down && docker compose up -d

build: ## Build all images
	docker compose build

ps: ## Show running containers
	docker compose ps

ps-local: ## Show running containers for local smoke stack
	docker compose -f docker-compose.yml -f docker-compose.local.yml ps

# ─── Logs ─────────────────────────────────────────────────────────────────────

logs: ## Tail all logs
	docker compose logs -f --tail=100

logs-pipeline: ## Tail pipeline logs (API + Worker)
	docker compose logs -f --tail=100 pipeline-api pipeline-worker

logs-serving: ## Tail serving API logs
	docker compose logs -f --tail=100 serving-api

logs-sync: ## Tail sync/monitor logs
	docker compose logs -f --tail=100 sync-scheduler sync-dashboard

logs-vllm: ## Tail vLLM logs
	docker compose logs -f --tail=100 vllm-server

logs-mineru: ## Tail MinerU logs
	docker compose logs -f --tail=100 mineru-api

# ─── Shell Access ─────────────────────────────────────────────────────────────

shell-pipeline: ## Open shell in pipeline-api container
	docker compose exec pipeline-api bash

shell-serving: ## Open shell in serving-api container
	docker compose exec serving-api bash

shell-sync: ## Open shell in sync-scheduler container
	docker compose exec sync-scheduler bash

shell-db: ## Open psql in PostgreSQL container
	docker compose exec postgres psql -U $${POSTGRES_USER:-admin} -d $${POSTGRES_DB:-rag_system}

# ─── Database ─────────────────────────────────────────────────────────────────

db-psql: ## Connect to PostgreSQL via psql
	docker compose exec postgres psql -U $${POSTGRES_USER:-admin} -d $${POSTGRES_DB:-rag_system}

db-reset: ## Reset database (drop + recreate from init.sql)
	@echo "WARNING: This will destroy all data!"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker compose exec postgres psql -U $${POSTGRES_USER:-admin} -c "DROP DATABASE IF EXISTS $${POSTGRES_DB:-rag_system}"
	docker compose exec postgres psql -U $${POSTGRES_USER:-admin} -c "CREATE DATABASE $${POSTGRES_DB:-rag_system}"
	docker compose exec postgres psql -U $${POSTGRES_USER:-admin} -d $${POSTGRES_DB:-rag_system} -f /docker-entrypoint-initdb.d/01_init.sql

# ─── Init ─────────────────────────────────────────────────────────────────────

init: ## First-time setup: copy .env, build, start
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — edit it before starting!")
	docker compose build
	docker compose up -d
	@echo ""
	@echo "Services starting... check with: make ps"
	@echo "Next: edit .env passwords, then run: make restart"

# ─── Development ──────────────────────────────────────────────────────────────

dev-infra: ## Start infra + run services locally
	docker compose -f docker-compose.base.yml up -d
	@echo ""
	@echo "Infrastructure ready. Run services locally:"
	@echo "  uvicorn rag_pipeline.api.main:app --port 8001 --reload"
	@echo "  uvicorn rag_serving.api.main:app --port 8002 --reload"
	@echo "  streamlit run rag_sync_monitor/dashboard/app.py --server.port 8003"
	@echo "  cd frontend && npm run dev"

test: ## Run tests
	python -m pytest tests/ -v

lint: ## Run linter
	python -m ruff check .

# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean: ## Remove all containers, volumes, and images
	@echo "WARNING: This will remove all containers, volumes, and built images!"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker compose --profile gpu down -v --rmi local
