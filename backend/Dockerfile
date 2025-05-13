# backend/Dockerfile

# --- Base Stage ---

# Define the Poetry version as a build argument
ARG POETRY_VERSION=2.1.2 # Using a slightly older stable version for example

# Use the official Python image.
FROM python:3.12-slim AS base

# Re-declare ARG within the stage so ENV can use it
ARG POETRY_VERSION

# Define APP_HOME early for clarity, though not strictly needed for WORKDIR
ENV APP_HOME=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Poetry settings
    POETRY_VERSION=${POETRY_VERSION} \
    POETRY_HOME="/opt/poetry" \
    # ---> CHANGED VENV LOCATION <---
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_VIRTUALENVS_PATH="/opt/pysetup/.venv" \
    POETRY_NO_INTERACTION=1 \
    # Path settings - Add venv bin and poetry bin to PATH
    # ---> UPDATED PATH <---
    PATH="/opt/pysetup/.venv/bin:$POETRY_HOME/bin:/usr/local/bin:$PATH"

# Set working directory
WORKDIR ${APP_HOME} # Use the ENV variable

# Install Poetry globally using the build argument
# Also update pip first
RUN pip install --upgrade pip && pip install poetry==${POETRY_VERSION}

# Create a non-root user and group early for consistent permissions
# Use the WORKDIR path for the home directory (-d)
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser -d ${APP_HOME} appuser

# --- Builder Stage ---
# Used to install dependencies with build tools
FROM base AS builder

# Set WORKDIR again for clarity in this stage
WORKDIR ${APP_HOME}

# Install build-time system dependencies if needed (e.g., for psycopg)
# Example for psycopg - uncomment if you use psycopg2-binary instead of psycopg[binary]
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Copy dependency definition files FIRST, ensuring correct ownership
# This leverages Docker cache more effectively
COPY --chown=appuser:appuser pyproject.toml poetry.lock ./

# Install ONLY runtime dependencies using Poetry
# Use --no-cache to avoid potential poetry caching issues inside build
# The venv will be created at /opt/pysetup/.venv due to ENV vars in base
RUN poetry install --no-dev --no-root --sync --no-cache

# Install the project itself as editable AFTER dependencies
# RUN poetry install --no-dev --sync --no-cache

# --- Development Stage ---
# Optimized for local development with hot-reloading
FROM base AS development

# Set WORKDIR again for clarity in this stage
WORKDIR ${APP_HOME}

# Install curl (needed for docker-compose healthcheck)
# And netcat-openbsd (needed for the entrypoint script's DB check)
# And any dev-specific system dependencies (like git if needed by poetry plugins)
RUN apt-get update && apt-get install -y curl netcat-openbsd --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Copy Poetry files, ensuring correct ownership
COPY --chown=appuser:appuser pyproject.toml poetry.lock ./

# Install ALL dependencies including dev group using Poetry
# The venv will be created at /opt/pysetup/.venv
RUN poetry install --verbose --sync --no-cache

# Copy application code (less critical now due to volume mount, but good practice)
COPY --chown=appuser:appuser . .

# --- ADDED: Copy and set permissions for the entrypoint script ---
COPY --chown=appuser:appuser ./scripts/entrypoint.sh /app/scripts/entrypoint.sh
RUN chmod +x /app/scripts/entrypoint.sh

# Switch to non-root user for running the application
USER appuser

# Expose the port (good practice)
EXPOSE 8000

# --- ADDED: Set the entrypoint script ---
# This script waits for DB, runs migrations, then executes CMD
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# --- MODIFIED: Define the default command for development ---
# This is what entrypoint.sh executes via 'exec "$@"' after its tasks
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# --- Production Stage (API) ---
FROM base AS production-api

WORKDIR ${APP_HOME}

# Copy installed runtime dependencies (venv) from builder stage
# Make sure the destination exists (though /opt/pysetup should from base)
RUN mkdir -p /opt/pysetup && chown appuser:appuser /opt/pysetup
COPY --chown=appuser:appuser --from=builder /opt/pysetup/.venv /opt/pysetup/.venv

# Copy only the application code needed for runtime
COPY --chown=appuser:appuser app ./app
# Add any other necessary files like scripts, static files etc.
# COPY --chown=appuser:appuser scripts ./scripts

USER appuser
EXPOSE 8000

# Use the venv Python via the updated PATH
# NOTE: Production does NOT use the entrypoint script
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000", "app.main:app"]


# --- Production Stage (Worker) ---
FROM production-api AS production-worker
# Inherits everything from production-api (user, venv, code, WORKDIR, USER, PATH)

# Use the venv Python via the updated PATH
# NOTE: Production does NOT use the entrypoint script
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=INFO"] # Add pool/concurrency as needed e.g. "-P gevent -c 4"
