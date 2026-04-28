# Module Makefile - m6-ui
NPM ?= npm
PORT ?= 3000
MODULE_NAME = m6-ui

.DEFAULT_GOAL := help

help: ## Show available targets
	@awk 'BEGIN{FS=":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## .*/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## npm install
	$(NPM) install

run: ## Next.js dev server
	$(NPM) run dev

build: ## Production build
	NEXT_PUBLIC_DEV_AUTH=0 $(NPM) run build

start: ## Start production server (after build)
	$(NPM) run start

test: ## Run vitest
	$(NPM) run test

lint: ## eslint + tsc
	$(NPM) run lint
	$(NPM) run typecheck || $(NPM) exec tsc -- --noEmit

fmt: ## prettier
	$(NPM) exec prettier -- --write 'src/**/*.{ts,tsx,css}'

clean: ## Remove .next, node_modules, build artifacts
	rm -rf .next node_modules .turbo dist

# ─── Docker (image baked at build time with NEXT_PUBLIC_API_BASE) ───────────
docker-build: ## Build docker image via compose (honors NEXT_PUBLIC_API_BASE)
	cd ../.. && docker compose -f modules/$(MODULE_NAME)/docker-compose.module.yml build

docker-up: ## Run UI in container (assumes m5-gateway is reachable)
	cd ../.. && docker compose -f modules/$(MODULE_NAME)/docker-compose.module.yml up -d --build

docker-down: ## Stop UI container
	cd ../.. && docker compose -f modules/$(MODULE_NAME)/docker-compose.module.yml down

docker-logs: ## Tail container logs
	cd ../.. && docker compose -f modules/$(MODULE_NAME)/docker-compose.module.yml logs -f

.PHONY: help install run build start test lint fmt clean docker-build docker-up docker-down docker-logs
