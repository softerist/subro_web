.PHONY: help dev compose-up compose-down logs logs-api logs-worker logs-frontend lint lint-py lint-ts format format-py format-ts test test-py test-ts coverage coverage-py coverage-ts build clean prune permissions

# Default target when no arguments are specified
help:
	@echo "Makefile for Subtitle Downloader Development"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Development Targets:"
	@echo "  dev              - Start the full stack using Docker Compose with hot-reloading (alias for compose-up)."
	@echo "  compose-up       - Start the Docker Compose stack in detached mode."
	@echo "  compose-down     - Stop and remove the Docker Compose stack."
	@echo "  logs             - Tail logs from all running services."
	@echo "  logs-api         - Tail logs specifically from the 'api' service."
	@echo "  logs-worker      - Tail logs specifically from the 'worker' service."
	@echo "  logs-frontend    - Tail logs specifically from the 'frontend' service."
	@echo ""
	@echo "Linting & Formatting:"
	@echo "  lint             - Run all linters via pre-commit on staged files."
	@echo "  lint-all         - Run all linters via pre-commit on all files."
	@echo "  lint-py          - Run Python linters (Ruff) on the backend."
	@echo "  lint-ts          - Run TypeScript/JS linters (ESLint) on the frontend."
	@echo "  format           - Run all formatters (Ruff format, Prettier)."
	@echo "  format-py        - Run Python formatter (Ruff format)."
	@echo "  format-ts        - Run TypeScript/JS formatter (Prettier)."
	@echo ""
	@echo "Testing & Coverage:"
	@echo "  test             - Run backend Python tests (unit & integration)."
	@echo "  test-py          - Run backend Python tests (alias for test)."
	@echo "  test-ts          - Run frontend tests (Vitest/Jest)."
	@echo "  coverage         - Run backend tests and generate coverage report."
	@echo "  coverage-py      - Run backend tests and generate coverage report (alias for coverage)."
	@echo "  coverage-ts      - Run frontend tests and generate coverage report."
	@echo ""
	@echo "Build & Clean:"
	@echo "  build            - Build production Docker images (requires registry login potentially)."
	@echo "  clean            - Remove build artifacts (__pycache__, node_modules, dist, etc.)."
	@echo "  prune            - Remove stopped containers, unused networks, and dangling images."
	@echo "  permissions      - Fix potential file permission issues from Docker volumes (run as sudo)."
	@echo ""

# Variables
COMPOSE_FILES = -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.override.yml
PROJECT_NAME = subapp_dev

# Development Commands
dev: compose-up ## Start the full stack with hot-reloading

rebuild-dev: compose-down # Ensure clean state
	docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.override.yml up -d --build

compose-up: ## Start the Docker Compose stack in detached mode
	@echo "Starting Docker Compose stack..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) up --build --detach

compose-down: ## Stop and remove the Docker Compose stack
	@echo "Stopping Docker Compose stack..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) down -v --remove-orphans

logs: ## Tail logs from all running services
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) logs -f

logs-api: ## Tail logs specifically from the 'api' service
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) logs -f api

logs-worker: ## Tail logs specifically from the 'worker' service
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) logs -f worker

logs-frontend: ## Tail logs specifically from the 'frontend' service
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) logs -f frontend


# Linting & Formatting
lint: ## Run all linters via pre-commit on staged files
	pre-commit run

lint-all: ## Run all linters via pre-commit on all files
	pre-commit run --all-files

lint-py: ## Run Python linters (Ruff) on the backend
	cd backend && poetry run ruff check .

lint-ts: ## Run TypeScript/JS linters (ESLint) on the frontend
	cd frontend && npm run lint

format: format-py format-ts ## Run all formatters

format-py: ## Run Python formatter (Ruff format)
	cd backend && poetry run ruff format .

format-ts: ## Run TypeScript/JS formatter (Prettier)
	cd frontend && npx prettier --write .


# Testing & Coverage
test: test-py ## Run backend Python tests (unit & integration)

test-py: ## Run backend Python tests
	@echo "Running backend tests..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T api poetry run pytest

test-ts: ## Run frontend tests (Vitest/Jest)
	@echo "Running frontend tests..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T frontend npm run test

coverage: coverage-py ## Run backend tests and generate coverage report

coverage-py: ## Run backend tests and generate coverage report
	@echo "Running backend tests with coverage..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T api poetry run pytest --cov=app --cov-report=term-missing --cov-report=html

coverage-ts: ## Run frontend tests and generate coverage report
	@echo "Running frontend tests with coverage..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T frontend npm run coverage


# Build & Clean
build: ## Build production Docker images
	@echo "Building production Docker images..."
	# Ensure correct build context and tagging strategy
	docker build -t subtitle-downloader-api:latest --target production-api ./backend
	docker build -t subtitle-downloader-worker:latest --target production-worker ./backend
	docker build -t subtitle-downloader-frontend:latest --target production ./frontend
	@echo "Note: Production build uses 'latest' tag. Use specific tags for releases."

clean: ## Remove build artifacts
	@echo "Cleaning build artifacts..."
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	rm -rf backend/dist backend/build backend/*.egg-info backend/.pytest_cache backend/.coverage backend/htmlcov backend/.mypy_cache backend/.ruff_cache
	rm -rf frontend/dist frontend/node_modules frontend/coverage frontend/.vite
	@echo "Clean complete."

prune: ## Remove stopped containers, unused networks, and dangling images
	@echo "Pruning Docker system..."
	docker system prune -f
	docker volume prune -f

permissions: ## Fix potential file permission issues from Docker volumes
	@echo "Attempting to fix volume permissions (requires sudo)..."
	sudo chown -R $(shell id -u):$(shell id -g) .
	@echo "Permissions reset to current user."

db-upgrade:
	@echo "Running database migrations..."
	poetry run alembic upgrade head
db-revision:
	@echo "Creating a new database revision..."
	poetry run alembic revision -m "$(REVISION_MSG)"
