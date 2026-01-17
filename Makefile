# ==============================================================================
# Variables
# ==============================================================================
PROJECT_NAME ?= subapp_dev
BASE_COMPOSE_FILE := infra/docker/docker-compose.yml
OVERRIDE_COMPOSE_FILE := infra/docker/docker-compose.override.yml
COMPOSE_FILES := --env-file .env -f $(BASE_COMPOSE_FILE) -f $(OVERRIDE_COMPOSE_FILE)

# Test Configuration
TEST_API_BASE_URL ?= http://localhost:8000
TEST_WS_BASE_URL ?= ws://localhost:8000
UID := $(shell id -u)
GID := $(shell id -g)
API_PORT_HOST ?= 8001
FRONTEND_PORT_HOST ?= 5174

# ==============================================================================
# Help Target
# ==============================================================================
.PHONY: help
help: ## Show help for Makefile targets
	@echo "Makefile for Subtitle Downloader Development"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Common Development Targets:"
	@echo "  dev                - Start/restart the full stack (uses existing volumes, hot-reloading)."
	@echo "  rebuild-dev        - Clean rebuild: stop, wipe volumes, migrate DB, then start fresh."
	@echo "  compose-up         - Start the Docker Compose stack in detached mode (builds if necessary)."
	@echo "  compose-down       - Stop and remove Docker Compose stack AND volumes."
	@echo "  compose-down-keep-volumes - Stop and remove Docker Compose stack, but KEEP volumes."
	@echo ""
	@echo "Database Migration Targets (run inside Docker):"
	@echo "  db-migrate         - Apply pending Alembic migrations to the Dockerized database."
	@echo "  db-makemigrations  - Create a new Alembic revision file (interactive)."
	@echo ""
	@echo "Logging Targets:"
	@echo "  logs               - Tail logs from all running services."
	@echo "  logs-api           - Tail logs specifically from the 'api' service."
	@echo "  logs-worker        - Tail logs specifically from the 'worker' service."
	@echo "  logs-frontend      - Tail logs specifically from the 'frontend' service."
	@echo ""
	@echo "Linting & Formatting Targets:"
	@echo "  lint               - Run all linters via pre-commit on staged files."
	@echo "  lint-all           - Run all linters via pre-commit on all files."
	@echo "  lint-py            - Run Python linters (Ruff) on the backend."
	@echo "  lint-ts            - Run TypeScript/JS linters (ESLint) on the frontend."
	@echo "  format             - Run all formatters (Ruff format, Prettier)."
	@echo "  format-py          - Run Python formatter (Ruff format)."
	@echo "  format-ts          - Run TypeScript/JS formatter (Prettier)."
	@echo ""
	@echo "Testing & Coverage Targets (run inside Docker):"
	@echo "  test               - Run backend Python tests."
	@echo "  test-py            - Run backend Python tests (alias for test)."
	@echo "  test-ts            - Run frontend tests."
	@echo "  coverage           - Run backend tests and generate coverage report."
	@echo "  coverage-py        - Run backend tests and generate coverage report (alias for coverage)."
	@echo "  coverage-ts        - Run frontend tests and generate coverage report."
	@echo "  test-integration   - Run integration tests inside dev container."
	@echo "  test-integration-prod - Run integration tests inside prod container."
	@echo ""
	@echo "Build & Clean Targets:"
	@echo "  build              - Build production Docker images."
	@echo "  clean              - Remove build artifacts (__pycache__, node_modules, dist, etc.)."
	@echo "  prune              - Remove stopped containers, unused networks, and dangling images/volumes."
	@echo "  permissions        - Fix potential file permission issues from Docker volumes (run as sudo)."
	@echo "  scan-vulns         - Scan production images for vulnerabilities (Trivy)."
	@echo "  scan-secrets       - Scan filesystem for secrets (Trivy)."
	@echo "  scan-sast          - Scan code for security issues (Semgrep)."
	@echo "  scan-all           - Run all local security scans."
	@echo ""
	@echo "Local Alembic Commands (run against DB defined by local .env, not Dockerized DB):"
	@echo "  local-db-upgrade   - (DEPRECATED-STYLE) Run Alembic upgrade head locally."
	@echo "  local-db-revision MSG=\"your_message\" - (DEPRECATED-STYLE) Create Alembic revision locally."


# Near the top with other variables if you like
PYTHON_MIGRATION_FILES_EXIST := $(shell find backend/alembic/versions -maxdepth 1 -name '*.py' -not -name '__init__.py' -print -quit)

