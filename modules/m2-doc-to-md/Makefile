# Module Makefile - m2-doc-to-md
PY ?= python3
PIP ?= pip
PORT ?= 8102
MODULE_NAME = m2-doc-to-md

.DEFAULT_GOAL := help

help: ## Show available targets
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## .*/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install module + shared-py (editable)
	$(PIP) install --break-system-packages -e ../../packages/shared-py
	$(PIP) install --break-system-packages -e .

run: ## Run uvicorn (real mode)
	MODULE_IMPL=real uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

run-mock: ## Run uvicorn (mock mode)
	MODULE_IMPL=mock uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

test: ## Run pytest
	TEST_MODE=1 $(PY) -m pytest tests/ -v

test-cov: ## Run pytest with coverage
	TEST_MODE=1 $(PY) -m pytest tests/ -v --cov=app --cov-report=term-missing

lint: ## ruff check + mypy
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports --no-strict-optional

fmt: ## ruff format
	ruff format app/ tests/

migrate: ## no alembic in this module
	@echo "no alembic"

pipeline: ## Host: incremental pipeline run (requires editable install + /data2 + /data dirs)
	$(PY) -m app.pipeline.run

pipeline-full: ## Host: clear state then run (requires .pipeline_state.json under M2_STATE_DIR or module root)
	rm -f .pipeline_state.json && $(PY) -m app.pipeline.run

docker-pipeline: ## Container: incremental pipeline run inside m2 image (uses mounted /data2)
	cd ../.. && docker compose -f infra/docker-compose.yml run --rm m2-doc-to-md python -m app.pipeline.run

docker-pipeline-full: ## Container: clear state in mounted /data/state then re-run
	cd ../.. && docker compose -f infra/docker-compose.yml run --rm m2-doc-to-md sh -c "rm -f /data/state/.pipeline_state.json && python -m app.pipeline.run"

build: ## Build docker image (uses repo root as context)
	cd ../.. && docker compose -f modules/$(MODULE_NAME)/docker-compose.module.yml build

docker-up: ## Run this module + base infra in containers
	cd ../.. && docker compose -f infra/docker-compose.base.yml -f modules/$(MODULE_NAME)/docker-compose.module.yml up -d --build

docker-down: ## Stop this module's containers
	cd ../.. && docker compose -f modules/$(MODULE_NAME)/docker-compose.module.yml down

docker-logs: ## Tail container logs
	cd ../.. && docker compose -f modules/$(MODULE_NAME)/docker-compose.module.yml logs -f

clean: ## Remove caches and build artifacts
	rm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache *.egg-info build dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.PHONY: help install run run-mock test test-cov lint fmt migrate pipeline pipeline-full docker-pipeline docker-pipeline-full build docker-up docker-down docker-logs clean
