# Project Charter: Subtitle Downloader Web Application

This document formally outlines the vision, scope, objectives, success metrics, and stakeholders for the Subtitle Downloader Web Application project.

## 1. Vision & Scope

*   **Core Vision:** To deliver a secure, role-based, internet-accessible web application enabling authorized users to execute a local Python subtitle downloader script, monitor its real-time progress via logs, and access a persistent history of executed jobs.
*   **Secondary Feature:** To provide a configurable single-page dashboard serving as a central hub with quick links to other self-hosted media services (e.g., qBittorrent, Plex, Jellyfin).
*   **Technology Scope:** The project will utilize a unified, container-first deployment strategy based on the following stack:
    *   **Backend API:** FastAPI (Python 3.12+)
    *   **Background Tasks:** Celery (Python) with Redis Broker/Backend
    *   **Frontend UI:** React + TypeScript (built with Vite, served by Nginx)
    *   **Reverse Proxy & TLS:** Caddy (v2.x)
    *   **Database:** PostgreSQL (v16+)
    *   **Orchestration:** Docker Compose (v2.20+)

## 2. Goals & Objectives

| Category        | Objective                                                                                                  |
| :-------------- | :--------------------------------------------------------------------------------------------------------- |
| **Primary**     | Provide a secure, robust, and user-friendly web interface for the subtitle downloader script, featuring live logs and persistent job history, accessible based on user roles (admin, standard). |
| **Secondary**   | Offer a configurable dashboard providing quick links and potentially status indicators for associated media server tools.                                                      |
| **Flexibility** | Ensure a container-native design for straightforward deployment, portability, and scalability across environments supporting Docker.                                        |

## 3. Success Metrics

*   **Reliability:** Achieve near-zero-downtime deployments using blue/green or rolling restarts via Caddy, targeting less than 30 seconds of user-perceived disruption during transitions.
*   **Performance:** Sustain 20 concurrent users actively initiating and monitoring subtitle download jobs with a P95 (95th percentile) API response latency below 250 milliseconds under typical load.
*   **Security:** Pass automated security scans (OWASP ZAP baseline, JWT attack suite) with zero critical or high-severity findings prior to release. Attain an 'A' grade or higher on Qualys SSL Labs test for the production deployment endpoint.
*   **Quality:** Maintain a minimum of 95% code coverage for backend unit and integration tests. Ensure zero linting errors reported by configured static analysis tools (ESLint for frontend, Ruff for backend) in the CI pipeline.

## 4. Stakeholders & Roles

| Role                 | Responsibility                                         | Owner                |
| :------------------- | :----------------------------------------------------- | :------------------- |
| Product Owner        | Defines vision, manages backlog, accepts deliverables | You ([Your Name/Handle]) |
| Technical Lead       | Oversees architecture, ensures code quality, reviews PRs | ChatGPT (AI Assistant) |
| DevOps Engineer      | Manages CI/CD pipeline, Docker infra, deployment       | You/[TBD]            |
| Frontend Developer   | Implements React UI, ensures accessibility, tests UI     | You/[TBD]            |
| Backend Developer    | Develops FastAPI API, Celery tasks, DB, security        | You/[TBD]            |

*(Note: Roles marked You/[TBD] indicate areas you will cover, potentially with AI assistance.)*

---