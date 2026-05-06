# Module Makefile - m4-rag (docker-based)
MODULE := m4-rag
ROOT := $(shell git rev-parse --show-toplevel)
export ROOT

DATA_ROOT ?= $(ROOT)/data
DATA_DIR := $(DATA_ROOT)/db
LOG_DIR := $(DATA_ROOT)/logs
export DATA_ROOT
export DATA_DIR
export LOG_DIR

DC := docker compose \
      --env-file=$(ROOT)/.env \
      -f $(ROOT)/infra/docker-compose.base.yml \
      -f $(ROOT)/modules/$(MODULE)/docker-compose.module.yml

.DEFAULT_GOAL := help

help: ## Show targets
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## .*/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build docker image
	$(DC) build $(MODULE)

run: ## Start service + dependencies
	$(DC) up -d $(MODULE)

stop: ## Stop service (volumes kept)
	$(DC) stop $(MODULE)

remove: ## Stop + remove containers and volumes
	$(DC) down -v

log: ## Tail service logs
	$(DC) logs -f $(MODULE)

test: ## Run pytest in a one-shot container
	$(DC) run --rm $(MODULE) python -m pytest tests/ -v

.PHONY: help build run stop remove log test
