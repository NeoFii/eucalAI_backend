# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Eucal AI backend — a mono-repo of Python microservices built with FastAPI, async SQLAlchemy (aiomysql), and Alembic migrations. Source lives under `src/` (src layout). Most services own their own database schema on MySQL 8.x; `router-service` is a pure ML inference service and has no DB. Services communicate via HMAC-signed internal HTTP calls (`common/internal.py`); router does not participate in HMAC.

## Services

All packages live under `src/`. Typical deployment uses `backend-app` (merged control plane) + `router-service` (scalable hot path) + `testing-scheduler` + `testing-worker`.

| Service | Module | Port | Purpose |
|---------|--------|------|---------|
| backend-app | `backend_app.main:app` | 8001 | Merged admin + user + content + testing control plane |
| user-service | `user_service` | 8000 | Registration, login, password, news proxy (standalone mode) |
| admin-service | `admin_service` | 8001 | Admin auth, super-admin, invite codes, audit (standalone mode) |
| testing-service | `testing_service` | 8002 | Model catalog, providers, quotes, benchmark (standalone mode) |
| router-service | `router_service` | 8003 | ML inference routing (numpy/torch/transformers). No DB. |
| content-service | `content_service` | 8004 | News CRUD (standalone mode) |
| testing-scheduler | `testing_service.main:app` | 8012 | Scheduled probe dispatcher |
| testing-worker | `testing_service.worker` | — | Benchmark queue consumer (arq + Redis) |

Router runtime assets (`runtime_config.json`, `model_paths.json`) live under `deploy/router/`. Install router ML deps with `uv sync --extra router`.

## Common Commands

```bash
# Install dependencies (uses uv, not pip)
uv sync

# Start all services (runs preflight checks first)
uv run start
uv run start --dev          # with hot-reload
uv run start admin-service user-service  # subset

# Environment validation
uv run check-env

# Database migrations (Alembic per-service)
uv run migrate --service admin-service upgrade head
uv run migrate --service user-service revision -m "description" --autogenerate

# Bulk migrate all services
uv run bootstrap-databases

# Bootstrap super-admin (run AFTER migrations)
uv run bootstrap-super-admin --skip-init-db
uv run bootstrap-super-admin --check-only --skip-init-db

# Run tests
uv run pytest
uv run pytest tests/test_admin.py          # single file
uv run pytest tests/test_admin.py::test_fn -v  # single test

# Lint
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy .
```

## Architecture

### Service structure (each service follows this pattern)
```
<service>/
  main.py          — FastAPI app with lifespan (engine init, bootstrap)
  config.py        — Service-specific Settings(BaseServiceSettings)
  db.py            — ServiceDatabaseRuntime wrapper, get_session dependency
  models/          — SQLAlchemy ORM models (DeclarativeBase per service)
  schemas.py       — Pydantic request/response schemas
  api/v1/          — Versioned route modules
  services/        — Business logic layer
  dependencies.py  — FastAPI Depends (auth, sessions)
```

### Shared layer (`common/`)
- `config.py` — `BaseServiceSettings` (pydantic-settings, reads `.env`)
- `db/` — `ServiceDatabaseRuntime` (async engine + session factory), `SnowflakeIdMixin`, `TimestampMixin`
- `internal.py` — HMAC-signed HTTP client for service-to-service calls (circuit breaker, retries)
- `core/` — Global exception handlers
- `utils/` — JWT, password hashing, snowflake IDs, crypto, timezone, OpenAI-compat helpers
- `health.py` — `/ready` and `/health` response builders
- `observability.py` — Structured logging, request-ID propagation

### Database
- Each DB-backed service has its own MySQL database (4 total: `eucal_ai_{admin,user,content,testing}`). Router has no DB.
- Async via `aiomysql` + `sqlalchemy[asyncio]`
- Migrations in `migrations/<service_name>/` — one Alembic env per DB service
- IDs are snowflake-based (`SnowflakeIdMixin`)

### Inter-service calls
Signed with `INTERNAL_SECRET` using headers `X-Internal-Service`, `X-Internal-Timestamp`, `X-Internal-Signature`. Verification via `common.internal.verify_internal_signature`. Key dependency graph:
- admin <-> user (bidirectional)
- user -> content
- testing -> admin

### Config
All config via `.env` loaded by pydantic-settings. Each service config extends `BaseServiceSettings` and maps `<SERVICE>_DATABASE_URL` to its local `DATABASE_URL`. No generic `DATABASE_URL` fallback exists.

## Tech Stack
- Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic
- MySQL 8.x (aiomysql), Redis 7.x (arq for benchmark queue)
- litellm for LLM routing, uv for package management
- Ruff for linting (line-length 100), mypy for type checking

## Testing
- pytest with `asyncio_mode = "auto"` — all async tests run automatically
- Tests in `tests/` directory, covering architecture boundaries, schema drift, runtime orchestration, and service-specific logic
