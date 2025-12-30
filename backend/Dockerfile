# backend/Dockerfile

# --- Base Stage ---

# Define the Poetry version as a build argument
ARG POETRY_VERSION=2.1.2

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
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    # Path settings - Add venv bin and poetry bin to PATH
    PATH="/app/.venv/bin:$POETRY_HOME/bin:/usr/local/bin:$PATH"

# Set working directory
WORKDIR ${APP_HOME} # Use the ENV variable

# Install Poetry globally using the build argument
# Also update pip first and install gosu
RUN apt-get update && apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && pip install poetry==${POETRY_VERSION}


# Create a non-root user and group early for consistent permissions
# Use the WORKDIR path for the home directory (-d)
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser -d ${APP_HOME} appuser

# Create media directory and set permissions
RUN mkdir -p /mnt/sata0/Media && chown appuser:appuser /mnt/sata0/Media

# --- Create scripts directory structure ---
RUN mkdir -p /app/scripts && chown appuser:appuser /app/scripts

# --- Builder Stage ---
# Used to install dependencies with build tools
FROM base AS builder

# Set WORKDIR again for clarity in this stage
WORKDIR ${APP_HOME}

# Install build-time system dependencies if needed (e.g., for psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Copy dependency definition files FIRST, ensuring correct ownership
COPY --chown=appuser:appuser pyproject.toml poetry.lock ./

# Install ONLY runtime dependencies using Poetry
# We use --only main. If issues arise, we might switch to full install or use dev stage.
RUN poetry install --only main --no-root --sync --no-cache

# --- Development Stage ---
# Optimized for local development with hot-reloading
FROM base AS development

# Set WORKDIR again for clarity in this stage
WORKDIR ${APP_HOME}

# Install curl (needed for docker-compose healthcheck)
# And netcat-openbsd (needed for the entrypoint script's DB check)
# And any dev-specific system dependencies (like git if needed by poetry plugins)
# Also install cargo for alass-cli
RUN apt-get update && apt-get install -y curl netcat-openbsd build-essential ffmpeg unrar-free cargo --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Copy Poetry files, ensuring correct ownership
COPY --chown=appuser:appuser pyproject.toml poetry.lock ./

# Install ALL dependencies including dev group using Poetry
# The venv will be created at /app/.venv
RUN poetry install --verbose --sync --no-cache

# Install ffsubsync for subtitle synchronization
RUN pip install ffsubsync

# Create NLTK data directory with proper ownership and download punkt tokenizer
RUN mkdir -p /app/nltk_data && \
    chown -R appuser:appuser /app/nltk_data && \
    python -m nltk.downloader -d /app/nltk_data punkt punkt_tab || true

# Set NLTK data path for runtime
ENV NLTK_DATA=/app/nltk_data

# Install alass-cli for subtitle synchronization (via cargo)
RUN cargo install alass-cli && \
    ln -sf /root/.cargo/bin/alass-cli /usr/local/bin/alass-cli

# Copy application code (less critical now due to volume mount, but good practice)
COPY --chown=appuser:appuser . .

# Make sure scripts directory exists before attempting to copy to it
RUN mkdir -p /app/scripts

# Create placeholder entrypoint script if it doesn't exist in the context
RUN if [ ! -f /app/scripts/entrypoint.sh ]; then \
    echo '#!/bin/bash' > /app/scripts/entrypoint.sh && \
    echo 'echo "Waiting for database..."' >> /app/scripts/entrypoint.sh && \
    echo 'sleep 5' >> /app/scripts/entrypoint.sh && \
    echo 'echo "Database ready!"' >> /app/scripts/entrypoint.sh && \
    echo 'exec "$@"' >> /app/scripts/entrypoint.sh; \
    fi

# Set proper permissions
RUN chmod +x /app/scripts/entrypoint.sh

# Create sub_downloader placeholder if needed
RUN if [ ! -f /app/scripts/sub_downloader.py ]; then \
    echo '#!/usr/bin/env python3' > /app/scripts/sub_downloader.py && \
    echo '# Placeholder for subtitle downloader script' >> /app/scripts/sub_downloader.py && \
    echo 'print("Subtitle downloader placeholder")' >> /app/scripts/sub_downloader.py; \
    fi

# Make Python scripts executable
RUN find /app/scripts -type f -iname "*.py" -exec chmod +x {} \;

# Expose the port (good practice)
EXPOSE 8000

# Set the entrypoint script
# This script waits for DB, runs migrations, then executes CMD
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Define the default command for development
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# --- Production Stage (API) ---
FROM base AS production-api

WORKDIR ${APP_HOME}

# Install runtime dependencies
# curl: healthcheck, netcat-openbsd: entrypoint wait
# ffmpeg: required by ffsubsync for subtitle sync
# unrar-free: extract subtitle archives
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    netcat-openbsd \
    ffmpeg \
    unrar-free \
    && rm -rf /var/lib/apt/lists/*

# Copy installed runtime dependencies (venv) from BUILDER stage (runtime-only deps)
# Using /app/.venv as configured by POETRY_VIRTUALENVS_IN_PROJECT=true
COPY --chown=appuser:appuser --from=builder /app/.venv /app/.venv

# Copy configuration and migration files
COPY --chown=appuser:appuser pyproject.toml alembic.ini ./
COPY --chown=appuser:appuser alembic ./alembic

# Copy only the application code needed for runtime
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser secrets ./secrets

# Ensure scripts directory exists and copy all scripts from development stage
RUN mkdir -p /app/scripts
COPY --chown=appuser:appuser --from=development /app/scripts /app/scripts
RUN chmod +x /app/scripts/*.sh /app/scripts/*.py 2>/dev/null || true

# Copy alass-cli binary from development (built via cargo)
COPY --from=development /root/.cargo/bin/alass-cli /usr/local/bin/alass-cli
RUN chmod +x /usr/local/bin/alass-cli

# Copy NLTK data from development (downloaded at build time)
COPY --chown=appuser:appuser --from=development /app/nltk_data /app/nltk_data
ENV NLTK_DATA=/app/nltk_data

EXPOSE 8000

# Set the entrypoint script
# This script waits for DB, runs migrations, then executes CMD
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Use the venv Python via the updated PATH
# Using uvicorn from PATH
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# --- Production Stage (Worker) ---
FROM production-api AS production-worker
# Inherits everything from production-api (user, venv, code, WORKDIR, USER, PATH, ENTRYPOINT)

# Use the venv Python via the updated PATH
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=INFO"]
