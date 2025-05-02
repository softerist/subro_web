# Architecture Vision: Subtitle Downloader Web Application (FastAPI Stack)

## Narrative Description

This application adopts a modern, containerized web architecture centered around a high-performance **FastAPI** backend API. The core goal is to provide a secure and responsive interface for managing a local subtitle downloading script.

**User Interaction Flow:**

1.  A user accesses the **React Single-Page Application (SPA)** served statically by an **Nginx** container.
2.  All traffic (frontend assets and API requests) is routed through a **Caddy** reverse proxy, which handles automatic HTTPS (TLS termination), applies security headers (HSTS, CSP, etc.), and directs requests appropriately.
3.  For API interactions (e.g., login, job submission, fetching history), Caddy proxies requests to the **FastAPI** backend container (`/api/*`).
4.  The FastAPI application handles authentication (JWT), authorization (role-based), data validation (Pydantic), and interacts with the **PostgreSQL** database for persistent storage (users, jobs, dashboard config).
5.  When a subtitle job is submitted, FastAPI enqueues a task message onto a **Redis** queue via the **Celery** library.
6.  A separate **Celery Worker** container monitors the Redis queue, picks up the job task, updates the job status in PostgreSQL, and executes the designated Python subtitle downloader script as a subprocess.
7.  The Celery worker captures `stdout`/`stderr` from the script and publishes log lines to a unique **Redis Pub/Sub** channel for that job.
8.  The FastAPI backend provides a **WebSocket** endpoint (`/ws/jobs/{job_id}`). When a user views a job's detail page, the React frontend establishes a WebSocket connection. The FastAPI backend subscribes to the relevant Redis Pub/Sub channel and forwards the log messages over the WebSocket to the frontend in near real-time.
9.  The entire stack (Caddy, Nginx, FastAPI, Celery Worker, PostgreSQL, Redis) is orchestrated using **Docker Compose**, ensuring consistent environments for development and production.

**Key Architectural Benefits:**

*   **Performance:** FastAPI provides high throughput for API requests. Celery enables non-blocking, asynchronous processing of potentially long-running subtitle jobs.
*   **Scalability:** Individual components (API instances, Celery workers) can be scaled independently if needed (though initial deployment uses single instances).
*   **Security:** Caddy handles TLS and security headers. FastAPI offers robust validation and dependency injection for security features. RBAC is implemented at the API level. Containerization provides process isolation.
*   **Maintainability:** Clear separation of concerns between frontend, backend API, and background workers. Use of modern tooling and linters promotes code quality.
*   **Developer Experience:** Hot reloading for frontend (Vite) and backend (Uvicorn/FastAPI) during development. Devcontainers provide a consistent environment.

## Core Component Interaction Diagram (Mermaid)

```mermaid
graph TD
    subgraph "User Browser"
        B[React SPA]
    end

    subgraph "Infrastructure (Docker Network)"
        C[Caddy Reverse Proxy <br/> (HTTPS, Headers, Routing)]

        subgraph "Frontend"
            FE_Nginx[Nginx <br/> (Serves Static React Build)]
        end

        subgraph "Backend"
            API[FastAPI <br/> (API Logic, Auth, WebSockets)]
            W[Celery Worker <br/> (Runs Script, Publishes Logs)]
            DB[(PostgreSQL <br/> Users, Jobs, Config)]
            R{{Redis <br/> Celery Broker/Backend, Pub/Sub}}
            Script(sub_downloader.py)
        end
    end

    B -- HTTPS Request --> C
    C -- Proxy Pass / --> FE_Nginx
    C -- Proxy Pass /api, /ws --> API

    API -- Read/Write --> DB
    API -- Enqueue Task --> R
    API -- Subscribe Logs --> R
    API -- Publish Logs --> B

    W -- Read/Write --> DB
    W -- Consume Task --> R
    W -- Execute --> Script
    Script -- stdout/stderr --> W
    W -- Publish Logs --> R

    FE_Nginx -- Serves JS/CSS/HTML --> B


graph TD
    subgraph "User Browser"
        B[React SPA]
    end

    subgraph "Infrastructure (Docker Network)"
        C[Caddy Reverse Proxy - HTTPS, Headers, Routing]

        subgraph "Frontend"
            FE_Nginx[Nginx - Serves Static React Build]
        end

        subgraph "Backend"
            API[FastAPI - API Logic, Auth, WebSockets]
            W[Celery Worker - Runs Script, Publishes Logs]
            DB[(PostgreSQL - Users, Jobs, Config)]
            R{{Redis - Celery Broker/Backend, Pub/Sub}}
            Script(sub_downloader.py)
        end
    end

    B -- HTTPS Request --> C
    C -- Proxy Pass / --> FE_Nginx
    C -- Proxy Pass /api, /ws --> API

    API -- Read/Write --> DB
    API -- Enqueue Task --> R
    API -- Subscribe Logs --> R
    API -- Publish Logs --> B

    W -- Read/Write --> DB
    W -- Consume Task --> R
    W -- Execute --> Script
    Script -- stdout/stderr --> W
    W -- Publish Logs --> R

    FE_Nginx -- Serves JS/CSS/HTML --> B