# ==============================================================================
# Development Docker Commands
# ==============================================================================
# THIS IS THE SECTION WHERE THE OLD 'dev' WAS. IT'S NOW GONE.
# The .PHONY for dev is handled by the later definition.
# We still keep the other .PHONY targets from the old block if they are unique.
.PHONY: rebuild-dev compose-up compose-down compose-down-keep-volumes ensure-dev-cleanup ensure-test-db

stop-prod: ## Stop production stacks to free up ports
	@echo "Stopping production stacks (if running)..."
	-docker compose -p infra -f infra/docker/compose.gateway.yml -f infra/docker/compose.data.yml down 2>/dev/null || true
	-docker compose -p blue -f infra/docker/compose.prod.yml down 2>/dev/null || true
	-docker compose -p green -f infra/docker/compose.prod.yml down 2>/dev/null || true

# rebuild-dev now correctly depends on the later 'dev' implicitly through compose-up if needed,
# or you might adjust its dependencies if 'ensure-migrations' logic should also apply here.
# For now, let's assume its current dependencies are fine.
rebuild-dev: ensure-dev-cleanup compose-down db-migrate compose-up ensure-test-db ## Clean rebuild: stop, wipe volumes, migrate, then start fresh
	@echo "Running migrations..."
	@make db-migrate
	@echo "Development stack fully rebuilt and started."
	@echo "Gateway (Caddy HTTP)  available at http://localhost:8090"
	@echo "Gateway (Caddy HTTPS) available at https://localhost:8444"
	@echo "API available at http://localhost:$(API_PORT_HOST)"
	@echo "API Docs available at http://localhost:$(API_PORT_HOST)/api/v1/docs"
	@echo "Frontend available at http://localhost:$(FRONTEND_PORT_HOST)"

ensure-test-db: ## Ensure test database exists on db_test container
	@echo "Ensuring test database exists..."
	@docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T db_test sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "SELECT 1 FROM pg_database WHERE datname='\''$${POSTGRES_DB}_pytest'\''" | grep -q 1' || \
		docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T db_test sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "CREATE DATABASE \"$${POSTGRES_DB}_pytest\";"' 2>/dev/null || true
	@echo "Test database ready."

compose-up: ## Start the Docker Compose stack in detached mode (builds if necessary)
	@echo "Starting Docker Compose stack..."
	@echo "Rebuilding frontend to ensure npm packages are up to date..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) build frontend
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) up --build --detach

compose-down: ## Stop and remove the Docker Compose stack AND volumes
	@echo "Stopping Docker Compose stack and removing volumes..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) down -v --remove-orphans

compose-down-keep-volumes: ## Stop and remove Docker Compose stack, but KEEP volumes
	@echo "Stopping Docker Compose stack, keeping volumes..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) down --remove-orphans

ensure-dev-cleanup: ## Remove conflicting containers/ports before dev/prod starts
	@echo "Ensuring no conflicting dev containers or ports are in use..."
	@conflicting=$$(docker ps -aq --filter "name=$(PROJECT_NAME)_db"); \
	conflicting_alt=$$(docker ps -aq --filter "name=$(PROJECT_NAME)-db"); \
	set -- $$conflicting $$conflicting_alt; \
	if [ $$# -gt 0 ]; then \
		echo "Removing conflicting DB containers: $$*"; \
		docker rm -f $$@; \
	fi
	@conflicting_test=$$(docker ps -aq --filter "name=$(PROJECT_NAME)_db_test"); \
	conflicting_test_alt=$$(docker ps -aq --filter "name=$(PROJECT_NAME)-db_test"); \
	set -- $$conflicting_test $$conflicting_test_alt; \
	if [ $$# -gt 0 ]; then \
		echo "Removing conflicting test DB containers: $$*"; \
		docker rm -f $$@; \
	fi
	@# Cleanup Redis (6379), Postgres (5432), and Test Postgres (5433)
	@for port in 6379 5432 5433; do \
		conflicting=$$(docker ps -q --filter "publish=$$port"); \
		if [ -n "$$conflicting" ]; then \
			echo "Stopping containers using port $$port: $$conflicting"; \
			docker stop $$conflicting; \
		fi; \
	done

# ==============================================================================
# Logging
# ==============================================================================
.PHONY: logs logs-api logs-worker logs-frontend
logs: ## Tail logs from all running services
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) logs -f

logs-api: ## Tail logs specifically from the 'api' service
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) logs -f api

