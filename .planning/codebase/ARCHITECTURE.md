<!-- refreshed: 2026-05-20 -->
# Architecture

**Analysis Date:** 2026-05-20

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Frontend (Vue/React SPA)                             │
└────────────┬──────────────────────────────────┬─────────────────────────────┘
             │ /api/v1/* (user + admin)         │ /v1/chat/completions
             │                                  │ /v1/messages
             │                                  │ /v1/responses
             ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          api-service (port 8000)                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ User Domain  │  │ Admin Domain │  │ Relay Domain │  │ Internal HMAC  │  │
│  │ (auth/keys/  │  │ (pools/model │  │ (LLM proxy   │  │ (routing-cfg   │  │
│  │  billing)    │  │  catalog/    │  │  + billing)  │  │  for inference)│  │
│  │              │  │  routing)    │  │              │  │                │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬───────┘  │
│         │                 │                  │                    │          │
│         └─────────────────┴──────────────────┴────────────────────┘          │
│                                    │                                         │
│                    ┌───────────────┼───────────────┐                         │
│                    ▼               ▼               ▼                         │
│              ┌──────────┐   ┌──────────┐   ┌──────────────┐                 │
│              │  MySQL   │   │  Redis   │   │ ARQ Worker   │                 │
│              │ eucal_ai │   │ db/0,1,2 │   │ (cron jobs)  │                 │
│              └──────────┘   └──────────┘   └──────────────┘                 │
└─────────────────────────────────────────────────────────────────────────────┘
             │ HTTP (HMAC-signed)
             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     inference-service (port 8004, GPU)                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Qwen2.5-7B backbone + 5× CG-TabM routing heads                     │   │
│  │  Classifies message difficulty → tier 1-5 → model selection          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Service Boundaries

| Service | Port | Responsibility | Status |
|---------|------|----------------|--------|
| **api-service** | 8000 | Unified service: user auth, admin, relay, billing | Active (merged target) |
| **user-service** | 8000 | User auth, keys, billing (legacy standalone) | Legacy — being merged into api-service |
| **admin-service** | 8001 | Admin panel, pools, routing config, model catalog (legacy) | Legacy — being merged into api-service |
| **router-service** | 8003 | LLM relay gateway (legacy, stateless) | Legacy — relay merged into api-service |
| **inference-service** | 8004 | GPU ML inference for difficulty classification | Active (standalone) |

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| User Auth | Registration, login, JWT, sessions, email verification | `services/api-service/api_service/controllers/auth.py` |
| API Keys | CRUD, validation, quota management | `services/api-service/api_service/controllers/keys.py` |
| Billing | Balance, transactions, topup, vouchers | `services/api-service/api_service/controllers/billing.py` |
| Admin Auth | Admin login, JWT, bootstrap super-admin | `services/api-service/api_service/controllers/admin/auth.py` |
| Pool Management | Provider pools, accounts, model configs | `services/api-service/api_service/controllers/admin/pools.py` |
| Model Catalog | Vendors, categories, models (public + admin) | `services/api-service/api_service/controllers/admin/model_catalog.py` |
| Routing Settings | Key-value routing config, weights, tier maps | `services/api-service/api_service/controllers/admin/routing_settings.py` |
| Relay (Chat) | OpenAI Chat Completions protocol proxy | `services/api-service/api_service/controllers/relay/chat.py` |
| Relay (Anthropic) | Anthropic Messages protocol proxy | `services/api-service/api_service/controllers/relay/anthropic.py` |
| Relay (Responses) | OpenAI Responses API protocol proxy | `services/api-service/api_service/controllers/relay/responses.py` |
| Relay Lifecycle | Orchestrates auth→route→upstream→billing→log | `services/api-service/api_service/relay/lifecycle/orchestrator.py` |
| Inference Client | HTTP client to inference-service /classify | `services/api-service/api_service/relay/inference_client.py` |
| Config Cache | Routing config: DB→Redis version poll→per-worker cache | `services/api-service/api_service/relay/config_cache.py` |
| ARQ Worker | Cron jobs: usage stats, cleanup, health checks, email | `services/api-service/api_service/core/jobs.py` |

## Pattern Overview

**Overall:** Layered monolith (api-service) + GPU microservice (inference-service)

**Key Characteristics:**
- Controller → Service → Repository → ORM Model layering
- Stateless services with `@staticmethod` + explicit `db: AsyncSession` parameter
- FastAPI dependency injection for auth, DB sessions, rate limiting
- Module-level singletons for relay infrastructure (config cache, SDK pool, rate limiter)
- HMAC-signed internal HTTP for service-to-service communication

## Layers

**Controllers:**
- Purpose: HTTP request parsing, response formatting, auth dependency injection
- Location: `services/api-service/api_service/controllers/`
- Contains: FastAPI routers with thin endpoint handlers
- Depends on: Services, Schemas, Dependencies
- Used by: FastAPI app router

**Services:**
- Purpose: Business logic orchestration, transaction management
- Location: `services/api-service/api_service/services/`
- Contains: Stateless `@staticmethod` methods with `db: AsyncSession` parameter
- Depends on: Repositories, Models, external clients
- Used by: Controllers

**Repositories:**
- Purpose: Data access abstraction over SQLAlchemy
- Location: `services/api-service/api_service/repositories/`
- Contains: `BaseRepository[ModelT]` subclasses with CRUD + pagination
- Depends on: ORM Models, SQLAlchemy session
- Used by: Services

**Models:**
- Purpose: SQLAlchemy ORM table definitions
- Location: `services/api-service/api_service/models/`
- Contains: 19 model classes + 3 enums (User, Admin, Billing, Routing domains)
- Depends on: SQLAlchemy Base, mixins
- Used by: Repositories, Services

**Relay:**
- Purpose: LLM proxy pipeline (auth, routing, upstream dispatch, billing, logging)
- Location: `services/api-service/api_service/relay/`
- Contains: Protocol adapters, SDK backends, billing, config cache, rate limiter
- Depends on: Models, Redis, inference-service, upstream LLM providers
- Used by: Relay controllers

**Common/Infra:**
- Purpose: Shared infrastructure (DB runtime, Redis, security, observability)
- Location: `services/api-service/api_service/common/`
- Contains: DB engine/session, Redis pools, JWT, crypto, exception handlers
- Depends on: SQLAlchemy, redis.asyncio, python-jose
- Used by: All layers

## Data Flow

### Primary Request Path: LLM Relay

1. **Client sends request** → `POST /v1/chat/completions` (`controllers/relay/chat.py:17`)
2. **API Key auth** → 3-tier lookup: TTLCache → Redis → DB (`relay/auth.py:107`)
3. **Rate limit check** → Redis sliding window (`relay/rate_limiter.py`)
4. **CallLifecycle.execute()** → orchestrates full pipeline (`relay/lifecycle/orchestrator.py:64`)
5. **Balance check** → Redis `user:quota:{user_id}` (`relay/lifecycle/orchestrator.py:95`)
6. **Route** → config_cache.load() + inference-service /classify → select model + channel (`relay/routing.py:40`)
7. **Upstream dispatch** → OpenAI/Anthropic SDK call via SdkClientPool (`relay/upstream_dispatch.py:16`)
8. **Stream/respond** → StreamingResponse with SSE or JSONResponse (`relay/lifecycle/orchestrator.py:188`)
9. **Finalize** → billing settle + call log update (fire-and-forget DB write) (`relay/lifecycle/finalize.py:26`)

### User Authentication Flow

1. **Login** → `POST /api/v1/auth/login` (`controllers/auth.py`)
2. **Validate credentials** → bcrypt verify via `asyncio.to_thread` (`services/auth_service.py`)
3. **Issue tokens** → JWT access (15min) + refresh (7d) + session record (`common/security/jwt.py`)
4. **Store session** → `user_sessions` table with refresh token hash
5. **Subsequent requests** → Bearer token → `get_current_user` dependency (`core/dependencies/user.py`)

### Admin Routing Config Update

1. **Admin updates setting** → `PUT /api/v1/admin/routing-settings/{key}` (`controllers/admin/routing_settings.py`)
2. **Service persists** → `routing_settings` table update (`services/admin/routing_setting_service.py`)
3. **Version bump** → `INCR routing_config:version` in Redis
4. **Workers detect** → Each api-service worker polls version on next request (`relay/config_cache.py:66`)
5. **Reload** → Full config rebuilt from DB (pools + accounts + model catalog + settings)
6. **Inference-service** → Polls `/internal/routing-config/active/inference` periodically

**State Management:**
- User balance: Redis `user:quota:{user_id}` (hot path) + `users.balance` column (persistence)
- Routing config: Redis version key + per-worker in-memory dict (rebuilt from DB on version change)
- API key validation: In-process TTLCache (60s, 2048 entries) → Redis `token:{hash}` → DB

## Key Abstractions

**RoutingConfigCache:**
- Purpose: Per-worker singleton holding full routing config (channels, prices, aliases, tier map)
- Examples: `services/api-service/api_service/relay/config_cache.py`
- Pattern: Redis version poll → DB reload on mismatch → synchronous `.load()` on every request

**CallLifecycle:**
- Purpose: Orchestrates a single relay request from auth through billing settlement
- Examples: `services/api-service/api_service/relay/lifecycle/orchestrator.py`
- Pattern: Builder-style init → `execute()` runs sequential pipeline with early-return errors

**ProtocolAdapter:**
- Purpose: Abstracts protocol differences (OpenAI Chat, Anthropic Messages, Responses API)
- Examples: `services/api-service/api_service/relay/adapters/openai_chat.py`, `anthropic_messages.py`, `openai_responses.py`
- Pattern: Protocol interface with `parse_request()`, `format_error()`, `create_stream_converter()`

**BaseRepository:**
- Purpose: Generic CRUD + paginated list with soft-delete awareness
- Examples: `services/api-service/api_service/common/infra/db/repository.py`
- Pattern: `BaseRepository[ModelT]` with `find_one()`, `get_list(ListParams)`, `add()`

**ServiceDatabaseRuntime:**
- Purpose: Manages async engine + session factory lifecycle per service
- Examples: `services/api-service/api_service/common/infra/db/runtime.py`
- Pattern: `create_engine()` → `init_session_factory()` → `get_db()` yields request-scoped session

## Entry Points

**api-service HTTP:**
- Location: `services/api-service/api_service/main.py`
- Triggers: `uvicorn api_service.main:app --workers 4`
- Responsibilities: All HTTP endpoints (user, admin, relay, internal, health)

**api-service ARQ Worker:**
- Location: `services/api-service/api_service/core/worker.py`
- Triggers: `arq api_service.core.worker.WorkerSettings`
- Responsibilities: Cron jobs (usage aggregation, session cleanup, balance reconciliation, health checks, email)

**inference-service HTTP:**
- Location: `services/inference-service/src/inference_service/main.py`
- Triggers: `uvicorn inference_service.main:app --port 8004`
- Responsibilities: `/internal/v1/classify` (ML inference), `/internal/logs` (log ring buffer)

## Architectural Constraints

- **Deployment:** api-service must fit 2h4g server (4 workers × ~350MB ≈ 1.4GB + MySQL + Redis)
- **Connection pools:** SQLAlchemy pool_size=5, max_overflow=10 per worker (4×15=60 total, within MySQL 151 limit)
- **Single database:** All 19 tables in one `eucal_ai` MySQL 8.0 database
- **Redis databases:** db/0 (sessions, rate limiting), db/1 (ARQ job queue), db/2 (routing config cache, token cache, billing)
- **No inter-service HTTP in hot path:** api-service relay does NOT call user-service/admin-service; only calls inference-service
- **Streaming:** SSE via Starlette StreamingResponse; billing finalization uses `asyncio.shield` on client disconnect
- **Global state:** Relay singletons (config_cache, sdk_pool, rate_limiter, channel_selector) initialized in LifespanRegistry

## Anti-Patterns

### Direct DB access in controllers

**What happens:** Controller directly queries ORM models instead of going through Service → Repository
**Why it's wrong:** Bypasses business logic, makes testing harder, violates layering
**Do this instead:** Always call a Service method. See `services/api-service/api_service/services/auth_service.py`

### Creating httpx clients per-request

**What happens:** `async with httpx.AsyncClient() as client:` inside a handler
**Why it's wrong:** Creates/destroys TCP connections on every request, no connection pooling
**Do this instead:** Use shared `InternalHttpPool` or `SdkClientPool`. See `services/api-service/api_service/relay/sdk_clients.py`

### Blocking calls in async context

**What happens:** Calling `bcrypt.hashpw()` or `smtplib.SMTP()` directly in async handler
**Why it's wrong:** Blocks the event loop, starves other requests
**Do this instead:** Wrap with `await asyncio.to_thread(blocking_fn, ...)`. See `services/api-service/api_service/core/jobs.py:209`

## Error Handling

**Strategy:** Layered exception hierarchy with global exception handlers

**Patterns:**
- Business exceptions defined in `common/core/exceptions.py` (e.g., `ApiKeyNotFoundException`, `InsufficientBalanceError`)
- Global `register_exception_handlers(app)` converts exceptions to `{code, message}` JSON + `X-Request-ID`
- Relay errors use `RoutingError(status_code, error_code, detail)` for protocol-specific formatting
- Redis failures are fail-open (D-06): degrade to DB fallback or trusted mode, never block requests

## Cross-Cutting Concerns

**Logging:** Structured JSON via `common/observability.py` → `log_event(logger, level, "eventName", key=value)`. Auto-injects request_id, trace_id. Sensitive data auto-redacted.

**Validation:** Pydantic v2 schemas for all request/response bodies. `ListParams` for paginated queries with time-range filtering.

**Authentication:**
- User: JWT Bearer token (access 15min + refresh 7d) via `get_current_user` dependency
- Admin: Separate JWT with role-based access (`require_active_admin`, `require_super_admin`)
- Relay: API Key via `require_api_key` (3-tier cache: TTLCache → Redis → DB)
- Internal: HMAC-SHA256 signature with timestamp anti-replay (`build_internal_auth_dependency`)

## Database Schema Overview

### User Domain Tables
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `users` | User accounts | id (snowflake), uid (nanoid), email, balance, rpm_limit |
| `user_sessions` | JWT refresh token sessions | user_id, refresh_token_hash, expires_at |
| `user_api_keys` | API keys for relay access | user_id, key_hash, status, quota_mode, quota_limit |
| `email_verification_codes` | Email OTP codes | email, code, purpose, expires_at |
| `balance_transactions` | Immutable ledger for all balance changes | user_id, type, amount, balance_before/after, ref_type/ref_id |
| `topup_orders` | Payment/topup order records | user_id, amount, status, payment_method |
| `api_call_logs` | Per-request audit log | request_id, user_id, model_name, tokens, cost, status, duration_ms |
| `usage_stats` | Hourly aggregated usage buckets | user_id, model, stat_hour, total_tokens, total_cost |
| `voucher_redemption_codes` | Promo/voucher codes | code, amount, status, redeemed_by |

### Admin Domain Tables
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `admin_users` | Admin accounts | id, uid, email, role (admin/super_admin), is_root |
| `admin_audit_logs` | Admin action audit trail | actor_admin_id, action, target_type, target_id |
| `audit_action_definitions` | Audit action metadata | action_key, category, label |

### Routing Domain Tables
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `pools` | Provider platform definitions | slug, base_url, priority, weight, is_enabled |
| `pool_model_configs` | Model availability per pool | pool_id, model_slug, upstream_model_id, cost_*_per_million |
| `pool_accounts` | API key accounts per pool | pool_id, api_key_enc (AES-256-GCM), status, rpm_limit |
| `routing_settings` | Key-value routing config | key, value, value_type, group_name |
| `model_vendors` | LLM vendor registry | slug, name, logo_url |
| `model_categories` | Model capability categories | key, name |
| `model_catalog` | Public model catalog | slug, routing_slug, vendor_id, sale_*_per_million |
| `model_catalog_category_map` | Model↔Category M:N | model_id, category_id |

## Caching Strategy (Redis)

| Redis DB | Purpose | Key Patterns |
|----------|---------|--------------|
| db/0 | Sessions, rate limiting | `session:{jti}`, `rate:{user_id}:{minute}` |
| db/1 | ARQ job queue | ARQ internal keys |
| db/2 | Routing config cache, token cache, billing | `routing_config:version`, `token:{hash}`, `user:quota:{user_id}` |

**Cache Invalidation:**
- Routing config: Admin write → `INCR routing_config:version` → workers detect on next request
- API key: Active invalidation via `invalidate_api_key_cache(key_hash)` + TTL expiry (60s)
- User balance: Redis DECRBY/INCRBY on relay billing; DB is source of truth for reconciliation

## Background Job Architecture (ARQ)

| Job | Schedule | Purpose |
|-----|----------|---------|
| `aggregate_usage_stats` | Every hour (minute=0) | Roll up api_call_logs into usage_stats buckets |
| `cleanup_expired_verification_codes` | Daily 03:00 | Remove used+expired email codes |
| `cleanup_expired_sessions` | Daily 03:30 | Remove sessions expired >7 days |
| `reconcile_balance_ledger` | Daily 04:30 | Detect drift between users.balance and transaction sum |
| `run_health_checks` | Every 10 minutes | Probe upstream pool accounts for availability |
| `send_verification_email` | On-demand (enqueued) | SMTP email send with 3× retry |

Worker runs in same process model as api-service (shares DB engine config), started via:
```bash
arq api_service.core.worker.WorkerSettings
```

## API Protocol Support

| Protocol | Endpoint | Adapter |
|----------|----------|---------|
| OpenAI Chat Completions | `POST /v1/chat/completions` | `relay/adapters/openai_chat.py` |
| Anthropic Messages | `POST /v1/messages` | `relay/adapters/anthropic_messages.py` |
| OpenAI Responses | `POST /v1/responses` | `relay/adapters/openai_responses.py` |
| Models List | `GET /v1/models` | `controllers/relay/models.py` |

All protocols share the same lifecycle pipeline (CallLifecycle) but use protocol-specific adapters for:
- Request parsing (normalize to OpenAI messages format for routing)
- Error response formatting (match upstream API error shapes)
- Stream chunk conversion (SSE event format differences)
- Non-stream response formatting

---

*Architecture analysis: 2026-05-20*
