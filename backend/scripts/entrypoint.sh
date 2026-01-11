#!/usr/bin/env bash
# Using bash for reliable pipefail support and better error handling
set -euo pipefail

# --- Logging Functions ---
log() {
    printf '[%s] Entrypoint: %s\n' "$(date +'%Y-%m-%d %H:%M:%S')" "$*"
}

log_error() {
    printf '[%s] Entrypoint ERROR: %s\n' "$(date +'%Y-%m-%d %H:%M:%S')" "$*" >&2
}

# --- Exit Handler for Better Diagnostics ---
on_exit() {
    local exit_code=$?

    # Don't log error for clean signal exits (143 = 128 + 15 for SIGTERM)
    if [ "$exit_code" -ne 0 ] && [ "$exit_code" -ne 143 ]; then
        log_error "Entrypoint failed with exit code $exit_code"
        log_error "Check logs above for details"
    fi
}
trap on_exit EXIT

# --- Signal Handling ---
# Exit with proper signal code during initialization
trap 'log "Received signal, exiting..."; exit 143' TERM INT

# --- Helper Functions ---

# Check if a command exists, exit if missing
require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        log_error "Missing required command: $1"
        log_error "Please ensure it's installed in the Docker image"
        exit 127
    }
}

# Validate that a value is a positive integer
is_positive_int() {
    case "$1" in
        ''|*[!0-9]*) return 1 ;;
        *) [ "$1" -gt 0 ] 2>/dev/null || return 1 ;;
    esac
}

