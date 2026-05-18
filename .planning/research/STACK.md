# Technology Stack

**Project:** EucalAI Backend — Architecture Consolidation (4 microservices to 2)
**Researched:** 2026-05-18
**Overall Confidence:** HIGH (stack is already validated in production; this is consolidation, not greenfield)

## Recommended Stack

### Runtime

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12.x | Runtime | Already deployed. 3.12 has significant perf improvements (specializing interpreter, comprehension inlining). No reason to jump to 3.13 mid-refactor. |
| uvicorn | >=0.34.0 | ASGI server | Production-proven, `--workers N` for multi-process. Already in use. Pin to 0.34+ for HTTP/2 and improved shutdown. |

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI | >=0.115.0 | HTTP framework | Already in use. 0.115+ has Pydantic v2 native, improved dependency injection perf, lifespan context. |
| Pydantic | >=2.5.0 | Validation/serialization | Already in use. v2 is 5-50x faster than v1 for model validation. Critical for relay request parsing. |
| pydantic-settings | >=2.1.0 | Configuration | Already in use. Supports `AliasChoices`, env file loading, nested models. |
| Starlette | (via FastAPI) | ASGI primitives | StreamingResponse for SSE relay, middleware, background tasks. Comes with FastAPI. |

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLAlchemy | >=2.0.25 | ORM + async engine | Already in use. 2.0 async is mature. `create_async_engine` with connection pooling handles the merged workload. |
| aiomysql | >=0.2.0 | MySQL async driver | Already in use. Lightweight, stable. Alternative asyncmy has marginal perf gains but less ecosystem support. |
| MySQL 8.0 | 8.0.x | Primary database | Already deployed. Single `eucal_ai` database post-merge. |
| Alembic | >=1.14.0 | Schema migrations | Already in use. Single migration chain for merged database. |

### Caching & Queues

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Redis | >=5.0.0 (client) | Cache + rate limiting + pub/sub | Already in use. Three logical databases: db/0 (sessions/general), db/1 (ARQ queue), db/2 (routing config cache). |
| ARQ | >=0.26.0 | Background job queue | Already in use. Lightweight Redis-backed async task queue. Handles health checks, stats aggregation, email sending. |

### HTTP Client & LLM SDKs

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| httpx | >=0.26.0 | Internal HTTP + inference-service calls | Already in use. Async, connection pooling, timeout control. Only remaining HTTP call is to inference-service. |
| openai | >=1.40.0 | OpenAI-compatible upstream calls | Already in use. Official SDK with streaming, retry, timeout. Used for Chat Completions + Responses protocol relay. |
| anthropic | >=0.34.0 | Anthropic upstream calls | Already in use. Official SDK with streaming. Used for Messages protocol relay. |

### Authentication & Security

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| python-jose[cryptography] | >=3.3.1 | JWT encode/decode | Already in use. Supports RS256/HS256. Handles user + admin token types. |
| passlib[bcrypt] | >=1.7.4 | Password hashing | Already in use. Wraps bcrypt with `asyncio.to_thread()` for non-blocking hash. |
| bcrypt | >=3.2.0,<4.0.0 | Bcrypt backend | Pin <4.0 because passlib has compatibility issues with bcrypt 4.x API changes. |
| cryptography | >=42.0.0 | AES-256-GCM for pool account secrets | Already in use for encrypting provider API keys at rest. |

### Utilities

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| snowflake-id | >=1.0.0 | Distributed ID generation | Already in use. worker_id=1 (user tables), worker_id=2 (admin tables). No collision post-merge. |
| nanoid | >=2.0.0 | User-facing UIDs | Already in use. 10-char NanoID for external identifiers (user_uid, key prefix). |
| cachetools | >=5.0.0 | In-memory TTL cache | Already in use. `TTLCache` for API key validation cache (2048 entries, 60s TTL). |
| slowapi | >=0.1.9 | HTTP rate limiting | Already in use for admin/user endpoints. Relay uses custom Redis-based rate limiter. |

### Dev Tools

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| ruff | latest | Linting + formatting | Already configured. Fast, replaces flake8+isort+black. |
| mypy | latest | Type checking | Already configured with `--strict` on router-service. |
| hatchling | latest | Build backend | Already in use. Simple, fast PEP 517 builds. |
| uv | latest | Package manager | Already in use. 10-100x faster than pip for resolution and install. |

## Key Architecture Decisions for Merged Stack

