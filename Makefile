# RAG-LLM 8-Module Monorepo — Root Makefile
# Per-module: cd modules/<m> && make help
# This file: cross-module orchestration only

DC := docker compose
INFRA := -f infra/docker-compose.yml
BASE := -f infra/docker-compose.base.yml
MOCK := -f infra/docker-compose.mock.yml
OBS := -f infra/docker-compose.observability.yml

BACKEND_MODS := m1-identity m2-doc-to-md m3-chunk-embed m4-rag m5-gateway m8-web-search m7-admin/backend
FRONT_MODS := m6-ui m7-admin/frontend
ALL_MODS := $(BACKEND_MODS) $(FRONT_MODS)

.DEFAULT_GOAL := help

help: ## Show targets
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## .*/ {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "  Per-module: cd modules/<m> && make help"

# ─── First-time setup ──────────────────────────────────────────────────────
bootstrap: ## Install shared-py + all backend modules (editable)
	@for m in $(BACKEND_MODS); do $(MAKE) -C modules/$$m install || exit 1; done
	@echo "Done. Run 'make up' or 'make up-mock'."

install-fe: ## npm install for both frontends
	@for m in $(FRONT_MODS); do $(MAKE) -C modules/$$m install || exit 1; done

# ─── Per-module delegation ─────────────────────────────────────────────────
test: ## Run tests in all backend modules
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
migrate: ## Run alembic upgrade head on M1, M3
	@for m in m1-identity m3-chunk-embed; do \
		$(MAKE) -C modules/$$m migrate; \
	done

# ─── Compose orchestration ─────────────────────────────────────────────────
up: ## Full stack (real mode)
	$(DC) $(INFRA) up -d --build

up-mock: ## Full stack (all mock)
	$(DC) $(INFRA) $(MOCK) up -d --build

up-one: ## Single module + base infra (m=m3-chunk-embed)
	$(DC) $(BASE) -f modules/$(m)/docker-compose.module.yml up -d --build

down: ## Stop stack (volumes kept)
	$(DC) $(INFRA) down

down-clean: ## Stop + remove volumes
	$(DC) $(INFRA) down -v

infra-up: ## Postgres + Neo4j + Redis only
	$(DC) $(BASE) up -d

infra-down: ## Stop infra
	$(DC) $(BASE) down

ps: ## docker compose ps
	$(DC) $(INFRA) ps

logs: ## Tail logs (s=m5-gateway)
	$(DC) $(INFRA) logs -f $(s)

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
build-images: ## Build all module docker images
	$(DC) $(INFRA) build

env-check: ## Verify required env vars
	@for v in JWT_SECRET POSTGRES_URL REDIS_URL VLLM_URL; do \
	  test -n "$${!v}" && echo "OK $$v" || echo "MISSING $$v"; \
	done

.PHONY: help bootstrap install-fe test test-fe test-all test-e2e lint fmt clean migrate \
        up up-mock up-one down down-clean infra-up infra-down ps logs \
        contracts contracts-validate contracts-lock contracts-verify \
        obs-up obs-down load-test load-spike \
        backup-pg backup-neo4j backup-all \
        lint-ci security-scan build-images env-check
