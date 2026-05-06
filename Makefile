# RAG-LLM 8-Module Monorepo — Root Makefile (docker-only)
#
# Standard ops vocabulary: build / run / stop / remove / log
#   - root targets operate on the full stack
#   - per-module targets delegate to modules/<m>/Makefile (m=m1-identity)
# Per-module: cd modules/<m> && make help

ROOT := $(CURDIR)
export ROOT

DATA_DIR ?= $(ROOT)/data/db
LOG_DIR ?= $(ROOT)/data/logs
export DATA_DIR
export LOG_DIR

# Root-level: don't use --project-directory because infra/docker-compose.yml
# uses `include:` directives whose paths resolve relative to the compose file.
# Volume paths use absolute DATA_DIR/LOG_DIR exported above, so no relative
# resolution surprises.
DC := docker compose --env-file=$(ROOT)/.env
INFRA := -f $(ROOT)/infra/docker-compose.yml
BASE := -f $(ROOT)/infra/docker-compose.base.yml
MOCK := -f $(ROOT)/infra/docker-compose.mock.yml
OBS := -f $(ROOT)/infra/docker-compose.observability.yml

BACKEND_MODS := m1-identity m2-doc-to-md m3-chunk-embed m4-rag m5-gateway m8-web-search m7-admin/backend
FRONT_MODS := m6-ui m7-admin/frontend
ALL_MODS := $(BACKEND_MODS) $(FRONT_MODS)

.DEFAULT_GOAL := help

help: ## Show targets
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## .*/ {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "  Per-module: cd modules/<m> && make help"

# ─── Host data directories ─────────────────────────────────────────────────
prepare: ## Create host data dirs (postgres/neo4j/redis/logs) with permissive perms
	@mkdir -p $(DATA_DIR)/postgres $(DATA_DIR)/neo4j $(DATA_DIR)/redis $(DATA_DIR)/m2-state
	@for m in $(BACKEND_MODS); do mkdir -p $(LOG_DIR)/$$m; done
	@chmod -R 777 $(DATA_DIR) $(LOG_DIR)
	@echo "Host dirs ready: DATA_DIR=$(DATA_DIR) LOG_DIR=$(LOG_DIR)"

# ─── Full stack ────────────────────────────────────────────────────────────
build: ## Build all module images
	$(DC) $(INFRA) build

run: prepare ## Start full stack (real mode)
	$(DC) $(INFRA) up -d

run-mock: prepare ## Start full stack (mock overlay)
	$(DC) $(INFRA) $(MOCK) up -d

stop: ## Stop full stack (volumes kept)
	$(DC) $(INFRA) stop

remove: ## Stop + remove containers and volumes
	$(DC) $(INFRA) down -v

log: ## Tail logs (s=m5-gateway for one service)
	$(DC) $(INFRA) logs -f $(s)

ps: ## docker compose ps
	$(DC) $(INFRA) ps

# ─── Single module + base infra ────────────────────────────────────────────
build-one: ## Build one module (m=m1-identity)
	@$(MAKE) -C modules/$(m) build

run-one: prepare ## Run one module + base infra (m=m1-identity)
	@$(MAKE) -C modules/$(m) run

stop-one: ## Stop one module (m=m1-identity)
	@$(MAKE) -C modules/$(m) stop

remove-one: ## Remove one module (m=m1-identity)
	@$(MAKE) -C modules/$(m) remove

log-one: ## Tail logs for one module (m=m1-identity)
	@$(MAKE) -C modules/$(m) log

# ─── Base infra only ───────────────────────────────────────────────────────
infra-up: prepare ## Start postgres + neo4j + redis only
	$(DC) $(BASE) up -d

infra-down: ## Stop base infra
	$(DC) $(BASE) down

# ─── Migrations (in container) ─────────────────────────────────────────────
migrate: ## Alembic upgrade head for DB-backed modules (m1, m3)
	@for m in m1-identity m3-chunk-embed; do $(MAKE) -C modules/$$m migrate; done

# ─── Backups ───────────────────────────────────────────────────────────────
backup-pg: ## pg_dump → backups/
	@mkdir -p backups
	$(DC) $(INFRA) exec -T postgres \
	  pg_dump -U $${POSTGRES_USER:-postgres} $${POSTGRES_DB:-ragdb} | gzip > backups/postgres_$$(date +%Y%m%d_%H%M%S).sql.gz

backup-neo4j: ## neo4j-admin dump → backups/
	@mkdir -p backups
	$(DC) $(INFRA) exec -T neo4j \
	  neo4j-admin database dump neo4j --to-stdout > backups/neo4j_$$(date +%Y%m%d_%H%M%S).dump

backup-all: backup-pg backup-neo4j ## All databases

# ─── Observability ─────────────────────────────────────────────────────────
obs-up: ## Start prometheus + grafana + loki
	$(DC) $(OBS) up -d

obs-down: ## Stop observability stack
	$(DC) $(OBS) down

.PHONY: help prepare build run run-mock stop remove log ps \
        build-one run-one stop-one remove-one log-one \
        infra-up infra-down migrate \
        backup-pg backup-neo4j backup-all \
        obs-up obs-down
