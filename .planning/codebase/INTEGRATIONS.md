# External Integrations

**Analysis Date:** 2026-05-20

## APIs & External Services

**LLM Providers (upstream relay):**
- OpenAI-compatible endpoints — Chat Completions + Responses protocol relay
  - SDK: `openai>=1.40.0` (`AsyncOpenAI`)
  - Client pool: `api_service/relay/sdk_clients.py` (`SdkClientPool`, LRU-bounded, max 64)
  - Backend: `api_service/relay/backends/openai_backend.py`
- Anthropic — Messages protocol relay
  - SDK: `anthropic>=0.34.0` (`AsyncAnthropic`)
  - Client pool: same `SdkClientPool` in `api_service/relay/sdk_clients.py`
  - Backend: `api_service/relay/backends/anthropic_backend.py`
  - Native slug config: `ANTHROPIC_NATIVE_SLUGS` setting (default: `["anthropic"]`)

**Inference Service (internal):**
- Purpose: ML difficulty classification for intelligent routing (Qwen2.5-7B + CG-TabM)
  - Client: `api_service/relay/inference_client.py` (`InferenceClient`)
  - Transport: httpx with circuit breaker + retry
  - Auth: `X-Inference-Secret` header
  - Endpoint: `POST /internal/v1/classify`
  - Env: `INFERENCE_SERVICE_URL`, `INFERENCE_SERVICE_SECRET`

**SMTP (email delivery):**
- Purpose: verification code emails (registration, login, password reset)
  - Implementation: stdlib `smtplib` via `asyncio.to_thread()` in ARQ worker
  - Location: `api_service/core/jobs.py` (`_send_smtp_sync`, `send_verification_email`)
  - Env: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`
  - Behavior: silent no-op when SMTP not configured (mock mode for dev)

## Data Storage

**Databases:**
- MySQL 8.0 — primary relational database
  - Connection: `DATABASE_URL` env var (`mysql+aiomysql://...`)
  - Driver: `aiomysql>=0.2.0` (async)
  - ORM: SQLAlchemy 2.x async (`create_async_engine`)
  - Pool config: `DATABASE_POOL_SIZE=5`, `DATABASE_MAX_OVERFLOW=10`, `DATABASE_POOL_RECYCLE=1800`
  - Database name: `eucal_ai` (single merged DB post-consolidation)
  - Migrations: Alembic (`services/api-service/migrations/`)
  - Character set: `utf8mb4` with `utf8mb4_unicode_ci` collation
  - Docker: `infra/docker-compose.local.yml` (port 3307 → 3306)

**Caching:**
- Redis 7 (Alpine) — multi-purpose cache/queue/session store
  - Three logical databases:
    - db/0 (`REDIS_URL`): sessions, rate limiting, general cache
    - db/1 (`WORKER_QUEUE_REDIS_URL`): ARQ background job queue
    - db/2 (`CACHE_REDIS_URL`): routing config cache, relay token cache
  - Client: `redis.asyncio` (aliased as `aioredis`)
  - Initialization: `api_service/common/infra/redis.py` (db/0), `api_service/common/infra/cache.py` (db/2)
  - Docker: `infra/docker-compose.local.yml` (port 6380 → 6379, no persistence)

**In-Memory Caches:**
- `cachetools.TTLCache` — API key validation cache (2048 entries, 60s TTL)
  - Location: relay auth layer (`api_service/relay/auth.py`)
- Routing config two-tier cache: in-process dict (5s) → Redis db/2 (60s) → DB
  - Location: `api_service/relay/config_cache.py`

**File Storage:**
- Local filesystem only (logs directory)
- No cloud object storage integration

## Authentication & Identity

**User Authentication:**
- JWT access tokens (HS256, 15min expiry) + refresh tokens (7 days)
  - Library: `python-jose[cryptography]>=3.3.1`
  - Implementation: `api_service/common/security/jwt.py`
  - Secret: `JWT_SECRET_KEY` env var (minimum 32 chars, validated at startup)
- Password hashing: bcrypt via passlib
  - Library: `passlib[bcrypt]>=1.7.4`, `bcrypt>=3.2.0,<4.0.0`
  - Implementation: `api_service/common/security/password.py`
  - Async wrapper: `asyncio.to_thread()` for non-blocking hash

**API Key Authentication (relay endpoints):**
- Bearer token format for LLM relay requests
- In-memory TTL cache for validated keys (avoids DB hit per request)
- Implementation: `api_service/relay/auth.py`

**Internal Service Auth:**
- HMAC-SHA256 signed requests (canonical body + path + timestamp + caller)
  - Signing: `api_service/common/http/internal_signing.py`
  - Verification: `api_service/common/http/internal_auth.py`
  - Client: `api_service/common/internal.py` (`request_internal_json`)
  - TTL: 30s anti-replay window (`INTERNAL_REQUEST_TTL_SECONDS`)
  - Secret: `INTERNAL_SECRET` env var (minimum 32 chars)

**Admin Authentication:**
- Separate admin JWT tokens (`ADMIN_TOKEN_EXPIRE_MINUTES=480`)
- Super-admin bootstrap on startup (`api_service/services/admin/bootstrap_service.py`)