logs-worker: ## Tail logs specifically from the 'worker' service
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) logs -f worker

logs-frontend: ## Tail logs specifically from the 'frontend' service
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) logs -f frontend
# ==============================================================================
# Database Migrations (Dockerized)
# ==============================================================================

.PHONY: db-migrate db-makemigrations db-apply-migration restart-api db-migrate-and-apply

db-migrate: ## Apply pending Alembic migrations to the Dockerized database
	@echo "Applying database migrations..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) \
		run --rm \
		--entrypoint "" api \
		poetry run alembic upgrade head
	@echo "Migrations applied. You may need to restart dependent services (e.g., 'make restart-api')."
	@echo "IMPORTANT: Review the migration file in backend/alembic/versions/ before applying it."

db-makemigrations: ## Create new Alembic migration file based on model changes
	@echo "Creating new Alembic revision..."
	@read -p "Enter migration message: " msg_val; \
	echo "Migration message will be: '$${msg_val}'"; \
	MIGRATION_MESSAGE_FOR_ALEMBIC="$${msg_val}" docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) \
		run --rm \
		--user "0:0" \
		-e MIGRATION_MESSAGE_FOR_ALEMBIC \
		-e PYTHONPATH=/app \
		-v $(shell pwd)/backend:/app \
		--entrypoint /bin/sh \
		api \
		-c 'cd /app && poetry run alembic revision --autogenerate -m "$$MIGRATION_MESSAGE_FOR_ALEMBIC"'
	@echo "New revision created in backend/alembic/versions/. Please review and edit it."
	@echo "IMPORTANT: Run 'make db-apply-migration' to apply changes, then restart services if needed."

db-apply-migration: ## Apply pending Alembic migrations explicitly
	@echo "Applying database migrations explicitly..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) \
		run --rm \
		--entrypoint "" api \
		poetry run alembic upgrade head
	@echo "Migrations applied. You may need to restart dependent services (e.g., 'make restart-api')."
	@echo "IMPORTANT: Review the migration file in backend/alembic/versions/ before applying it."

restart-api: ## Restart the API service
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) restart api
	@echo "API service restarted."
	@echo "Note: If you made changes to the database schema, consider running 'make db-migrate' to apply migrations."

db-migrate-and-apply: db-makemigrations db-apply-migration ## Generate migration and apply it immediately
	@echo "Migration created and applied. You may need to restart dependent services (e.g., 'make restart-api')."
	@echo "IMPORTANT: Review the migration file in backend/alembic/versions/ before applying it."


.PHONY: dev ensure-migrations stop-prod prod reset-prod add-test-statistics reset-prod-with-stats reset-dev reset-dev-db add-test-statistics-dev reset-dev-with-stats rebuild-prod rebuild-dev-with-stats rebuild-prod-with-stats
dev: stop-prod ensure-dev-cleanup ensure-migrations compose-up db-migrate ## Start the full stack (generates initial migration if needed, uses existing volumes)
	@echo "Development stack is up."
	@echo "Gateway (Caddy HTTP)  available at http://localhost:8090"
	@echo "Gateway (Caddy HTTPS) available at https://localhost:8444"
	@echo "API available at http://localhost:$(API_PORT_HOST)"
	@echo "API Docs available at http://localhost:$(API_PORT_HOST)/api/v1/docs"
	@echo "Frontend available at http://localhost:$(FRONTEND_PORT_HOST)"

# New helper target
ensure-migrations:
	@if [ -z "$(PYTHON_MIGRATION_FILES_EXIST)" ]; then \
		echo "No migration files found in backend/alembic/versions/."; \
		echo "Running initial migration generation..."; \
		make db-makemigrations MSG="Initial migration auto-generated by make dev"; \
		echo "Initial migration generated."; \
	else \
		echo "Migration files found. Skipping generation."; \
	fi

prod: ensure-dev-cleanup ## Deploy to production using blue-green deployment script
	@echo "Deploying to production..."
	chmod +x ./infra/scripts/blue_green_deploy.sh
	./infra/scripts/blue_green_deploy.sh
	@echo "Production stack deployed."
	@echo ""
	@echo "Installing/updating fail2ban security..."
	-@$(MAKE) fail2ban-install 2>/dev/null || echo "Note: fail2ban-install requires sudo. Run 'make fail2ban-install' manually if needed."
	@echo ""
	@echo "Gateway (Caddy HTTP)  available at http://localhost:8080"
	@echo "Gateway (Caddy HTTPS) available at https://localhost:8443"
	@echo "API Docs are MASKED for security. Access via your secret path defined in .env.prod"

