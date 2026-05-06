# Module Makefile - m1-identity (docker-based)
#
# All operational targets delegate to docker compose at the monorepo root,
# using the same compose files as `make build-one m=m1-identity` from root.
# This guarantees identical behavior whether you run from root or from
# inside the module directory.

MODULE := m1-identity
ROOT := $(shell git rev-parse --show-toplevel)
export ROOT

DATA_ROOT ?= $(ROOT)/data
DATA_DIR := $(DATA_ROOT)/db
LOG_DIR := $(DATA_ROOT)/logs
export DATA_ROOT
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

migrate: ## alembic upgrade head (in container)
	$(DC) run --rm $(MODULE) alembic upgrade head

create-admin: ## Create admin (EMAIL=a@b.com PASSWORD=secret [NAME=Admin] [OVERWRITE=1])
	@test -n "$(EMAIL)" || (echo "EMAIL required"; exit 1)
	@test -n "$(PASSWORD)" || (echo "PASSWORD required"; exit 1)
	$(DC) run --rm $(MODULE) python -m app.cli create-admin \
	  --email "$(EMAIL)" --password "$(PASSWORD)" \
	  $(if $(NAME),--name "$(NAME)") \
	  $(if $(OVERWRITE),--overwrite)

admin-health: ## Curl /admin/health from host (TOKEN=<jwt>)
	@test -n "$(TOKEN)" || (echo "TOKEN=<admin jwt> required"; exit 1)
	curl -fsS -H "Authorization: Bearer $(TOKEN)" http://localhost:8101/admin/health | python -m json.tool

.PHONY: help build run stop remove log test migrate create-admin admin-health
