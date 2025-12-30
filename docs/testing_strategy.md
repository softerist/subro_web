# Testing Strategy

This project uses a Docker-based workflow for backend and frontend tests to keep
parity with production dependencies (Postgres, Redis).

## Quick Start (All Tests)

1. Start the dev stack (override the host test DB port if 5433 is busy):

```bash
DB_TEST_PORT=5434 docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.override.yml --project-name subapp_dev up -d
```

1. Ensure the test database exists (first run only):

```bash
docker exec -i subapp_dev-db_test-1 createdb -U admin subappdb_pytest
```

1. Run tests:

```bash
make test
make test-ts
```

## Backend (pytest)

- `make test` runs pytest inside the `subapp_dev` API container.
- Settings come from `backend/.env.test`.
- If port 5433 is already in use, set `DB_TEST_PORT` before starting the stack.

## Frontend (vitest)

- `make test-ts` runs vitest inside the `subapp_dev` frontend container.

## Notes

- Integration tests call the running API at `http://localhost:8000`, so the dev
  stack must be up.
- If you run pytest locally (outside Docker), ensure Postgres is reachable on
  `localhost:5433` or update `backend/.env.test`.