prod-skip-reencrypt: ensure-dev-cleanup ## Deploy to production skipping re-encryption (faster)
	@echo "Deploying to production (skipping re-encryption)..."
	REENCRYPT_ON_DEPLOY=0 ./infra/scripts/blue_green_deploy.sh
	@echo "Production stack deployed (Fast)."
	@echo "Gateway (Caddy HTTP)  available at http://localhost:8080"
	@echo "Gateway (Caddy HTTPS) available at https://localhost:8443"
	@echo "API Docs are MASKED for security. Access via your secret path defined in .env.prod"

prod-hardened: ensure-dev-cleanup ## Deploy with security hardening (read-only fs, capability dropping)
	@echo "Deploying hardened production stack..."
	docker compose --env-file infra/.env.prod -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.prod.yml \
		--project-name subapp_prod up --build --detach
	@echo "Hardened production stack deployed."
	@echo "Gateway (Caddy HTTP)  available at http://localhost:8090"
	@echo "API Docs are MASKED for security. Access via your secret path defined in .env.prod"

reset-prod: rebuild-prod ## Alias for rebuild-prod

rebuild-prod: ## DESTRUCTIVE: Stop production, WIPE database, and redeploy
	@echo "WARNING: This will DELETE ALL DATA in the production database."
	@echo "Cleaning up existing containers (if any)..."
	@docker rm -f infra-caddy-1 infra-db-1 infra-redis-1 infra-backup-1 infra-scheduler-1 green-api-1 green-worker-1 green-frontend-1 blue-api-1 blue-worker-1 blue-frontend-1 2>/dev/null || true
	@echo "Removing network to clear locks..."
	@docker network rm infra_internal_net || true
	@echo "Wiping database volume..."
	@docker volume rm infra_postgres_data || true
	@echo "Restarting infrastructure..."
	@docker compose -f infra/docker/compose.data.yml -f infra/docker/compose.gateway.yml -p infra up -d
	@echo "Running migrations..."
	@# Wait for DB to be ready before migrating
	@sleep 5
	@docker compose --env-file infra/.env.prod -p infra -f infra/docker/compose.prod.yml run --rm --entrypoint "" api poetry run alembic upgrade head
	@echo "Redeploying application..."
	@# Explicitly set --env-file to ensure build args like VITE_API_BASE_URL are picked up
	@docker compose --env-file infra/.env.prod -p blue -f infra/docker/compose.prod.yml build --pull
	@docker compose --env-file infra/.env.prod -p blue -f infra/docker/compose.prod.yml up -d
	@echo "Database reset complete. Please visit the Onboarding page."
	@echo "Gateway (Caddy HTTP)  available at http://localhost:8080"
	@echo "Gateway (Caddy HTTPS) available at https://localhost:8443"
	@echo "Onboarding Page:      https://localhost:8443/onboarding"

add-test-statistics: ## Populate translation_log and deepl_usage tables from /app/logs/translation_log.json
	@echo "Copying and running population script..."
	@docker cp backend/scripts/populate_db_from_json.py blue-api-1:/app/scripts/
	@docker exec -u appuser blue-api-1 python3 scripts/populate_db_from_json.py
	@echo "Test statistics populated."

reset-prod-with-stats: reset-prod add-test-statistics ## Reset prod database AND populate test statistics

rebuild-prod-with-stats: rebuild-prod add-test-statistics ## Rebuild prod AND populate test statistics

reset-dev: reset-dev-db ## Alias for reset-dev-db

reset-dev-db: rebuild-dev ## Reset dev database (rebuild-dev already wipes volumes)

add-test-statistics-dev: ## Populate translation_log and deepl_usage tables for DEV
	@echo "Copying and running population script for DEV..."
	@docker cp backend/scripts/populate_db_from_json.py subapp_dev-api-1:/app/scripts/
	@docker exec -u appuser subapp_dev-api-1 python3 scripts/populate_db_from_json.py
	@echo "Dev test statistics populated."

reset-dev-with-stats: reset-dev add-test-statistics-dev ## Reset dev database AND populate test statistics

rebuild-dev-with-stats: rebuild-dev add-test-statistics-dev ## Rebuild dev AND populate test statistics



