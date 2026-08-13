.DEFAULT_GOAL := help
BACKEND := backend
FRONTEND := frontend

.PHONY: help setup setup-backend setup-frontend dev collector api build \
        test lint format typecheck check clean install-services doctor

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: setup-backend setup-frontend ## Install all dependencies

setup-backend: ## Sync the Python backend (uv)
	cd $(BACKEND) && uv sync

setup-frontend: ## Install the frontend (pnpm)
	cd $(FRONTEND) && pnpm install

collector: ## Run the sampling daemon (foreground)
	cd $(BACKEND) && uv run netpulse-collector

api: ## Run the API + dashboard server (foreground)
	cd $(BACKEND) && uv run netpulse-api

dev: ## Run the frontend dev server (proxies /api to :8477)
	cd $(FRONTEND) && pnpm dev

build: ## Build the frontend into frontend/dist (served by the API)
	cd $(FRONTEND) && pnpm build

test: ## Run the backend test suite
	cd $(BACKEND) && uv run pytest -q

lint: ## Lint backend (ruff) + frontend (oxlint)
	cd $(BACKEND) && uv run ruff check .
	cd $(FRONTEND) && pnpm lint

typecheck: ## Type-check backend (mypy) + frontend (tsc)
	cd $(BACKEND) && uv run mypy src
	cd $(FRONTEND) && pnpm typecheck

format: ## Auto-format both sides
	cd $(BACKEND) && uv run ruff format . && uv run ruff check --fix .
	cd $(FRONTEND) && pnpm format

check: lint typecheck test ## Full gate: lint + types + tests

install-services: ## Install & start the systemd --user units
	mkdir -p $$HOME/.config/systemd/user
	cp systemd/netpulse-collector.service systemd/netpulse-api.service $$HOME/.config/systemd/user/
	systemctl --user daemon-reload
	systemctl --user enable --now netpulse-collector.service netpulse-api.service
	@echo "netpulse running at http://127.0.0.1:8477"

doctor: ## Report which optional probe tools are present
	@bash scripts/doctor.sh

clean: ## Remove build output and caches (keeps the DB)
	rm -rf $(FRONTEND)/dist $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache $(BACKEND)/.pytest_cache
