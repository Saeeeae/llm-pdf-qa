# RAG-LLM 8-Module Monorepo — Root Makefile
#
# Build philosophy
#   - Every module ships a Dockerfile + docker-compose.module.yml.
#   - The whole stack is composed via `infra/docker-compose.yml` (uses `include:`).
#   - Persistent state lives outside containers on two host paths:
#       DATA_ROOT  (default /data)   DBs, model cache, markdown, state, logs
#       DATA2_ROOT (default /data2)  raw input documents (read-only mount)
#   - `make data-init` lays out the DATA_ROOT subdirectories.
#   - `make up` builds + starts everything; `make build-images` only builds.
#
# Per-module: cd modules/<m> && make help
DC := docker compose
INFRA := -f infra/docker-compose.yml
BASE := -f infra/docker-compose.base.yml
MOCK := -f infra/docker-compose.mock.yml
OBS := -f infra/docker-compose.observability.yml

DATA_ROOT ?= /data
DATA2_ROOT ?= /data2

BACKEND_MODS := m1-identity m2-doc-to-md m3-chunk-embed m4-rag m5-gateway m8-web-search m7-admin/backend
FRONT_MODS := m6-ui m7-admin/frontend
ALL_MODS := $(BACKEND_MODS) $(FRONT_MODS)

# Compose service names (must match infra/docker-compose.yml)
SERVICES := m1-identity m2-doc-to-md m3-chunk-embed m4-rag m5-gateway m6-ui m7-admin m7-admin-ui m8-web-search

.DEFAULT_GOAL := help

help: ## Show targets
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## .*/ {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "  Storage roots: DATA_ROOT=$(DATA_ROOT) DATA2_ROOT=$(DATA2_ROOT)"
	@echo "  Per-module:    cd modules/<m> && make help"

# ─── First-time setup ──────────────────────────────────────────────────────
bootstrap: ## Install shared-py + all backend modules (editable, host venv)
	@for m in $(BACKEND_MODS); do $(MAKE) -C modules/$$m install || exit 1; done
	@echo "Done. Run 'make data-init && make up' (or 'make up-mock')."

install-fe: ## npm install for both frontends
	@for m in $(FRONT_MODS); do $(MAKE) -C modules/$$m install || exit 1; done

data-init: ## Create DATA_ROOT / DATA2_ROOT directory layout
	@echo "Initializing DATA_ROOT=$(DATA_ROOT) DATA2_ROOT=$(DATA2_ROOT)"
	@for d in db/postgres db/neo4j db/redis models markdown state/m2 logs/m2 logs/m5 logs/m7 logs/m8; do \
	  mkdir -p $(DATA_ROOT)/$$d || (echo "mkdir failed (try: sudo make data-init)"; exit 1); \
	done
	@mkdir -p $(DATA2_ROOT) || (echo "mkdir DATA2_ROOT failed"; exit 1)
	@echo "OK. Drop input documents into $(DATA2_ROOT)/."

secrets-init: ## Generate infra/secrets/{jwt_secret,postgres_password,neo4j_password}
	@mkdir -p infra/secrets
	@for n in jwt_secret postgres_password neo4j_password; do \
	  test -f infra/secrets/$$n || { openssl rand -base64 48 > infra/secrets/$$n && chmod 600 infra/secrets/$$n && echo "wrote infra/secrets/$$n"; }; \
	done

# ─── Per-module delegation ─────────────────────────────────────────────────
test: ## Run tests in all backend modules (host venv)
	@for m in $(BACKEND_MODS); do \
		echo "=== test $$m ==="; \
		$(MAKE) -C modules/$$m test || exit 1; \
	done

test-fe: ## Run tests in both frontends
	@for m in $(FRONT_MODS); do \
		echo "=== test $$m ==="; \
		$(MAKE) -C modules/$$m test || exit 1; \
	done

test-all: test test-fe test-e2e ## All unit + e2e