# ==============================================================================
# Linting & Formatting (Run locally)
# ==============================================================================
.PHONY: lint lint-all lint-py lint-ts format format-py format-ts
lint: ## Run all linters via pre-commit on staged files
	pre-commit run

lint-all: ## Run all linters via pre-commit on all files
	pre-commit run --all-files

lint-py: ## Run Python linters (Ruff) and type checker (Mypy) on the backend
	cd backend && poetry run ruff check . && poetry run mypy .

lint-ts: ## Run TypeScript/JS linters (ESLint) on the frontend
	cd frontend && npm run lint -- --fix

format: format-py format-ts ## Run all formatters

format-py: ## Run Python formatter (Ruff format)
	cd backend && poetry run ruff format .

format-ts: ## Run TypeScript/JS formatter (Prettier)
	cd frontend && npx prettier --write .


# ==============================================================================
# Testing & Coverage (Run inside Docker)
# ==============================================================================
.PHONY: test test-py test-ts test-integration test-integration-prod coverage coverage-py coverage-ts test-audit
test: test-py scan-all ## Run backend Python tests, security scans, and type checks
	cd backend && poetry run mypy .

test-py: ## Run backend Python tests
	@echo "Running backend tests..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T api poetry run pytest

test-ts: ## Run frontend tests
	@echo "Running frontend tests..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T frontend npm run test

test-audit: ## Run audit and security focused tests
	@echo "Running audit focused tests..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T api poetry run pytest \
		tests/api/test_audit.py \
		tests/api/test_audit_integration.py \
		tests/unit/tasks/test_maintenance.py \
		tests/unit/services/test_security_audit.py \
		tests/unit/test_audit_service.py \
		tests/unit/services/test_security_lockout.py -v

coverage: coverage-py ## Run backend tests and generate coverage report

coverage-py: ## Run backend tests and generate coverage report
	@echo "Running backend tests with coverage..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T api poetry run pytest --cov=app --cov-report=term-missing --cov-report=html

coverage-ts: ## Run frontend tests and generate coverage report
	@echo "Running frontend tests with coverage..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T frontend npm run coverage

test-integration: ## Run integration tests inside dev container (requires dev stack running)
	@echo "Running integration tests inside dev container..."
	docker compose $(COMPOSE_FILES) --project-name $(PROJECT_NAME) exec -T \
		-e TEST_API_BASE_URL=http://localhost:8000 \
		-e TEST_WS_BASE_URL=$(TEST_WS_BASE_URL) \
		api poetry run pytest tests/integration/ -v --tb=short

test-integration-prod: ## Run integration tests inside prod container (requires prod stack running)
	@echo "Copying tests to prod container..."
	@docker exec blue-api-1 rm -rf /app/tests 2>/dev/null || true
	@docker cp backend/tests blue-api-1:/app/
	@docker cp backend/pyproject.toml blue-api-1:/app/
	@echo "Installing test dependencies..."
	@docker exec blue-api-1 pip install pytest pytest-asyncio pytest-dotenv websockets redis --quiet
	@echo "Running integration tests inside prod container..."
	docker exec -e TEST_API_BASE_URL=http://localhost:8000 \
		-e TEST_WS_BASE_URL=$(TEST_WS_BASE_URL) \
		blue-api-1 python -m pytest /app/tests/integration/ /app/tests/api/test_audit_integration.py -v --tb=short -o "addopts="


# ==============================================================================
# Build & Clean
# ==============================================================================
.PHONY: build clean prune permissions
build: ## Build production Docker images
	@echo "Building production Docker images..."
	# Ensure correct build context and tagging strategy
	# Consider parameterizing TAG=latest or TAG=$$(git rev-parse --short HEAD)
	docker build --build-arg POETRY_VERSION=$$(awk '/poetry/ {print $$2}' .tool-versions) -t subtitle-downloader-api:latest --target production-api ./backend
	docker build --build-arg POETRY_VERSION=$$(awk '/poetry/ {print $$2}' .tool-versions) -t subtitle-downloader-worker:latest --target production-worker ./backend
	docker build -t subtitle-downloader-frontend:latest --target production ./frontend
	@echo "Note: Production build uses 'latest' tag. Use specific tags for releases."

