# TASK-01: Project Scaffolding

## Objective
Set up the monorepo structure for the Meridian Marketplace deep example, establishing all top-level directories, package managers, and the local development orchestration layer.

## Components
- `next-app/` — Next.js dashboard (pnpm or bun)
- `django-api/` — Django backend with Strawberry GraphQL (uv)
- `fastapi-agent/` — FastAPI alert-enrichment agent (uv)
- `shared/openslo/` — OpenSLO YAML definitions and generated PrometheusRule CRDs
- `docker-compose.yaml` — Local development stack (Postgres, Prometheus, Alertmanager, all services)
- Root `Makefile` — Unified build/run/test commands
- Root `pyproject.toml` or workspace config as needed

## Steps
1. Create top-level directories: `next-app/`, `django-api/`, `fastapi-agent/`, `shared/openslo/`.
2. Initialize `django-api/` with `uv init` and add Django, Strawberry, psycopg dependencies.
3. Initialize `fastapi-agent/` with `uv init` and add FastAPI, uvicorn, httpx, pyyaml dependencies.
4. Initialize `next-app/` with `pnpm create next-app` (or `bun create next-app`), TypeScript enabled.
5. Create `docker-compose.yaml` with services: postgres, prometheus, alertmanager, django-api, fastapi-agent, next-app. Use health checks and dependency ordering.
6. Create root `Makefile` with targets: `up`, `down`, `build`, `migrate`, `seed`, `test`, `lint`, `clean`.
7. Add a root `.env.example` documenting required environment variables.
8. Add `.gitignore` entries for each sub-project (Python venvs, node_modules, __pycache__, .next).
9. Verify `make up` brings the full stack online with `docker compose up --build`.

## Acceptance Criteria
- [ ] All four sub-project directories exist with valid package manifests
- [ ] `uv sync` succeeds in both Python projects
- [ ] `pnpm install` (or `bun install`) succeeds in `next-app/`
- [ ] `docker compose up --build` starts all services without errors
- [ ] `make up` and `make down` work as documented
- [ ] Each service responds on its expected port (Django 8000, FastAPI 8001, Next.js 3000)

## Dependencies
- None — this is the foundational task

## Estimated Complexity
Medium
