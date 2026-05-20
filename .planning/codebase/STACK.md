# Technology Stack

**Analysis Date:** 2026-05-20

## Languages

**Primary:**
- Python 3.12.x (runtime) — all services
- Python >=3.10 (minimum target in pyproject.toml)

**Secondary:**
- SQL (MySQL 8.0 DDL/DML via Alembic migrations and raw queries)

## Runtime

**Environment:**
- Python 3.12.3 (verified on deployment host)
- uvicorn >=0.34.0 (ASGI server, multi-worker mode)

**Package Manager:**
- uv (fast resolver/installer, replaces pip)
- Lockfiles: `uv.lock` present in each legacy service (`admin-service`, `user-service`, `router-service`, `inference-service`)
- api-service does NOT have a `uv.lock` yet (uses `pyproject.toml` directly)

## Frameworks

**Core:**
- FastAPI >=0.115.0 (api-service) / >=0.109.0 (legacy services) — HTTP framework
- Pydantic >=2.5.0 — request/response validation, model serialization
- pydantic-settings >=2.1.0 — typed configuration from `.env` files
- SQLAlchemy >=2.0.25 (async mode) — ORM + async engine + connection pooling
- Starlette (via FastAPI) — ASGI primitives, StreamingResponse for SSE relay

**Testing:**
- pytest >=8.0.0 — test runner
- pytest-asyncio >=0.23.0 — async test support (`asyncio_mode = "auto"`)
- coverage >=7.0 — code coverage measurement

**Build/Dev:**
- hatchling — PEP 517 build backend (all services)
- ruff >=0.4.0 — linting + formatting (replaces flake8, isort, black)
- mypy >=1.10.0 — static type checking (`disallow_untyped_defs = true`)

## Key Dependencies

**Critical (api-service `pyproject.toml`):**
- `openai>=1.40.0` — AsyncOpenAI SDK for upstream LLM relay (Chat Completions + Responses protocol)
- `anthropic>=0.34.0` — AsyncAnthropic SDK for upstream Anthropic Messages relay
- `sqlalchemy[asyncio]>=2.0.25` — async ORM with connection pooling
- `aiomysql>=0.2.0` — async MySQL driver
- `redis>=5.0` — async Redis client (`redis.asyncio`)
- `arq>=0.26.0` — async background job queue (Redis-backed)
- `python-jose[cryptography]>=3.3.1` — JWT encode/decode (HS256)
- `passlib[bcrypt]>=1.7.4` + `bcrypt>=3.2.0,<4.0.0` — password hashing
- `cryptography>=42.0.0` — AES-256-GCM encryption for provider API keys at rest

**Infrastructure:**
- `httpx>=0.26.0` — async HTTP client for internal service calls + inference-service
- `slowapi>=0.1.9` — HTTP rate limiting on admin/user endpoints
- `cachetools>=5.0.0` — in-memory TTL cache (API key validation, routing config)
- `snowflake-id>=1.0.0` — distributed ID generation (primary keys)
- `nanoid>=2.0.0` — user-facing UID generation (10-char external identifiers)
- `alembic>=1.14.0` — database schema migrations
- `email-validator>=2.1.0` — email format validation
- `python-multipart>=0.0.6` — multipart form data parsing
- `python-dotenv>=1.0.0` — `.env` file loading
- `tzdata>=2025.3` — timezone data

**Inference-service only:**
- `numpy>=1.26` — numerical computation
- `scikit-learn>=1.4` — ML utilities
- `torch>=2.1` — PyTorch deep learning framework
- `transformers>=4.40` — Hugging Face Transformers (Qwen2.5-7B backbone)

**Legacy services (admin-service, user-service):**
- `litellm>=1.0.0` — listed in deps but NOT actively used in api-service (replaced by direct SDK usage)

## Configuration

**Environment:**
- All config via pydantic-settings `BaseServiceSettings` → `ApiServiceSettings`
- Config file: `services/api-service/api_service/core/config.py`
- Base config: `services/api-service/api_service/common/config.py`
- `.env` file loaded automatically; `.env.example` documents all variables
- Startup validation: `JWT_SECRET_KEY` (>=32 chars), `INTERNAL_SECRET` (>=32 chars) required

**Key env vars:**
- `DATABASE_URL` — MySQL connection string (`mysql+aiomysql://...`)
- `REDIS_URL` — Redis db/0 (sessions, rate limiting)
- `CACHE_REDIS_URL` — Redis db/2 (routing config cache)
- `WORKER_QUEUE_REDIS_URL` — Redis db/1 (ARQ job queue)
- `JWT_SECRET_KEY` — JWT signing secret
- `INTERNAL_SECRET` — HMAC signing for inter-service calls
- `PROVIDER_SECRET_MASTER_KEY` — AES-256 master key for encrypting provider API keys
- `INFERENCE_SERVICE_URL` — inference-service endpoint
- `INFERENCE_SERVICE_SECRET` — shared secret for inference-service auth
- `SMTP_HOST/PORT/USER/PASSWORD` — email delivery (optional)

**Build:**
- `pyproject.toml` — per-service dependency declaration
- Build backend: hatchling
- Package index: `https://pypi.tuna.tsinghua.edu.cn/simple` (Tsinghua mirror, China)

## Platform Requirements

**Development:**
- Python 3.12+
- MySQL 8.0 (via Docker or local install)
- Redis 7+ (via Docker or local install)
- `uv` package manager
- Docker + Docker Compose (for infrastructure: `infra/docker-compose.local.yml`)

**Production:**
- Target: 2h4g server (2 CPU cores, 4GB RAM)
- api-service: 4 uvicorn workers × ~350MB ≈ 1.4GB + MySQL + Redis
- inference-service: separate GPU server (PyTorch + Qwen2.5-7B)
- Docker images: `python:3.12-slim` (router-service, inference-service), `python:3.11-slim` (legacy admin/user-service)

## Service Architecture (Current State)

| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| api-service | 8000 | Unified: user + admin + relay (merged) | **Active development** |
| inference-service | 8004 | GPU ML inference (difficulty routing) | Active |
| admin-service | 8001 | Admin backend (legacy, being merged) | Legacy |
| user-service | 8000 | User auth/billing (legacy, being merged) | Legacy |
| router-service | 8003 | API gateway/relay (legacy, being merged) | Legacy |

The project is consolidating from 4 microservices into 2: `api-service` (merged user + admin + router) and `inference-service` (GPU workload stays separate).

## Ruff Configuration (All Services)

```toml
target-version = "py310"
line-length = 100
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]
ignore = ["E501"]
quote-style = "double"
indent-style = "space"
```

## Mypy Configuration (All Services)

```toml
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

## Pytest Configuration (api-service)

```toml
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
```

---

*Stack analysis: 2026-05-20*
