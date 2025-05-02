# Subtitle Downloader Web Application

[![CI Status](https://github.com/your-username/your-repo/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/your-repo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) <!-- Choose appropriate license -->
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code Style: Prettier](https://img.shields.io/badge/code_style-prettier-ff69b4.svg)](https://prettier.io)

A secure, role-based web application to trigger a local subtitle downloader script, monitor job progress in real-time, view history, and access other self-hosted services via a dashboard. Built with FastAPI, Celery, React, Caddy, and Docker.

## Core Features

*   Secure user authentication (JWT) and role-based access control (Admin/Standard).
*   Web interface to submit jobs (specifying target folder, language) to a Python subtitle downloader script.
*   Real-time log streaming from running jobs via WebSockets.
*   Persistent job history stored in PostgreSQL.
*   Asynchronous job processing via Celery and Redis.
*   Configurable dashboard linking to external media services (Plex, Jellyfin, etc.).
*   Containerized deployment using Docker Compose.
*   Automatic HTTPS via Caddy.

## Technology Stack

*   **Backend API:** FastAPI (Python 3.12)
*   **Background Tasks:** Celery, Redis
*   **Frontend:** React (Vite), TypeScript, Tailwind CSS, Nginx (serving)
*   **Reverse Proxy:** Caddy
*   **Database:** PostgreSQL 16
*   **Orchestration:** Docker Compose
*   **Development:** VS Code Devcontainers, Pre-commit, Ruff, ESLint, Pytest, Vitest

## Quick Start (Development)

1.  **Prerequisites:**
    *   Docker & Docker Compose (v2+)
    *   Git
    *   Make (optional, for convenience)
    *   `mkcert` (for trusted local HTTPS, recommended)
    *   ASDF (optional, for managing Python/Node versions via `.tool-versions`)
    *   Direnv (optional, for auto-loading `.env`)

2.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/your-repo.git
    cd your-repo
    ```

3.  **Setup Environment:**
    *   Copy the environment template: `cp .env.example .env`
    *   Review and update `.env` with necessary secrets (e.g., `JWT_SECRET_KEY`) and configurations. **Do not commit `.env`!**
    *   (Recommended) If using `mkcert` for local HTTPS:
        ```bash
        mkcert -install
        mkcert localhost 127.0.0.1 ::1
        # Ensure cert/key paths in Caddyfile/docker-compose match
        ```

4.  **Install Tool Versions (if using ASDF):**
    ```bash
    asdf install
    ```

5.  **Build and Start Services:**
    *   Using Make:
        ```bash
        make dev
        ```
    *   Or directly with Docker Compose:
        ```bash
        docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.override.yml up --build -d
        ```

6.  **Access the application:**
    *   Frontend: `https://localhost` (or your configured Caddy host)
    *   API Docs: `https://localhost/api/docs`

7.  **Stop Services:**
    *   Using Make: `make compose-down`
    *   Or directly: `docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.override.yml down`

## Documentation

*   [Roadmap](./docs/roadmap.md)
*   [Architecture Vision](./docs/architecture_vision.md)
*   [Deployment Guide](./docs/deployment.md) ([Link to TBD])
*   [Testing Strategy](./docs/testing_strategy.md) ([Link to TBD])
*   [Security Model](./docs/security_model.md) ([Link to TBD])
*   [Architectural Decision Records (ADRs)](./docs/adr/) ([Link to TBD])

## Contributing

Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for details on how to contribute, coding standards, and the pull request process.

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details. <!-- Or choose/create your license -->