lint: ## Lint all modules
	@for m in $(ALL_MODS); do \
		echo "=== lint $$m ==="; \
		$(MAKE) -C modules/$$m lint || exit 1; \
	done

fmt: ## Format all modules
	@for m in $(ALL_MODS); do $(MAKE) -C modules/$$m fmt; done

clean: ## Clean all caches
	@for m in $(ALL_MODS); do $(MAKE) -C modules/$$m clean; done

# ─── Migrations ────────────────────────────────────────────────────────────
# Run inside one-shot containers via `docker compose run --rm`. This:
#   - uses the module image (alembic + asyncpg already installed)
#   - resolves `postgres:5432` via the ragnet Docker DNS
#   - waits for the postgres healthcheck via depends_on
#   - cleans up the container after
migrate: ## Run alembic upgrade head on M1 + M3 inside their containers
	$(DC) $(INFRA) up -d postgres
	$(DC) $(INFRA) run --rm m1-identity alembic upgrade head
	$(DC) $(INFRA) run --rm m3-chunk-embed alembic upgrade head

migrate-down: ## Rollback last migration on M1 + M3 (inside containers)
	$(DC) $(INFRA) run --rm m1-identity alembic downgrade -1
	$(DC) $(INFRA) run --rm m3-chunk-embed alembic downgrade -1

migrate-status: ## Show current revision in M1 + M3 DBs
	@echo "── m1-identity ──"; $(DC) $(INFRA) run --rm m1-identity alembic current
	@echo "── m3-chunk-embed ──"; $(DC) $(INFRA) run --rm m3-chunk-embed alembic current

# ─── Build ─────────────────────────────────────────────────────────────────
# Whole-stack and per-module image builds. Uses Compose so build args
# (NEXT_PUBLIC_*, secrets) are honored consistently.
build-images: ## Build all 9 service images (8 modules + m7-admin-ui)
	$(DC) $(INFRA) build

build-one: ## Build one image (m=m3-chunk-embed | m6-ui | m7-admin-ui ...)
	@test -n "$(m)" || (echo "usage: make build-one m=<service-name>"; exit 1)
	$(DC) $(INFRA) build $(m)

build-no-cache: ## Build all images from scratch
	$(DC) $(INFRA) build --no-cache

# ─── Compose orchestration ─────────────────────────────────────────────────
up: data-init secrets-init ## Full stack (real mode); auto-creates DATA_ROOT and secrets
	$(DC) $(INFRA) up -d --build

up-mock: data-init secrets-init ## Full stack (all modules in mock mode)
	$(DC) $(INFRA) $(MOCK) up -d --build

up-one: ## Single module + base infra (m=m3-chunk-embed)
	@test -n "$(m)" || (echo "usage: make up-one m=<module-dir>"; exit 1)
	$(DC) $(BASE) -f modules/$(m)/docker-compose.module.yml up -d --build

down: ## Stop stack (DATA_ROOT bind mounts persist)
	$(DC) $(INFRA) down

down-clean: ## Stop + remove ALL persistent state under DATA_ROOT (DESTRUCTIVE)
	$(DC) $(INFRA) down
	@echo "Removing $(DATA_ROOT) and $(DATA2_ROOT) is intentionally NOT automatic."
	@echo "If you really want to wipe data: rm -rf $(DATA_ROOT)/db $(DATA_ROOT)/markdown $(DATA_ROOT)/state $(DATA_ROOT)/logs $(DATA_ROOT)/models"

infra-up: data-init ## Postgres + Neo4j + Redis only
	$(DC) $(BASE) up -d

infra-down: ## Stop infra
	$(DC) $(BASE) down

ps: ## docker compose ps
	$(DC) $(INFRA) ps

logs: ## Tail logs (s=m5-gateway)
	$(DC) $(INFRA) logs -f $(s)

restart: ## Restart one service (s=m4-rag)
	@test -n "$(s)" || (echo "usage: make restart s=<service>"; exit 1)
	$(DC) $(INFRA) restart $(s)