clean: ## Remove build artifacts
	@echo "Cleaning build artifacts..."
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} +
	rm -rf backend/dist backend/build backend/*.egg-info backend/.pytest_cache backend/.coverage backend/htmlcov backend/.mypy_cache backend/.ruff_cache
	rm -rf frontend/dist frontend/node_modules frontend/coverage frontend/.vite
	@echo "Clean complete."

prune: ## Remove stopped containers, unused networks, and dangling images/volumes
	@echo "Pruning Docker system (containers, networks, images)..."
	docker system prune -f
	@echo "Pruning Docker volumes..."
	docker volume prune -f

permissions: ## Fix potential file permission issues from Docker volumes
	@echo "Attempting to fix volume permissions (requires sudo)..."
	sudo chown -R $(shell id -u):$(shell id -g) .
	@echo "Permissions reset to current user."


# ==============================================================================
# Security Scanning (Local)
# ==============================================================================
.PHONY: scan-vulns scan-secrets scan-sast scan-all

scan-vulns: ## Scan production target image for CRITICAL vulnerabilities using Trivy
	@echo "Scanning production API image for CRITICAL vulnerabilities..."
	@docker build --build-arg POETRY_VERSION=$$(awk '/poetry/ {print $$2}' .tool-versions) -t subro-api:scan --target production-api ./backend
	@trivy image --severity CRITICAL subro-api:scan

scan-secrets: ## Scan filesystem for secrets using Trivy
	@echo "Scanning filesystem for secrets..."
	@trivy fs --scanners secret --include-dev-deps --skip-dirs .venv --skip-dirs venv --skip-dirs backend/.venv --skip-dirs frontend/node_modules .

scan-sast: ## Scan code for security issues using Semgrep
	@echo "Running Semgrep SAST scan..."
	@set -a; [ -f .env ] && . ./.env; set +a; \
	SEMGREP_APP_TOKEN="$$SEMGREP_APP_TOKEN" semgrep scan --config auto .

scan-all: scan-vulns scan-secrets scan-sast ## Run all local security scans
	@echo "All security scans completed."


# ==============================================================================
# Local (Non-Dockerized) Alembic Commands - Use with caution, ensure .env is set for local DB
# ==============================================================================
.PHONY: local-db-upgrade local-db-revision
local-db-upgrade: ## (DEPRECATED-STYLE) Run Alembic upgrade head locally (targets DB in local .env)
	@echo "Running LOCAL database migrations (not against Dockerized DB)..."
	cd backend && poetry run alembic upgrade head

local-db-revision: ## (DEPRECATED-STYLE) Create Alembic revision locally (MSG="your_message")
	@echo "Creating a new LOCAL database revision (MSG=\"$(MSG)\")..."
	@if [ -z "$(MSG)" ]; then echo "Error: MSG variable is not set. Usage: make local-db-revision MSG=\"your message\""; exit 1; fi
	cd backend && poetry run alembic revision -m "$(MSG)"


# ==============================================================================
# Fail2Ban Management
# ==============================================================================
.PHONY: fail2ban-install fail2ban-status fail2ban-unban fail2ban-test

fail2ban-install: ## Install and configure fail2ban for subro_web
	@echo "Installing fail2ban for subro_web..."
	@chmod +x infra/scripts/install_fail2ban.sh
	@sudo infra/scripts/install_fail2ban.sh

fail2ban-status: ## Check fail2ban status and all banned IPs
	@echo "=== Fail2Ban Status ==="
	@sudo fail2ban-client status
	@echo ""
	@echo "=== Currently Banned IPs ==="
	@sudo fail2ban-client banned || echo "No IPs currently banned"

fail2ban-unban: ## Unban an IP address (usage: make fail2ban-unban IP=x.x.x.x)
	@if [ -z "$(IP)" ]; then echo "Usage: make fail2ban-unban IP=x.x.x.x"; exit 1; fi
	@echo "Unbanning $(IP) from all jails..."
	@sudo fail2ban-client unban $(IP)
	@echo "Done. $(IP) has been unbanned."

fail2ban-test: ## Test fail2ban filter regex against security log
	@echo "Testing subro-login filter..."
	@sudo fail2ban-regex /opt/subro_web/logs/security.log /etc/fail2ban/filter.d/subro-login.conf 2>/dev/null || echo "Filter not installed yet"
	@echo ""
	@echo "Testing subro-ratelimit filter..."
	@sudo fail2ban-regex /opt/subro_web/logs/security.log /etc/fail2ban/filter.d/subro-ratelimit.conf 2>/dev/null || echo "Filter not installed yet"
