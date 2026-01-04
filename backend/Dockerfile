# backend/Dockerfile

# --- Base Stage ---
# Use Ubuntu 24.04 (Noble Numbat) - newer base image with 0 CRITICAL CVEs
FROM ubuntu:24.04 AS base

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Define the Poetry version as a build argument
ARG POETRY_VERSION=2.1.2

# Define APP_HOME early for clarity
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
    PATH="/app/.venv/bin:/opt/poetry/bin:/usr/local/bin:$PATH"

# Set working directory
WORKDIR ${APP_HOME}

# Install Python 3.12, pip, venv, and gosu.
# Run apt-get upgrade to patch all OS-level CVEs.
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3-pip \
    python3-setuptools \
    gosu \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Symlink python3 to python for convenience
RUN ln -s /usr/bin/python3.12 /usr/local/bin/python

# Install Poetry using the official installer script to avoid dependency conflicts
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 -

# Create a non-root user and group early for consistent permissions
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

# Install build-time system dependencies (build-essential, libpq-dev for Postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    python3.12-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition files FIRST, ensuring correct ownership
COPY --chown=appuser:appuser pyproject.toml poetry.lock ./

# Install ALL dependencies including main
RUN poetry install --no-root --sync --no-cache

# --- Development Stage ---
# Optimized for local development with hot-reloading
FROM base AS development

# Set WORKDIR again for clarity in this stage
WORKDIR ${APP_HOME}

# Install development system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    netcat-openbsd \
    ffmpeg \
    unrar-free \
    xz-utils \
    git \
    build-essential \
    python3.12-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Poetry files
COPY --chown=appuser:appuser pyproject.toml poetry.lock ./

# Install ALL dependencies including dev group
RUN poetry install --verbose --sync --no-cache

# Install ffsubsync for subtitle synchronization
RUN pip install ffsubsync --break-system-packages || pip install ffsubsync

# Create NLTK data directory
RUN mkdir -p /app/nltk_data && \
    chown -R appuser:appuser /app/nltk_data && \
    python -m nltk.downloader -d /app/nltk_data punkt punkt_tab || true

# Set NLTK data path for runtime
ENV NLTK_DATA=/app/nltk_data

# Install alass-cli for subtitle synchronization (pre-built binary)
RUN curl -fsSL https://github.com/kaegi/alass/releases/download/v2.0.0/alass-linux64 -o /usr/local/bin/alass-cli && \
    chmod +x /usr/local/bin/alass-cli

# Copy application code
COPY --chown=appuser:appuser . .

# Set proper permissions for scripts
RUN chmod +x /app/scripts/*.sh /app/scripts/*.py 2>/dev/null || true

# Expose port
EXPOSE 8000

# Set the entrypoint script
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Default command for development
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# --- Production Stage (API) ---
FROM base AS production-api

WORKDIR ${APP_HOME}

# Install runtime dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    netcat-openbsd \
    ffmpeg \
    unrar-free \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --chown=appuser:appuser --from=builder /app/.venv /app/.venv

# Copy configuration and migration files
COPY --chown=appuser:appuser pyproject.toml alembic.ini ./
COPY --chown=appuser:appuser alembic ./alembic

# Copy application code
COPY --chown=appuser:appuser app ./app

# Copy scripts from development stage
COPY --chown=appuser:appuser --from=development /app/scripts /app/scripts
RUN chmod +x /app/scripts/*.sh /app/scripts/*.py 2>/dev/null || true

# Copy alass-cli binary from development
COPY --from=development /usr/local/bin/alass-cli /usr/local/bin/alass-cli
RUN chmod +x /usr/local/bin/alass-cli

# Copy NLTK data from development
COPY --chown=appuser:appuser --from=development /app/nltk_data /app/nltk_data
ENV NLTK_DATA=/app/nltk_data

EXPOSE 8000

# Entrypoint and CMD
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# --- Production Stage (Worker) ---
FROM production-api AS production-worker
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=INFO"]