# Check if value is truthy (true, TRUE, 1, yes, YES, on, ON)
is_true() {
    case "${1:-}" in
        true|TRUE|1|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

# Parse DATABASE_URL into connection components for libpq tooling.
# Outputs: host, port, user, password, dbname, sslmode (one per line).
parse_database_url() {
    command -v python >/dev/null 2>&1 || return 1

    python - <<'PY'
import os
import sys
from urllib.parse import parse_qs, unquote, urlparse

url = os.environ.get("DATABASE_URL", "")
if not url:
    sys.exit(1)

parsed = urlparse(url)
if not parsed.scheme:
    sys.exit(1)

def clean(value: str) -> str:
    return unquote(value) if value else ""

host = parsed.hostname or ""
try:
    port = str(parsed.port) if parsed.port is not None else ""
except ValueError:
    port = ""
user = clean(parsed.username or "")
password = clean(parsed.password or "")
dbname = parsed.path.lstrip("/") if parsed.path else ""
sslmode = parse_qs(parsed.query).get("sslmode", [""])[0]

print(host)
print(port)
print(user)
print(password)
print(dbname)
print(sslmode)
PY
}

# Generic retry function with exponential backoff
# Usage: retry <max_attempts> <base_sleep> <command> [args...]
retry() {
    local max_attempts="$1"
    local base_sleep="$2"
    shift 2

    local attempt=1
    while [ "$attempt" -le "$max_attempts" ]; do
        set +e
        "$@"
        local exit_code=$?
        set -e
        if [ "$exit_code" -eq 0 ]; then
            return 0
        fi

        if [ "$attempt" -ge "$max_attempts" ]; then
            log_error "Command failed after $max_attempts attempts"
            return "$exit_code"
        fi

        # Exponential backoff: sleep = base_sleep * attempt (capped at 15s for snappier startup)
        local sleep_time=$((base_sleep * attempt))
        [ "$sleep_time" -gt 15 ] && sleep_time=15

        log "Attempt $attempt/$max_attempts failed (exit code: $exit_code)"
        log "Retrying in ${sleep_time}s..."
        sleep "$sleep_time"

        attempt=$((attempt + 1))
    done
}

# --- Command Execution Abstraction ---
# Explicit runners avoid fragile inference logic
# Each handles the poetry vs direct execution distinction clearly

run_python() {
    # Run python with arguments
    if [ "$APP_ENV" = "development" ]; then
        poetry run python "$@"
    else
        python "$@"
    fi
}

run_module() {
    # Run python module with -m flag
    if [ "$APP_ENV" = "development" ]; then
        poetry run python -m "$@"
    else
        python -m "$@"
    fi
}

run_alembic() {
    # Run alembic CLI
    if [ "$APP_ENV" = "development" ]; then
        poetry run alembic "$@"
    else
        # Use python -m to avoid dependency on alembic console script
        python -m alembic "$@"
    fi
}

# --- Configuration ---
APP_ENV="${APP_ENV:-production}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-60}"
MAX_MIGRATION_ATTEMPTS="${MAX_MIGRATION_ATTEMPTS:-30}"
MIGRATION_RETRY_SLEEP="${MIGRATION_RETRY_SLEEP:-1}"     # Set to 1s for faster CI/startup
BOOTSTRAP_RETRY_ATTEMPTS="${BOOTSTRAP_RETRY_ATTEMPTS:-3}"
BOOTSTRAP_RETRY_SLEEP="${BOOTSTRAP_RETRY_SLEEP:-2}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
RUN_BOOTSTRAP="${RUN_BOOTSTRAP:-true}"
USE_ADVISORY_LOCK="${USE_ADVISORY_LOCK:-true}"
LOCK_TIMEOUT="${LOCK_TIMEOUT:-60}"

# Sync DB_HOST/DB_PORT with possibly provided POSTGRES_SERVER/POSTGRES_PORT
DB_HOST="${POSTGRES_SERVER:-$DB_HOST}"
DB_PORT="${POSTGRES_PORT:-$DB_PORT}"

# Construct DATABASE_URL if missing but components exist
if [ -z "${DATABASE_URL:-}" ] && [ -n "${POSTGRES_USER:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ]; then
    log "DATABASE_URL missing, constructing from components..."
    # Map POSTGRES_DB to 'subappdb' if missing to match config.py defaults
    DB_NAME="${POSTGRES_DB:-subappdb}"
    DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
    # Export it so python/alembic/etc can see it
    export DATABASE_URL
fi

# Validate required information for database connection
if [ -z "${DATABASE_URL:-}" ]; then
    log_error "DATABASE_URL is missing and could not be reconstructed from POSTGRES_* variables."
    log_error "Please ensure DATABASE_URL or (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_SERVER, POSTGRES_DB) are set."
    exit 1
fi

# Validate numeric configurations
is_positive_int "$WAIT_TIMEOUT" || {
    log_error "WAIT_TIMEOUT must be a positive integer, got: $WAIT_TIMEOUT"
    exit 2
}
is_positive_int "$MAX_MIGRATION_ATTEMPTS" || {
    log_error "MAX_MIGRATION_ATTEMPTS must be a positive integer, got: $MAX_MIGRATION_ATTEMPTS"
    exit 2
}
is_positive_int "$MIGRATION_RETRY_SLEEP" || {
    log_error "MIGRATION_RETRY_SLEEP must be a positive integer, got: $MIGRATION_RETRY_SLEEP"
    exit 2
}
is_positive_int "$BOOTSTRAP_RETRY_ATTEMPTS" || {
    log_error "BOOTSTRAP_RETRY_ATTEMPTS must be a positive integer, got: $BOOTSTRAP_RETRY_ATTEMPTS"
    exit 2
}
is_positive_int "$BOOTSTRAP_RETRY_SLEEP" || {
    log_error "BOOTSTRAP_RETRY_SLEEP must be a positive integer, got: $BOOTSTRAP_RETRY_SLEEP"
    exit 2
}
is_positive_int "$LOCK_TIMEOUT" || {
    log_error "LOCK_TIMEOUT must be a positive integer, got: $LOCK_TIMEOUT"
    exit 2
}

# Validate that a command was provided
if [ "$#" -eq 0 ]; then
    log_error "No command provided to entrypoint"
    log_error "Set CMD in Dockerfile or provide command in docker-compose.yml"
    exit 64
fi

# Check for required commands
require_cmd date

# OPTIMIZATION: Only require poetry in development
# Production images can use system python and remove poetry for smaller size
if [ "$APP_ENV" = "development" ]; then
    require_cmd poetry
fi

log "Starting entrypoint script in ${APP_ENV} mode"

# --- User/Group ID Management (Development Only) ---
if [ "$APP_ENV" = "development" ]; then
    require_cmd gosu
    require_cmd groupadd
    require_cmd useradd
    require_cmd getent
    require_cmd chown
    require_cmd mkdir

    PUID="${PUID:-1000}"
    PGID="${PGID:-1000}"

    log "Development mode: Configuring appuser with UID:$PUID GID:$PGID"

    # Create group if not exists
    if ! getent group appuser >/dev/null 2>&1; then
        groupadd -g "$PGID" appuser
    else
        groupmod -o -g "$PGID" appuser 2>/dev/null || true
    fi

    # Create user if not exists
    if ! getent passwd appuser >/dev/null 2>&1; then
        useradd -u "$PUID" -g "$PGID" -d /app -s /bin/bash appuser
    else
        usermod -o -u "$PUID" appuser 2>/dev/null || true
    fi

    # PERFORMANCE: Only chown writable directories, not the entire codebase
    # Best effort - don't crash on read-only mounts (common in hardened K8s)
    log "Setting ownership on writable directories (best effort)"

    mkdir -p /app/logs 2>/dev/null || log "Warning: Could not create /app/logs"
    chown -R appuser:appuser /app/logs 2>/dev/null || log "Warning: Could not chown /app/logs (non-fatal)"

    # Handle subtitle translation logs
    TRANS_LOG_DIR="/app/app/modules/subtitle/services/logs"
    if [ -d "$(dirname "$TRANS_LOG_DIR")" ]; then
        mkdir -p "$TRANS_LOG_DIR" 2>/dev/null || log "Warning: Could not create $TRANS_LOG_DIR"
        chown -R appuser:appuser "$TRANS_LOG_DIR" 2>/dev/null || log "Warning: Could not chown subtitle logs (non-fatal)"
    fi

    # Handle external media mount if it exists (often read-only)
    if [ -d "/mnt/sata0/Media" ]; then
        chown appuser:appuser /mnt/sata0/Media 2>/dev/null || log "Warning: Could not chown Media mount (likely read-only)"
    fi
else
    log "Production mode: Using pre-configured appuser from Dockerfile"
fi

# --- Wait for Database ---
log "Waiting for PostgreSQL (timeout: ${WAIT_TIMEOUT}s)"

wait_for_db() {
    local start_time=$(date +%s)
    local time_budget="$WAIT_TIMEOUT"
    local db_check_url="$DATABASE_URL"
    local db_host="$DB_HOST"
    local db_port="$DB_PORT"
    local db_user="${POSTGRES_USER:-}"
    local db_password="${POSTGRES_PASSWORD:-}"
    local db_name="${POSTGRES_DB:-}"
    local db_sslmode=""
    local -a db_parts=()

    if [[ "$db_check_url" == postgresql+*://* ]]; then
        log "Normalizing DATABASE_URL scheme for libpq readiness checks"
        db_check_url="postgresql://${db_check_url#postgresql+*://}"
    elif [[ "$db_check_url" == postgres://* ]]; then
        log "Normalizing DATABASE_URL scheme for libpq readiness checks"
        db_check_url="postgresql://${db_check_url#postgres://}"
    fi

    local parsed_db_url
    parsed_db_url="$(parse_database_url 2>/dev/null || true)"
    if [ -n "$parsed_db_url" ]; then
        mapfile -t db_parts <<< "$parsed_db_url"
        if [ -n "${db_parts[0]:-}" ]; then
            db_host="${db_parts[0]}"
            db_port="${db_parts[1]:-$db_port}"
            db_user="${db_parts[2]:-$db_user}"
            db_password="${db_parts[3]:-$db_password}"
            db_name="${db_parts[4]:-$db_name}"
            db_sslmode="${db_parts[5]:-}"
        fi
    else
        log "Warning: Unable to parse DATABASE_URL, falling back to POSTGRES_* variables"
    fi

    if [ -n "$db_host" ]; then
        log "Database readiness target: host=$db_host port=$db_port db=${db_name:-unknown} user=${db_user:-unknown}"
    else
        log "Database readiness target: using DATABASE_URL"
    fi

    # Helper to check remaining time budget
    check_timeout() {
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        if [ "$elapsed" -ge "$time_budget" ]; then
            log_error "Timeout waiting for database after ${time_budget}s"
            return 1
        fi
        return 0
    }

    # Prefer pg_isready with DATABASE_URL for basic connectivity check
    if command -v pg_isready >/dev/null 2>&1; then
        log "Using pg_isready for initial database connectivity check"

        local -a pg_args=()
        if [ -n "$db_host" ]; then
            pg_args+=("-h" "$db_host" "-p" "$db_port")
            [ -n "$db_user" ] && pg_args+=("-U" "$db_user")
            [ -n "$db_name" ] && pg_args+=("-d" "$db_name")
        else
            pg_args+=("-d" "$db_check_url")
        fi

        local -a pg_env=()
        [ -n "$db_password" ] && pg_env+=(PGPASSWORD="$db_password")
        [ -n "$db_sslmode" ] && pg_env+=(PGSSLMODE="$db_sslmode")

        while ! env "${pg_env[@]}" pg_isready "${pg_args[@]}" -q 2>/dev/null; do
            check_timeout || return 1

            local current_time=$(date +%s)
            local elapsed=$((current_time - start_time))

            # Log progress every 10 seconds
            if [ $((elapsed % 10)) -eq 0 ] && [ "$elapsed" -gt 0 ]; then
                log "Still waiting for database... (${elapsed}s elapsed)"
            fi

            sleep 2
        done

        log "Database port is accepting connections"

        # If psql is available, verify we can actually query the database
        # Use remaining time budget for auth verification
        if command -v psql >/dev/null 2>&1; then
            log "Verifying database authentication and query capability"

            local last_log_time=0
            if [ -n "$db_host" ]; then
                local -a psql_args=("-h" "$db_host" "-p" "$db_port")
                [ -n "$db_user" ] && psql_args+=("-U" "$db_user")
                [ -n "$db_name" ] && psql_args+=("-d" "$db_name")
                while ! env "${pg_env[@]}" psql "${psql_args[@]}" -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1; do
                    check_timeout || return 1

                    # Log every 10 seconds to reduce noise
                    local current_time=$(date +%s)
                    local elapsed=$((current_time - start_time))
                    if [ $((elapsed - last_log_time)) -ge 10 ]; then
                        log "Database authentication check failed, retrying... (${elapsed}s elapsed)"
                        last_log_time=$elapsed
                    fi

                    sleep 2
                done
            else
                while ! psql "$db_check_url" -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1; do
                    check_timeout || return 1

                    # Log every 10 seconds to reduce noise
                    local current_time=$(date +%s)
                    local elapsed=$((current_time - start_time))
                    if [ $((elapsed - last_log_time)) -ge 10 ]; then
                        log "Database authentication check failed, retrying... (${elapsed}s elapsed)"
                        last_log_time=$elapsed
                    fi

                    sleep 2
                done
            fi

            log "Database authentication verified successfully"
        else
            log "psql not available, skipping authentication verification"
        fi
    else
        log "pg_isready not available, falling back to netcat port check"
        log "WARNING: This only checks if port is open, not if database is ready"
        require_cmd nc

        local nc_host="${db_host:-$DB_HOST}"
        local nc_port="${db_port:-$DB_PORT}"

        while ! nc -z "$nc_host" "$nc_port" >/dev/null 2>&1; do
            check_timeout || return 1

            local current_time=$(date +%s)
            local elapsed=$((current_time - start_time))

            if [ $((elapsed % 10)) -eq 0 ] && [ "$elapsed" -gt 0 ]; then
                log "Still waiting for database port... (${elapsed}s elapsed)"
            fi

            sleep 2
        done
    fi

    return 0
}

if ! wait_for_db; then
    log_error "Failed to connect to database"
    log_error "Check your DATABASE_URL and ensure the database container is running"
    exit 1
fi

log "Database is ready and accepting connections"

# --- Change to App Directory ---
cd /app || {
    log_error "Failed to change directory to /app"
    exit 1
}

log "Working directory: $(pwd)"

# Verify python/alembic environment (only in dev where we require poetry)
if [ "$APP_ENV" = "development" ]; then
    log "Verifying poetry environment..."
    if ! poetry run python --version >/dev/null 2>&1; then
        log_error "Poetry environment is not properly configured"
        log_error "Run 'poetry install' to set up dependencies"
        exit 1
    fi

    if ! poetry run alembic --version >/dev/null 2>&1; then
        log_error "Alembic is not available in poetry environment"
        log_error "Ensure alembic is listed in pyproject.toml dependencies"
        exit 1
    fi

    log "Poetry environment verified successfully"
else
    # In production, just verify python and alembic are available
    log "Verifying python environment..."

    require_cmd python

    if ! python --version >/dev/null 2>&1; then
        log_error "Python is not available or not working"
        exit 1
    fi

    # Verify alembic module is importable
    if ! python -c "import alembic" 2>/dev/null; then
        log_error "Alembic is not available in python environment"
        log_error "Ensure dependencies are installed"
        exit 1
    fi

    log "Python environment verified successfully"
fi

# --- Database Migration with Optional Python-Based Advisory Lock ---

# Check if Python environment supports advisory locking
python_lock_supported() {
    run_python - <<'PY' 2>/dev/null
import sys
try:
    import sqlalchemy
    import alembic
    sys.exit(0)
except ImportError as e:
    sys.exit(1)
PY
}

run_migrations() {
    if is_true "$USE_ADVISORY_LOCK"; then
        # Verify Python dependencies are available for advisory locking
        if ! python_lock_supported; then
            log_error "Advisory lock requested but required Python packages not available"
            log_error "Ensure sqlalchemy and alembic are installed"
            log_error "Falling back to standard migration (no lock protection)"
            run_alembic upgrade head
            return
        fi

        log "Running migrations with Python-based advisory lock"
        log "Lock timeout: ${LOCK_TIMEOUT}s"
        log "NOTE: This provides session-level protection against concurrent migrations"

        # Run migration with advisory lock using inline Python (no temp file needed)
        # This keeps the connection alive during the entire migration
        LOCK_TIMEOUT="$LOCK_TIMEOUT" run_python - <<'PY'
import os
import sys
import time
from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic import command

LOCK_ID = 424242
DATABASE_URL = os.environ["DATABASE_URL"]
LOCK_TIMEOUT = int(os.environ.get("LOCK_TIMEOUT", "60"))

try:
    # Ensure we use a synchronous driver for the advisory lock
    sync_url = DATABASE_URL.replace("+asyncpg", "") if "+asyncpg" in DATABASE_URL else DATABASE_URL
    engine = create_engine(sync_url)

    with engine.connect() as conn:
        # Try to acquire lock with timeout (non-blocking)
        print(f"Attempting to acquire PostgreSQL advisory lock (ID: {LOCK_ID})", flush=True)
        deadline = time.time() + LOCK_TIMEOUT

        while True:
            # Try non-blocking lock
            got_lock = conn.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": LOCK_ID}
            ).scalar()

            if got_lock:
                print(f"Advisory lock acquired successfully", flush=True)
                break

            if time.time() >= deadline:
                raise TimeoutError(
                    f"Timed out after {LOCK_TIMEOUT}s waiting to acquire advisory lock {LOCK_ID}. "
                    f"Another process may be holding the lock."
                )

            time.sleep(2)

        try:
            print("Running migrations while holding advisory lock...", flush=True)

            # Load alembic config and run migrations
            alembic_cfg = Config(os.path.join(os.getcwd(), "alembic.ini"))
            command.upgrade(alembic_cfg, "head")

            print("Migrations completed successfully", flush=True)
        finally:
            # Always release lock, even if migration fails
            print("Releasing advisory lock...", flush=True)
            conn.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": LOCK_ID}
            )
            print("Advisory lock released", flush=True)

    sys.exit(0)

except TimeoutError as e:
    print(f"ERROR: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Migration failed: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PY
    else
        log "Running migrations without advisory lock"
        log "NOTE: Relying on jitter for collision avoidance"
        log "WARNING: This does NOT guarantee safety with concurrent migrations"
        log "For production with multiple replicas, consider USE_ADVISORY_LOCK=true"

        run_alembic upgrade head
    fi
}

if is_true "$RUN_MIGRATIONS"; then
    log "Starting database migration process"
    log ""
    log "MULTI-REPLICA SAFETY OPTIONS (in order of preference):"
    log "  1. BEST: Use Kubernetes InitContainer or separate migration job"
    log "  2. GOOD: Set RUN_MIGRATIONS=true on only ONE replica"
    log "  3. OK: Enable USE_ADVISORY_LOCK=true (provides session-level locking)"
    log "  4. RISKY: Current default relies on jitter only (reduces but doesn't prevent conflicts)"
    log ""

    # PRODUCTION BEST PRACTICE: Add jitter to prevent thundering herd
    # Using bash $RANDOM for per-process randomness (0-9 seconds)
    if [ "$APP_ENV" != "development" ]; then
        JITTER=$(( RANDOM % 10 ))
        if [ "$JITTER" -gt 0 ]; then
            log "Adding ${JITTER}s jitter to prevent concurrent migration conflicts"
            sleep "$JITTER"
        fi
    fi

    # Log initial database state for diagnostics (handle errors gracefully)
    INITIAL_DB_REV="$(run_alembic current 2>/dev/null | grep -oE '[0-9a-zA-Z._-]{8,32}' | head -n 1 || true)"
    INITIAL_DB_REV="${INITIAL_DB_REV:-none}"
    log "Current database revision: $INITIAL_DB_REV"

    # Count available migration files for diagnostics
    if [ -d "alembic/versions" ]; then
        MIGRATION_COUNT=$(find alembic/versions -type f -name "*.py" ! -name "__*" 2>/dev/null | wc -l || echo "0")
        log "Found $MIGRATION_COUNT migration file(s) in alembic/versions/"
    else
        log "Warning: alembic/versions directory not found"
    fi

    # Run migration with retry logic
    log "Applying database migrations..."
    if ! retry "$MAX_MIGRATION_ATTEMPTS" "$MIGRATION_RETRY_SLEEP" run_migrations; then
        log_error "Failed to apply database migrations after $MAX_MIGRATION_ATTEMPTS attempts"
        log_error "Initial revision: $INITIAL_DB_REV"

        # Try to get current state for debugging
        CURRENT_REV="$(run_alembic current 2>/dev/null | grep -oE '[0-9a-zA-Z._-]{8,32}' | head -n 1 || true)"
        CURRENT_REV="${CURRENT_REV:-unknown}"
        log_error "Current revision: $CURRENT_REV"

        log_error "Manual intervention required. Debug commands:"
        log_error "  docker-compose exec app alembic current"
        log_error "  docker-compose exec app alembic history"
        log_error "  docker-compose exec app alembic heads"
        exit 1
    fi

    # Log final migration state
    FINAL_REV="$(run_alembic current 2>/dev/null | grep -oE '[0-9a-zA-Z._-]{8,32}' | head -n 1 || true)"
    FINAL_REV="${FINAL_REV:-none}"
    log "Database migrations completed successfully"
    log "Final database revision: $FINAL_REV"

    if [ "$INITIAL_DB_REV" != "$FINAL_REV" ]; then
        log "Database updated from $INITIAL_DB_REV to $FINAL_REV"
    else
        log "Database already up to date (no changes applied)"
    fi
else
    log "Skipping database migrations (RUN_MIGRATIONS=$RUN_MIGRATIONS)"
    log "Ensure migrations are run by another instance or init container"
fi

# --- Database Bootstrapping ---
if is_true "$RUN_BOOTSTRAP"; then
    log "Running database bootstrap (initial_data.py)"
    log "NOTE: This script should be idempotent (safe to run multiple times)"

    if ! retry "$BOOTSTRAP_RETRY_ATTEMPTS" "$BOOTSTRAP_RETRY_SLEEP" run_module app.initial_data; then
        log_error "Database bootstrap failed after $BOOTSTRAP_RETRY_ATTEMPTS attempts"
        log_error "This is usually non-fatal if data already exists"
        log_error "Check logs above for specific errors"
        log "Continuing startup despite bootstrap failure..."
    else
        log "Database bootstrap completed successfully"
    fi
else
    log "Skipping database bootstrap (RUN_BOOTSTRAP=$RUN_BOOTSTRAP)"
fi

# --- Start Application ---
log "All initialization tasks completed successfully"
log "Starting application with command: $(printf '%q ' "$@")"

# Drop privileges and exec into the main application
if [ "$APP_ENV" = "development" ]; then
    # Development: Use gosu to drop from root to appuser
    log "Development mode: Switching to appuser via gosu"
    exec gosu appuser "$@"
else
    # Production: Should already be appuser from Dockerfile
    CURRENT_USER=$(id -un)
    CURRENT_UID=$(id -u)

    log "Running as user: $CURRENT_USER (UID: $CURRENT_UID)"

    # If somehow running as root in production, handle based on security policy
    if [ "$CURRENT_UID" = "0" ]; then
        log "WARNING: Container running as root in production mode"

        if is_true "${ALLOW_ROOT_PRODUCTION:-false}"; then
            log "WARNING: Starting as root due to ALLOW_ROOT_PRODUCTION=true (NOT RECOMMENDED)"
            exec "$@"
        elif command -v gosu >/dev/null 2>&1; then
            log "Attempting to drop privileges to appuser via gosu"
            exec gosu appuser "$@"
        else
            log_error "Cannot drop privileges: gosu not available"
            log_error "Running as root in production is a SECURITY RISK"
            log_error "Refusing to start as root without explicit override"
            log_error "To override, set ALLOW_ROOT_PRODUCTION=true (NOT RECOMMENDED)"
            exit 1
        fi
    else
        # Not root, proceed normally
        exec "$@"
    fi
fi