**Secrets at Rest:**
- Provider API keys encrypted with AES-256-GCM
  - Library: `cryptography>=42.0.0` (`AESGCM`)
  - Implementation: `api_service/common/security/crypto.py`
  - Master key: `PROVIDER_SECRET_MASTER_KEY` env var (64-char hex = 32 bytes)

## Monitoring & Observability

**Error Tracking:**
- No external error tracking service (Sentry, etc.)
- Structured JSON logging with automatic sensitive data redaction

**Logs:**
- Structured JSON logging via `api_service/common/observability.py`
- `log_event(logger, level, "eventName", key=value)` pattern
- Request context auto-injection: `request_id`, `trace_id`, `span_id`, `uid`
- Ring buffer for recent logs (`LOG_RING_BUFFER_CAPACITY=2000`)
- File rotation: 50MB max, 5 backups, 30-day retention
- Sensitive data auto-redaction in observability layer

**Health Checks:**
- Liveness: `GET /health` (always returns healthy if process running)
- Readiness: `GET /ready` (checks DB + Redis db/0 + Redis db/2)
- Proactive channel health probing: ARQ cron every 10 minutes (`run_health_checks`)

## CI/CD & Deployment

**Hosting:**
- Self-hosted (2h4g server for api-service)
- Separate GPU server for inference-service
- Docker containers with multi-stage builds

**CI Pipeline:**
- No GitHub Actions workflow detected (`.github/` contains only `pr_template.md`)
- Manual deployment via Docker

**Docker:**
- Infrastructure: `infra/docker-compose.yml` (production), `infra/docker-compose.local.yml` (dev)
- Per-service Dockerfiles with multi-stage builds (builder + runner)
- Base images: `python:3.12-slim` (api-service target), `python:3.11-slim` (legacy services)
- Non-root user (`appuser`) in production containers
- uvicorn with `--workers 4` in CMD

## Background Jobs (ARQ)

**Queue:** Redis db/1 via ARQ

**Worker entrypoint:** `arq api_service.core.worker.WorkerSettings`

**Registered jobs:**
| Job | Schedule | Purpose |
|-----|----------|---------|
| `aggregate_usage_stats` | Hourly (minute=0) | Aggregate call logs into usage_stats buckets |
| `cleanup_expired_verification_codes` | Daily (03:00) | Remove expired+used verification codes |
| `cleanup_expired_sessions` | Daily (03:30) | Remove sessions expired >7 days |
| `reconcile_balance_ledger` | Daily (04:30) | Detect balance drift vs transaction sum |
| `send_verification_email` | On-demand (enqueued) | Send SMTP verification emails (3 retries) |
| `run_health_checks` | Every 10 min | Proactive upstream channel health probing |

**Config:** `max_jobs=5`, `job_timeout=300s`

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## Rate Limiting

**User/Admin API endpoints:**
- `slowapi>=0.1.9` — decorator-based rate limiting

**Relay endpoints:**
- Custom Redis-based rate limiter: `api_service/relay/rate_limiter.py`
- Per-user RPM limit (`RATE_LIMIT_DEFAULT_USER_RPM=20`)
- Global RPM limit (`RATE_LIMIT_GLOBAL_RPM=0` = disabled)
- Sliding window implementation using Redis

## Inter-Service Communication

**api-service → inference-service:**
- Transport: httpx (`InferenceClient`)
- Auth: `X-Inference-Secret` header
- Circuit breaker: threshold=3, cooldown=30s
- Retry: 1 retry with 0.2s backoff

**Internal HTTP framework (`common/internal.py`):**
- Shared httpx client pool (connection reuse)
- HMAC-SHA256 signed requests
- Circuit breaker per target service
- Retry with linear backoff
- Limits: `max_connections=20`, `max_keepalive_connections=10`

## ID Generation

**Primary keys:**
- Snowflake IDs via `snowflake-id>=1.0.0`
- Worker ID derived from PID: `os.getpid() % 32`
- Datacenter ID configurable (`SNOWFLAKE_DATACENTER_ID=1`)

**User-facing identifiers:**
- NanoID 10-char UIDs via `nanoid>=2.0.0`
- Used for: `user_uid`, API key prefixes, external references

## Environment Configuration

**Required env vars (startup fails without):**
- `JWT_SECRET_KEY` (>=32 chars)
- `INTERNAL_SECRET` (>=32 chars)
- `PROVIDER_SECRET_MASTER_KEY` (64-char hex)
- `DATABASE_URL`

**Optional env vars:**
- `REDIS_URL` (defaults to `redis://127.0.0.1:6379/0`)
- `CACHE_REDIS_URL` (defaults to `redis://127.0.0.1:6379/2`)
- `WORKER_QUEUE_REDIS_URL` (defaults to `redis://127.0.0.1:6379/1`)
- `INFERENCE_SERVICE_URL` (defaults to `http://127.0.0.1:8004`)
- `SMTP_*` (optional, mock mode when unconfigured)

**Secrets location:**
- Environment variables (loaded from `.env` file in development)
- `.env` file present but gitignored
- `.env.example` documents all variables: `services/api-service/.env.example`

---

*Integration audit: 2026-05-20*
