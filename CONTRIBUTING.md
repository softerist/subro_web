# Contributing to Subtitle Downloader Web Application

Thank you for your interest in contributing! We welcome contributions from the community. Please follow these guidelines to ensure a smooth process.

## Code of Conduct

This project adheres to a Code of Conduct [Placeholder: Link to Code of Conduct file or section, e.g., CODE_OF_CONDUCT.md]. By participating, you are expected to uphold this code.

## Getting Started

1. Ensure you have the necessary prerequisites installed (Docker, Git, Make, etc. - see `README.md`).
2. Fork the repository on GitHub.
3. Clone your fork locally: `git clone git@github.com:your-username/your-repo.git`
4. Set up the development environment as described in the `README.md` Quick Start section.
5. Install pre-commit hooks: `pre-commit install --install-hooks && pre-commit install --hook-type commit-msg`

## Branching Strategy

We follow a trunk-based development model using the `main` branch as the single source of truth.

- All development work should happen on short-lived feature branches.
- Branch names should follow the pattern `feature/issue-ticket-brief-desc` (e.g., `feature/15-add-job-cancellation`).
- Create branches from the latest `main`.
- Keep branches focused on a single issue or feature.

## Commit Messages

- Commit messages **must** follow the [Conventional Commits specification](https://www.conventionalcommits.org/en/v1.0.0/).
- This allows for automated changelog generation and semantic versioning.
- A `commitizen` pre-commit hook is configured to help format messages correctly. You can use `git cz` or `cz c` if you have commitizen installed globally, or let the hook guide you during `git commit`.
- Example: `feat: add real-time log streaming via websockets`
- Example: `fix(api): correct authorization check for job details endpoint`
- Example: `docs: update architecture diagram for redis pubsub`
- Example: `chore: update pre-commit hook versions`

## Pull Request (PR) Process

1. Ensure your feature branch is up-to-date with the latest `main` branch (`git pull origin main --rebase`). Resolve any conflicts.
2. Make sure all tests pass (`make test`) and linting checks pass (`make lint`).
   - `make test` now includes functional tests AND security scans (Trivy, Semgrep).
   - You can run security scans individually with `make scan-vulns`, `make scan-secrets`, or `make scan-sast`.
3. Push your feature branch to your fork on GitHub.
4. Create a Pull Request from your feature branch to the original repository's `main` branch.
5. Provide a clear title and description for your PR, explaining the "what" and "why" of the changes. Link the relevant GitHub Issue if applicable (e.g., "Closes #15").
6. The CI pipeline must pass for the PR to be mergeable.
7. At least one approval from a maintainer (e.g., Technical Lead) is required for merging.
8. Address any code review feedback promptly. Push subsequent changes to the same feature branch; the PR will update automatically.
9. Once approved and CI passes, the maintainer will merge the PR using a squash merge to keep the `main` history clean.

## Coding Standards

- **Python (Backend):**
  - Follow PEP 8 guidelines.
  - Use Ruff for linting and isort for import sorting (enforced by pre-commit).
  - Use Black for code formatting (line length 100, enforced by pre-commit).
  - Use type hints extensively. Run MyPy for type checking.
- **TypeScript/React (Frontend):**
  - Follow standard React/TypeScript best practices.
  - Use ESLint for linting (enforced by pre-commit).
  - Use Prettier for code formatting (enforced by pre-commit).
- **General:**
  - Write clear, concise, and well-commented code where necessary.
  - Write unit and integration tests for new features and bug fixes. Aim for high test coverage (>95% backend).
  - Keep functions and components focused (Single Responsibility Principle).

## Comment Style

Good comments explain **WHY**, not **WHAT**. Code should be self-explanatory for what it does.

### Keep These Comments

- **Docstrings** for public functions/classes
- **WHY-reasoning** explaining non-obvious decisions or trade-offs
- **Linter directives:** `# noqa`, `# type: ignore`, `// eslint-disable`, `# fmt: off/on`
- **Side-effect imports:** Comments like `# Import... to ensure models are registered`

### Avoid These Comments

- Comments that restate what code does (e.g., `i += 1  # increment i`)
- Stale TODOs older than 6 months
- Debug markers (`# DEBUG`, `# INSERTED`)
- Excessive section dividers

### Style Guidelines

- **Section headers (if needed):** Use `# --- Section Name ---` format, max 1-2 per file
- **Inline comments:** Explain rationale only, not obvious logic
- **Docstrings:** Use Google-style format for consistency

## Issue Tracking

- We use GitHub Issues to track bugs, feature requests, and tasks.
- We use GitHub Projects (Kanban board) for visualizing work in progress (Todo → In Progress → Review → Done). Link issues to PRs.

## Questions?

Feel free to open an issue if you have questions about contributing or need clarification on anything.
