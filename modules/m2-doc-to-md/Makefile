# Module Makefile - m2-doc-to-md
PY ?= python3
PIP ?= pip
PORT ?= 8002
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

pipeline: ## Run document-to-markdown pipeline once (incremental)
	$(PY) -m app.pipeline.run

pipeline-full: ## Force full re-run (clears state)
	rm -f .pipeline_state.json && $(PY) -m app.pipeline.run

build: ## Build docker image
	docker build -t rag-$(MODULE_NAME):local .

clean: ## Remove caches and build artifacts
	rm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache *.egg-info build dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.PHONY: help install run run-mock test test-cov lint fmt migrate pipeline pipeline-full build clean