shell: ## Exec shell into a service (s=m1-identity)
	@test -n "$(s)" || (echo "usage: make shell s=<service>"; exit 1)
	$(DC) $(INFRA) exec $(s) sh

# ─── Contracts ─────────────────────────────────────────────────────────────
contracts: ## YAML syntax validate
	@for f in packages/contracts/*.yaml; do \
		python3 -c "import yaml; yaml.safe_load(open('$$f'))" && echo "OK $$f" || exit 1; \
	done

contracts-validate: ## redocly lint OpenAPI specs
	@for f in packages/contracts/*.yaml; do redocly lint "$$f" --format=stylish || exit 1; done

contracts-lock: ## Update contract SHA256 locks
	bash scripts/contracts-lock.sh

contracts-verify: ## Verify no contract drift
	bash scripts/contracts-verify.sh

# ─── E2E ───────────────────────────────────────────────────────────────────
test-e2e: ## E2E integration tests (requires Docker)
	python3 -m pytest tests-e2e/ -v --tb=short

# ─── Observability + Load ──────────────────────────────────────────────────
obs-up: ## Start Prometheus + Grafana + Loki stack
	$(DC) $(OBS) up -d

obs-down: ## Stop observability stack
	$(DC) $(OBS) down

LOAD_HOST ?= http://localhost:8000

load-test: ## 100u / 200qpm sustained 30min
	locust -f loadtest/locustfile.py --host=$(LOAD_HOST) -u 100 -r 10 -t 30m \
	  --headless --csv=loadtest/results/sustained
	python3 loadtest/analyze.py loadtest/results/sustained

load-spike: ## Spike 0→200 over 30s
	locust -f loadtest/scenarios/spike.py --host=$(LOAD_HOST) \
	  --headless --csv=loadtest/results/spike

# ─── Backup ────────────────────────────────────────────────────────────────
POSTGRES_USER ?= postgres
POSTGRES_DB ?= ragdb

backup-pg: ## pg_dump → backups/
	@mkdir -p backups
	$(DC) $(INFRA) exec -T postgres \
	  pg_dump -U $(POSTGRES_USER) $(POSTGRES_DB) | gzip > backups/postgres_$(shell date +%Y%m%d_%H%M%S).sql.gz

backup-neo4j: ## neo4j-admin dump → backups/
	@mkdir -p backups
	$(DC) $(INFRA) exec -T neo4j \
	  neo4j-admin database dump neo4j --to-stdout > backups/neo4j_$(shell date +%Y%m%d_%H%M%S).dump

backup-all: backup-pg backup-neo4j ## All databases

# ─── CI mirrors ────────────────────────────────────────────────────────────
lint-ci: lint ## (alias)

security-scan: ## bandit + safety + npm audit
	bandit -r modules/ packages/shared-py/ \
	  --exclude modules/m6-ui,modules/m7-admin/frontend -ll -q || true
	safety check --full-report || true
	@for m in $(FRONT_MODS); do npm audit --audit-level=high --prefix modules/$$m || true; done

# ─── Production helpers ─────────────────────────────────────────────────────
env-check: ## Verify required env vars are set in current shell
	@for v in JWT_SECRET POSTGRES_URL REDIS_URL VLLM_URL; do \
	  test -n "$${!v}" && echo "OK $$v" || echo "MISSING $$v"; \
	done

config: ## Render the merged compose config (debugging)
	$(DC) $(INFRA) config

.PHONY: help bootstrap install-fe data-init secrets-init test test-fe test-all test-e2e lint fmt clean \
        migrate migrate-down migrate-status \
        build-images build-one build-no-cache \
        up up-mock up-one down down-clean infra-up infra-down ps logs restart shell config \
        contracts contracts-validate contracts-lock contracts-verify \
        obs-up obs-down load-test load-spike \
        backup-pg backup-neo4j backup-all \
        lint-ci security-scan env-check