### Connection Pool Sizing (CRITICAL for 2h4g server)

```python
# SQLAlchemy engine configuration for api-service
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,          # Base connections per worker
    max_overflow=5,        # Burst capacity
    pool_timeout=30,       # Wait for connection before error
    pool_recycle=3600,     # Recycle connections every hour (MySQL wait_timeout)
    pool_pre_ping=True,    # Detect stale connections
    echo=False,
)
```

**Rationale:** 4 uvicorn workers x (10 + 5) = 60 max MySQL connections. MySQL 8.0 default `max_connections=151`. Leaves headroom for ARQ worker (separate pool of 5) and admin tools.

### Redis Connection Strategy

```python
# Separate pools for different concerns
redis_main = Redis.from_url(REDIS_URL, decode_responses=True, max_connections=20)
redis_cache = Redis.from_url(CACHE_REDIS_URL, decode_responses=True, max_connections=10)
```

**Rationale:** Isolate cache operations (routing config, API key cache) from session/rate-limit operations. Prevents cache stampede from blocking auth checks.

### Uvicorn Worker Configuration

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4 --limit-concurrency 100
```

**Rationale:** 4 workers on 2-core CPU provides good concurrency for I/O-bound workload. `--limit-concurrency 100` prevents memory exhaustion under load spikes. Each worker ~350MB = 1.4GB total.

### Streaming Relay Pattern

```python
# Use Starlette StreamingResponse for SSE relay
async def relay_stream(upstream_stream):
    async for chunk in upstream_stream:
        yield f"data: {chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"

return StreamingResponse(
    relay_stream(response),
    media_type="text/event-stream",
    headers={"X-Accel-Buffering": "no"},  # Nginx pass-through
)
```

### Fire-and-Forget DB Writes

```python
# Replace CallLogBuffer HTTP batch with direct async DB write
async def _write_call_log(log_data: dict) -> None:
    try:
        async with get_db_context() as db:
            db.add(ApiCallLog(**log_data))
            await db.commit()
    except Exception:
        logger.warning("call_log_write_failed", exc_info=True)

# Non-blocking: doesn't hold up the response
asyncio.create_task(_write_call_log(log_data))
```

**Rationale:** Same-process DB write is simpler and more reliable than HTTP buffer+batch. If write volume grows, switch to `asyncio.Queue` + periodic flush (still in-process, no HTTP).

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| ASGI Server | uvicorn (multi-worker) | gunicorn + uvicorn workers | Unnecessary complexity for 4 workers. uvicorn `--workers` is sufficient. gunicorn adds process management overhead with no benefit at this scale. |
| MySQL Driver | aiomysql | asyncmy | asyncmy claims better perf but has fewer users, less battle-tested. aiomysql is already working in production. Not worth the migration risk. |
| Task Queue | ARQ | Celery | Celery is overkill for this workload (health checks, stats). ARQ is async-native, Redis-backed, minimal overhead. Already in use. |
| JWT Library | python-jose | PyJWT | python-jose already in use, supports JWE if needed later. PyJWT is simpler but would require migration effort for zero benefit. |
| Rate Limiting | Custom Redis (relay) + slowapi (API) | redis-py-cluster rate limiting | Single Redis instance is sufficient at current scale. Custom implementation gives exact control over token bucket + sliding window semantics. |
| HTTP Client | httpx | aiohttp | httpx has better API, type hints, and is already in use. aiohttp would require rewriting all HTTP client code. |
| LLM Relay | openai + anthropic SDKs | litellm | litellm adds abstraction overhead and version churn. Direct SDK usage gives full control over streaming, error handling, and protocol-specific features. The existing router-service already uses direct SDKs for relay. |
| Config | pydantic-settings | dynaconf / python-decouple | pydantic-settings integrates natively with FastAPI's DI. Type-safe, validates at startup. Already in use. |
| ID Generation | snowflake-id | UUID v7 | Snowflake IDs already in production data. Switching would require data migration. Snowflake gives time-ordering + worker isolation. |
| Password Hashing | passlib + bcrypt<4 | argon2-cffi | bcrypt is industry standard, already in production. argon2 is theoretically better but requires tuning and passlib already wraps bcrypt well. |

## What NOT to Use

| Technology | Why Avoid |
|------------|-----------|
| litellm (for relay) | Adds 50+ MB of dependencies, version churn every week, abstracts away protocol details you need to control (streaming chunk format, error mapping, token counting). Use direct openai/anthropic SDKs. |
| Celery | Massive dependency tree, requires separate broker config, overkill for 3-4 background job types. ARQ is async-native and already working. |
| SQLModel | Thin wrapper over SQLAlchemy that adds confusion about which API to use. Pure SQLAlchemy 2.0 is clearer and more powerful. |
| asyncmy | Marginal perf gain not worth the risk of switching MySQL drivers mid-refactor. |
| gunicorn | Adds process manager complexity. uvicorn `--workers` handles multi-process fine for 4 workers. |
| FastAPI-Cache | Adds decorator magic that's hard to invalidate precisely. Manual Redis cache with explicit invalidation (RoutingConfigCache pattern) is more predictable. |
| Dramatiq | Another task queue option but not async-native. ARQ is the right choice for async FastAPI. |
| bcrypt>=4.0.0 | Breaking API change that passlib hasn't fully adapted to. Pin <4.0 until passlib releases a compatible version or migrate to argon2. |

## Performance Configuration

### SQLAlchemy Session Strategy

```python
# Use scoped sessions per-request via FastAPI dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

