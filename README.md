# Subtitle Downloader Web Application

[![CI Status](https://github.com/softerist/subro_web/actions/workflows/ci.yml/badge.svg)](https://github.com/softerist/subro_web/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) <!-- Choose appropriate license -->
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code Style: Prettier](https://img.shields.io/badge/code_style-prettier-ff69b4.svg)](https://prettier.io)

A secure, role-based web application to trigger a local subtitle downloader script, monitor job progress in real-time, view history, and access other self-hosted services via a dashboard. Built with FastAPI, Celery, React, Caddy, and Docker.

## Core Features

- **Access Control:** Granular roles (Standard, Admin, Superuser) with safe delegation:
  - **Password Management:** Admins can reset user passwords (forcing change on next login) and disable MFA for recovery.
  - **Path Safety:** Non-superusers are restricted to subdirectories of approved root paths.
  - **Statistics:** Translation usage metrics available to all authenticated users.
- Web interface to submit jobs (specifying target folder, language) to a Python subtitle downloader script.

## Production Deployment

Deploy the application using the included **Blue-Green Deployment** strategy for zero-downtime updates.

### Commands

| Command                    | Description                                                                                                                 | Use Case                                                                |
| :------------------------- | :-------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------- |
| `make prod`                | **Default Deployment**. Deploys the new stack and **re-encrypts** sensitive database fields (data encryption key rotation). | Use for regular maintenance or when rotating keys.                      |
| `make prod-skip-reencrypt` | **Fast Deployment**. Deploys the new stack **without** re-encrypting data.                                                  | Use for rapid iterations, hotfixes, or when key rotation is not needed. |

### Access Control & Recovery

- **Force Password Change:** Admins can flag users to require a password update on their next login.
- **MFA Reset:** Admins can disable 2FA for users who have lost their device (via the "Reset Password" dialog).
- **Strict Pathing:** To prevent file system exposure, standard admins can only add paths that are _children_ of existing root paths managed by Superusers.
- Real-time log streaming from running jobs via WebSockets.
- Persistent job history stored in PostgreSQL.
- Asynchronous job processing via Celery and Redis.
- Configurable dashboard linking to external media services (Plex, Jellyfin, etc.).
- Containerized deployment using Docker Compose.
- Automatic HTTPS via Caddy.

## 🏗 System Architecture

### Backend API & Job Processing

The backend utilizes a **FastAPI** application for HTTP endpoints and a **Celery** worker for asynchronous processing.

- **Job Submission:** Jobs are submitted via REST API, validated, and stored in **PostgreSQL**.
- **Execution:** A dedicated Celery worker executes the subtitle downloader script as a subprocess, ensuring isolation and stability.
- **Real-Time Logs:** The worker captures `stdout`/`stderr` line-by-line and publishes them to **Redis Pub/Sub**.
- **Live Streaming:** The API provides a **WebSocket** endpoint (`/api/v1/ws/jobs/{id}/logs`) that streams these logs to the client in real-time.
- **Security:** Authenticated via JWT; Jobs are protected by strict Role-Based Access Control (RBAC).

## Technology Stack

- **Backend API:** FastAPI (Python 3.12)
- **Background Tasks:** Celery, Redis
- **Frontend:** React (Vite), TypeScript, Tailwind CSS, Nginx (serving)
- **Reverse Proxy:** Caddy
- **Database:** PostgreSQL 16
- **Orchestration:** Docker Compose
- **Development:** VS Code Devcontainers, Pre-commit, Ruff, ESLint, Pytest, Vitest

## Quick Start (Development)

1. **Prerequisites:**

   - Docker & Docker Compose (v2+)
   - Git
   - Make (optional, for convenience)
   - `mkcert` (for trusted local HTTPS, recommended)
   - ASDF (optional, for managing Python/Node versions via `.tool-versions`)
   - Direnv (optional, for auto-loading `.env`)

2. **Clone the repository:**

   ```bash
   git clone https://github.com/softerist/subro_web.git
   cd subro_web
   ```

3. **Setup Environment:**

   - Copy the environment template: `cp .env.example .env`
   - Review and update `.env`. To automate building the first superuser, ensure these are set:

     ```bash
     FIRST_SUPERUSER_EMAIL=admin@example.com
     FIRST_SUPERUSER_PASSWORD=SecurePassword123 # Must have Upper, Lower, and Number
     ```

   - **Important:** When adding DeepL keys, use proper JSON array format: `DEEPL_API_KEYS=["key1:fx", "key2:fx"]` (no wrapping single quotes).
   - (Recommended) If using `mkcert` for local HTTPS:

     ```bash
     mkcert -install
     mkcert localhost 127.0.0.1 ::1
     ```

     (Ensure cert/key paths in Caddyfile/docker-compose match)

4. **Install Tool Versions (if using ASDF):**

   ```bash
   asdf install
   ```

5. **Build and Start Services:**

   - Using Make:

     ```bash
     make dev
     ```

   - Or directly with Docker Compose:

     ```bash
     docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.override.yml up --build -d
     ```

6. **Initial Setup & Admin Access:**

   There are two ways to initialize the system:

   - **Automated (Recommended):** Set the `FIRST_SUPERUSER_` variables in your `.env` (dev) or `.env.prod` (production) file BEFORE starting the containers. The system will detect these and bootstrap the admin account automatically.
   - **Setup Wizard:** If no environment variables are detected, visit `https://localhost/setup` on your first visit to create the initial superuser and configure API keys via the web interface.

   > [!IMPORTANT]
   > All passwords must meet complexity requirements: Minimum 8 characters, including at least one uppercase letter, one lowercase letter, and one number.

7. **Access the Application:**

   - Frontend: `https://localhost`
   - API Docs: `https://localhost/api/v1/docs`

8. **Stop Services:**
   - Using Make: `make compose-down`
   - Or directly: `docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.override.yml down`

## Testing

Run the test suites in Docker:

```bash
make test
make test-ts
```

## Documentation

- [Roadmap](./docs/roadmap.md)
- [WebSocket API](./docs/api/websockets.md)
- [Architecture Vision](./docs/architecture_vision.md)
- [Deployment Guide](./docs/deployment.md)
- [Testing Strategy](./docs/testing_strategy.md)
- [Security Model](./docs/security_model.md)
- [Architectural Decision Records (ADRs)](./docs/adr/)

## Production Sanity Check

Use the production sanity check script to validate health and basic job creation.

```bash
# Uses infra/.env.prod by default (falls back to .env.prod)
infra/scripts/prod_sanity_check.sh

# Include a quick job creation test (requires an API key)
SANITY_API_KEY=your_api_key infra/scripts/prod_sanity_check.sh

# Optional overrides
ENV_FILE=/path/to/.env.prod SANITY_FOLDER_PATH=/mnt/sata0/Media SANITY_INSECURE=1 infra/scripts/prod_sanity_check.sh
```

## Contributing

Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for details on how to contribute, coding standards, and the pull request process.

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details. <!-- Or choose/create your license -->
