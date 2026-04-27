# Module Makefile - m7-admin-frontend
NPM ?= npm
PORT ?= 3001
MODULE_NAME = m7-admin-frontend

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

docker-build: ## Build docker image
	docker build -t rag-$(MODULE_NAME):local .

.PHONY: help install run build start test lint fmt clean docker-build