**Key:** Do NOT auto-commit. Explicit `await db.commit()` in service layer gives transaction control. The dependency provides rollback-on-exception safety net.

### API Key Validation Cache

```python
from cachetools import TTLCache

# In-process cache avoids DB hit on every relay request
_api_key_cache: TTLCache = TTLCache(maxsize=2048, ttl=60)
```

**Rationale:** Relay requests are the hot path. Caching validated API keys for 60s means most requests skip DB entirely. 2048 entries covers typical active key count. TTL ensures revoked keys stop working within 60s.

### Routing Config Cache (Redis + DB)

```python
# Two-tier cache: in-process dict (5s) -> Redis (60s) -> DB
# Admin writes invalidate Redis key, forcing reload on next request
```

**Rationale:** Routing config changes rarely (admin action). 60s Redis TTL is acceptable staleness. Admin invalidation ensures urgent changes propagate within seconds.

## Installation

```bash
# Core dependencies (api-service pyproject.toml)
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-multipart>=0.0.6",
    "email-validator>=2.1.0",
    "httpx>=0.26.0",
    "slowapi>=0.1.9",
    "sqlalchemy[asyncio]>=2.0.25",
    "aiomysql>=0.2.0",
    "alembic>=1.14.0",
    "cryptography>=42.0.0",
    "python-jose[cryptography]>=3.3.1",
    "passlib[bcrypt]>=1.7.4",
    "bcrypt>=3.2.0,<4.0.0",
    "snowflake-id>=1.0.0",
    "nanoid>=2.0.0",
    "python-dotenv>=1.0.0",
    "tzdata>=2025.3",
    "cachetools>=5.0.0",
    "arq>=0.26.0",
    "redis>=5.0",
    "openai>=1.40.0",
    "anthropic>=0.34.0",
]

# Dev dependencies
[project.optional-dependencies]
dev = [
    "ruff>=0.4.0",
    "mypy>=1.10.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx",  # for TestClient
    "coverage>=7.0",
]
```

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Core framework (FastAPI + SQLAlchemy + Pydantic) | HIGH | Already in production across all 4 services. Versions verified from installed packages. |
| Database (MySQL + aiomysql + Alembic) | HIGH | Already in production. Merge is additive (combine two DBs), no driver change. |
| Caching (Redis + cachetools) | HIGH | Already in production. RoutingConfigCache pattern is well-defined in architecture doc. |
| LLM SDKs (openai + anthropic) | HIGH | Already in production in router-service. Direct SDK usage is the right pattern for protocol relay. |
| Connection pool sizing | MEDIUM | Calculated from 2h4g constraints but needs load testing to validate. May need tuning. |
| bcrypt version pin | MEDIUM | passlib + bcrypt<4 compatibility is a known issue but the exact resolution timeline is unclear. Monitor for passlib updates. |

## Sources

- Installed package versions verified via `pip show` on the deployment environment (Python 3.12.3)
- Architecture decisions from `docs/architecture-refactoring.md` (project internal)
- Service patterns from existing CLAUDE.md files in admin-service, user-service, router-service
- SQLAlchemy 2.0 async patterns from existing `common/db/runtime.py` implementations
- Connection pool math: 4 workers x 15 connections = 60, within MySQL 8.0 default limit of 151
