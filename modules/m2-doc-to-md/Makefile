# Module Makefile - m2-doc-to-md (docker-based)
#
# All operational targets delegate to docker compose at the monorepo root,
# using the same compose files as `make build-one m=m2-doc-to-md` from root.
# This guarantees identical behavior whether you run from root or from
# inside the module directory.

MODULE := m2-doc-to-md
ROOT := $(shell git rev-parse --show-toplevel)
export ROOT

DATA_DIR := $(ROOT)/data/db
LOG_DIR := $(ROOT)/data/logs
export DATA_DIR
export LOG_DIR

# No --project-directory: keep default resolution (compose-file-relative)
# so module compose's env_file (../../.env) and build context (../..) work.
# DATA_DIR/LOG_DIR are exported absolutely above, so volume paths are safe.
DC := docker compose \
      --env-file=$(ROOT)/.env \
      -f $(ROOT)/infra/docker-compose.base.yml \
      -f $(ROOT)/modules/$(MODULE)/docker-compose.module.yml

.DEFAULT_GOAL := help

help: ## Show targets
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## .*/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build docker image
	$(DC) build $(MODULE)

run: ## Start service + dependencies (postgres, redis)
	$(DC) up -d $(MODULE)

stop: ## Stop service (volumes kept)
	$(DC) stop $(MODULE)

remove: ## Stop + remove containers and volumes
	$(DC) down -v

log: ## Tail service logs
	$(DC) logs -f $(MODULE)

test: ## Run pytest in a one-shot container
	$(DC) run --rm $(MODULE) python -m pytest tests/ -v

pipeline: ## Run document scan/convert pipeline once (incremental)
	$(DC) run --rm $(MODULE) python -m app.pipeline.run

.PHONY: help build run stop remove log test pipeline
