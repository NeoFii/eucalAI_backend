# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Eucal AI backend — a mono-repo of Python microservices built with FastAPI, async SQLAlchemy (aiomysql), and Alembic migrations. Source lives under `src/` (src layout). Most services own their own database schema on MySQL 8.x; `router-service` is a CPU gateway (no DB, no ML deps) and `inference-service` handles GPU-based ML inference. Services communicate via HMAC-signed internal HTTP calls (`common/internal.py`); router and inference do not participate in HMAC.

## Services

All packages live under `src/`. Typical deployment uses `backend-app` (merged control plane) + `router-service` (CPU gateway) + `inference-service` (GPU inference) + `testing-scheduler` + `testing-worker`.

| Service | Module | Port | Purpose |
|---------|--------|------|---------|
| backend-app | `backend_app.main:app` | 8001 | Merged admin + user + testing control plane |
| user-service | `user_service` | 8000 | Registration, login, password |
| admin-service | `admin_service` | 8001 | Admin auth, super-admin, invite codes, audit (standalone mode) |
| testing-service | `testing_service` | 8002 | Model catalog, providers, quotes, benchmark (standalone mode) |
| router-service | `router_service` | 8003 | CPU gateway: API key auth, routing via inference-svc, upstream forwarding. No DB, no ML deps. |
| inference-service | `inference_service` | 8004 | GPU inference: Qwen backbone + 5 CG-TabM routers. No DB. |
| testing-scheduler | `testing_service.main:app` | 8012 | Scheduled probe dispatcher |
| testing-worker | `testing_service.worker` | — | Benchmark queue consumer (arq + Redis) |

Router runtime assets (`runtime_config.json`, `model_paths.json`) live under `deploy/router/`. Install inference ML deps with `uv sync --extra inference`.

`backend-app` merges admin/user/testing into one process but they still make HMAC-signed HTTP calls to themselves over loopback for wire compatibility with standalone deployments.

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
- Each DB-backed service has its own MySQL database (3 total: `eucal_ai_{admin,user,testing}`). Router has no DB.
- Async via `aiomysql` + `sqlalchemy[asyncio]`
- Migrations in `migrations/<service_name>/` — one Alembic env per DB service
- IDs are snowflake-based (`SnowflakeIdMixin`)

### Inter-service calls
Signed with `INTERNAL_SECRET` using headers `X-Internal-Service`, `X-Internal-Timestamp`, `X-Internal-Signature`. Verification via `common.internal.verify_internal_signature`. Calls include circuit breaker (threshold 3, cooldown 30s) and configurable retries. Key dependency graph:
- admin <-> user (bidirectional)
- testing -> admin (real-time identity verification on every admin request)
- router -> inference-svc (internal HTTP: `/internal/v1/classify`, shared secret via `X-Inference-Secret`)
- router -> user-service (API Key validation via backend-app)

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
- Tests use in-memory SQLite (`sqlite+aiosqlite:///:memory:`) and monkeypatch for mocking — no real DB required
- Alembic revisions are the schema source of truth; SQL snapshots in `scripts/sql/` are reference only

## Deployment
- Docker Compose in `deploy/docker-compose.yml` orchestrates backend-app + router-service + redis + testing-worker + testing-scheduler
- MySQL is managed separately (not in compose)
- `testing-scheduler` runs APScheduler in a separate process from `testing-service`
- `testing-worker` is an arq consumer process for the benchmark queue
