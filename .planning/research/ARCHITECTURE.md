# Architecture Patterns

**Domain:** Consolidated LLM API Gateway (4 microservices -> 2 services)
**Researched:** 2026-05-18
**Confidence:** HIGH (based on existing codebase analysis + established FastAPI patterns)

## Recommended Architecture

### High-Level: Layered Monolith with Domain Modules

The consolidated `api-service` follows a **layered monolith** pattern (inspired by new-api's Go structure), where a single process hosts multiple domain modules that share infrastructure (DB, Redis, HTTP server) but maintain logical separation through directory boundaries and dependency injection.

```
                         ┌─────────────────────────────────────────────────────────────┐
                         │                      api-service :8000                       │
                         │                                                             │
  ┌──────────────┐       │  ┌─────────────────────────────────────────────────────┐   │
  │ User Frontend│──────>│  │  Middleware Stack                                    │   │
  └──────────────┘       │  │  (CORS → Observability → RequestContext → Auth)      │   │
                         │  └─────────────────────────────────────────────────────┘   │
  ┌──────────────┐       │                          │                                  │
  │Admin Frontend│──────>│  ┌───────────┬───────────┼───────────┬──────────────┐      │
  └──────────────┘       │  │           │           │           │              │      │
                         │  │  user/    │  admin/   │  relay/   │  internal/   │      │
  ┌──────────────┐       │  │controllers│controllers│controllers│  controllers │      │
  │ API Clients  │──────>│  │           │           │           │              │      │
  │ (sk-xxx)     │       │  └─────┬─────┴─────┬─────┴─────┬─────┴──────┬───────┘      │
  └──────────────┘       │        │           │           │            │              │
                         │  ┌─────▼───────────▼───────────▼────────────▼───────┐      │
  ┌──────────────┐       │  │              Service Layer (stateless)            │      │
  │inference-svc │──────>│  │  user_auth | admin_auth | billing | api_key      │      │
  │  (GPU)       │       │  │  pool | routing_setting | model_catalog          │      │
  └──────────────┘       │  │  relay/call_lifecycle | relay/routing             │      │
                         │  │  relay/channel_selector | relay/upstream_caller   │      │
                         │  └─────────────────────────┬────────────────────────┘      │
                         │                            │                                │
                         │  ┌─────────────────────────▼────────────────────────┐      │
                         │  │           Repository Layer (data access)          │      │
                         │  │  UserRepo | AdminUserRepo | ApiKeyRepo            │      │
                         │  │  PoolRepo | RoutingSettingRepo | CallLogRepo      │      │
                         │  └─────────────────────────┬────────────────────────┘      │
                         │                            │                                │
                         │  ┌─────────────────────────▼────────────────────────┐      │
                         │  │           ORM Models (SQLAlchemy 2.x async)       │      │
                         │  └─────────────────────────┬────────────────────────┘      │
                         │                            │                                │
                         │  ┌─────────────────────────▼────────────────────────┐      │
                         │  │  Infrastructure: MySQL (eucal_ai) + Redis (3 DBs) │      │
                         │  └──────────────────────────────────────────────────┘      │
                         └─────────────────────────────────────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With | Auth Mode |
|-----------|---------------|-------------------|-----------|
| `controllers/user/` | User-facing API (auth, billing, keys, models) | Service layer only | User JWT (cookie/Bearer) |
| `controllers/admin/` | Admin panel API (CRUD, dashboard, audit) | Service layer only | Admin JWT (cookie/Bearer) |
| `controllers/relay/` | LLM proxy endpoints (chat, messages, responses) | `relay/call_lifecycle` orchestrator | API Key (Bearer sk-xxx) |
| `controllers/internal/` | Inter-service endpoints for inference-service | Service layer | HMAC signature |
| `services/` | Business logic (stateless, `@staticmethod`) | Repositories, other services | N/A (in-process) |
| `services/relay/` | Relay orchestration (lifecycle, routing, upstream) | inference_client (HTTP), services, Redis | N/A (in-process) |
| `repositories/` | Data access (BaseRepository pattern) | ORM models, DB session | N/A (in-process) |
| `models/` | SQLAlchemy ORM definitions | Database | N/A |
| `common/` | Shared infrastructure (DB runtime, Redis, HMAC, observability) | External systems | N/A |
| `core/` | App bootstrap (config, DI, router mounting, lifespan) | All components | N/A |

### Boundary Rules

1. **Controllers never import other controllers.** Each controller domain is isolated.
2. **Controllers call services, never repositories directly** (except admin controllers doing simple read-only queries via repository for performance).
3. **Services may call other services** (e.g., `call_lifecycle` calls `billing_service`).
4. **Services call repositories** for data access.
5. **Repositories never call services** (no upward dependency).
6. **The relay domain** (`services/relay/`) is the only component that makes outbound HTTP calls (to inference-service and upstream LLM providers).
7. **No gateway layer exists** in the consolidated service. All former HTTP gateways become direct service/repository calls.

---

## Data Flow

### Flow 1: LLM Relay Request (Critical Path)

```
Client (Authorization: Bearer sk-xxx)
    │
    ▼
[FastAPI Middleware: observability, request_id injection]
    │
    ▼
[controllers/relay/chat.py]
    │ Depends(require_api_key) ──────────────────────────────────────┐
    │                                                                 │
    │   ┌─────────────────────────────────────────────────────────┐  │
    │   │ require_api_key dependency:                              │  │
    │   │  1. Extract Bearer token from header                    │  │
    │   │  2. SHA-256 hash the raw key                            │  │
    │   │  3. Check TTLCache (in-memory, 60s TTL, 2048 entries)   │  │
    │   │  4. Cache miss → ApiKeyService.validate_by_hash(db)     │  │
    │   │  5. Load User.balance from same DB session              │  │
    │   │  6. Return ValidatedPrincipal (user_id, balance, etc.)  │  │
    │   └─────────────────────────────────────────────────────────┘  │
    │                                                                 │
    ▼ <──────────────────────────────────────────────────────────────┘
[services/relay/call_lifecycle.py] ── orchestrates 8 phases:
    │
    ├── Phase 1: Balance check (principal.balance, no I/O)
    │
    ├── Phase 2: Rate limit check (Redis sliding window)
    │
    ├── Phase 3: Route decision
    │     ├── RoutingConfigCache.load() → Redis 60s TTL → DB fallback
    │     ├── InferenceClient.classify() → HTTP POST to GPU server
    │     │     (circuit breaker: 3 failures → 30s open → fallback tier-3)
    │     └── ChannelSelector.select() → weighted round-robin (in-memory)
    │
    ├── Phase 4: Upstream LLM call
    │     ├── SdkClientPool.get_client() → LRU cache of OpenAI/Anthropic clients
    │     ├── upstream_call_with_retry() → max 2 retries with channel failover
    │     └── ProtocolAdapter transforms request/response per protocol
    │
    ├── Phase 5: Response streaming (SSE) or JSON assembly
    │
    └── Phase 6: Finalization (fire-and-forget via asyncio.create_task)
          ├── Write ApiCallLog to DB
          ├── BillingService.consume_for_call_log() (SELECT FOR UPDATE + debit)
          └── UsageStatService.upsert_from_log() (hourly aggregation)
```

### Flow 2: Admin Operation (e.g., User Management)

```
Admin Frontend (cookie: admin_access_token=<JWT>)
    │
    ▼
[FastAPI Middleware: observability, RequestContext(ip, ua)]
    │
    ▼
[controllers/admin/user_management.py]
    │ Depends(require_active_admin) ─── validates JWT, checks status
    │ Depends(get_db) ─── yields AsyncSession
    │
    ▼
[UserRepository(db).get_list(...)]  ← direct DB query, no HTTP proxy
    │
    ▼
[AuditService.record_auto(db, ...)]  ← audit log with auto ip/ua from context
    │
    ▼
Response to admin frontend
```

### Flow 3: Routing Config Cache Lifecycle

```
Admin modifies routing config via admin/routing_settings.py
    │
    ├── RoutingSettingService.update(db, ...) → DB write
    │
    └── RoutingConfigCache.invalidate() → redis.delete("routing_config:full")
                                           (next relay request triggers reload)

Relay request needs config:
    │
    ▼
RoutingConfigCache.load()
    ├── Redis GET "routing_config:full" → HIT → return cached dict
    │
    └── MISS → _fetch_from_db():
          ├── RoutingSettingService.resolve_for_internal(db)
          ├── PoolService.resolve_model_channels(db, tier_models)
          ├── ModelCatalogService.get_prices_by_slugs(db, tier_models)
          └── Redis SETEX (60s TTL) → return assembled config
```

---

## Authentication Architecture

### Multi-Auth in a Single FastAPI App

The key insight: each auth mode maps to a distinct FastAPI `Depends()` function, and routes declare which dependency they need. There is no global auth middleware that tries to handle all modes.

```python
# core/dependencies.py — four independent auth paths

async def get_current_user(request, db) -> User:
    """User JWT from cookie 'user_access_token' or Authorization Bearer."""

async def get_current_admin(request, db) -> AdminUser:
    """Admin JWT from cookie 'admin_access_token' or Authorization Bearer.
    Also checks token blacklist (for admin logout)."""

async def require_api_key(request, db) -> ValidatedPrincipal:
    """API Key from Authorization: Bearer sk-xxx.
    Uses TTLCache for hot-path performance."""

def build_internal_auth_dependency(secret, allowed_callers) -> Callable:
    """HMAC signature verification for internal endpoints.
    Validates X-Internal-Service + X-Internal-Signature + X-Internal-Timestamp."""
```

### Auth Routing Strategy

| URL Prefix | Auth Dependency | Token Source |
|------------|----------------|--------------|
| `/api/v1/auth/*`, `/api/v1/billing/*`, `/api/v1/keys/*` | `require_active_user` | Cookie `user_access_token` or Bearer JWT |
| `/api/v1/admin/*` | `require_active_admin` or `require_super_admin` | Cookie `admin_access_token` or Bearer JWT |
| `/v1/chat/completions`, `/v1/anthropic/*`, `/v1/responses` | `require_api_key` | Bearer `sk-xxx` |
| `/api/v1/internal/*` | `verify_internal_secret` | HMAC headers |
| `/health`, `/ready`, `/v1/models` (public) | None | — |

### No Conflict Between Auth Modes

- User JWT and Admin JWT use different cookie names and different `type` claims in the JWT payload.
- API Key tokens always start with `sk-` prefix, making them trivially distinguishable from JWTs.
- HMAC internal auth uses custom headers (`X-Internal-*`), completely orthogonal to Bearer/cookie auth.
- Each route explicitly declares its auth dependency — no ambiguity.

---

## Patterns to Follow

### Pattern 1: Dependency Injection via FastAPI Depends

All cross-cutting concerns (auth, DB session, current user) flow through `Depends()`. This keeps controllers thin and testable.

```python
@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    users, total = await repo.get_list(ListParams(page=page, page_size=20))
    return PaginatedResponse(items=users, total=total)
```

### Pattern 2: Relay Component Injection via app.state

Relay components (inference_client, channel_selector, routing_config_cache, sdk_client_pool, rate_limiter) are initialized in lifespan and stored on `app.state`. Controllers access them via `request.app.state`.

```python
# In lifespan:
app.state.routing_config_cache = RoutingConfigCache(cache_ttl=60)
app.state.inference_client = InferenceClient(...)

# In controller:
@router.post("/v1/chat/completions")
async def chat_completions(request: Request, principal=Depends(require_api_key)):
    lifecycle = CallLifecycle(
        principal=principal,
        routing_config_cache=request.app.state.routing_config_cache,
        inference_client=request.app.state.inference_client,
        ...
    )
    return await lifecycle.execute(adapter, request)
```

### Pattern 3: Fire-and-Forget Finalization

Post-response work (call log, billing, stats) runs as background tasks that do not block the HTTP response. Uses `asyncio.create_task()` with its own DB session from `get_db_context()`.

```python
async def _finalize_call(log_data: dict, cost: int, user_id: int) -> None:
    try:
        async with get_db_context() as db:
            db.add(ApiCallLog(**log_data))
            await BillingService.consume_for_call_log(db, user_id, cost, ...)
            await db.commit()
    except Exception:
        logger.warning("finalize_failed", request_id=log_data.get("request_id"))

# In call_lifecycle after response is ready:
asyncio.create_task(_finalize_call(log_data, cost, principal.user_id))
```

### Pattern 4: Cache Invalidation on Write

Admin write operations that affect relay behavior (routing config, pool changes, model catalog) must call `routing_config_cache.invalidate()` after committing. This is a simple Redis DELETE — the next relay request triggers a fresh DB load.

```python
# In admin/routing_settings.py controller:
@router.put("/{setting_id}")
async def update_routing_setting(...):
    await RoutingSettingService.update(db, setting_id, payload)
    await db.commit()
    await request.app.state.routing_config_cache.invalidate()
    return {"ok": True}
```

### Pattern 5: Single Database Engine, Multiple Session Scopes

One `AsyncEngine` with connection pooling serves all domains. Two session acquisition patterns:

- **Request-scoped** (`get_db()` via Depends): auto-rollback on exception, controller/service owns commit.
- **Task-scoped** (`get_db_context()`): for background tasks and ARQ workers, same semantics.

```python
# Connection pool sizing for 4 uvicorn workers:
# pool_size=10, max_overflow=20 → max 30 connections per worker → 120 total
# MySQL default max_connections=151, so this fits with headroom.
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Shared Mutable State Between Workers

**What:** Storing relay state (channel health, config cache) in Python module-level globals that don't sync across uvicorn workers.

**Why bad:** With `--workers 4`, each worker has its own process. Module-level `dict` or `TTLCache` is per-worker. Channel cooldown in worker 1 doesn't affect worker 2.

**Instead:** Use Redis for state that must be shared (rate limiting, channel health). Accept per-worker isolation for state that's acceptable to diverge (API key TTLCache, routing config cache — each worker loads independently, slight staleness is fine).

### Anti-Pattern 2: Blocking the Event Loop in Relay Path

**What:** Calling synchronous operations (bcrypt, file I/O, CPU-heavy JSON parsing) in the relay hot path.

**Why bad:** Relay requests are latency-sensitive. A 50ms bcrypt call blocks the entire event loop for that worker.

**Instead:** API key validation uses SHA-256 (fast, non-blocking). Bcrypt is only used in user/admin auth flows where latency tolerance is higher, and even there it's wrapped in `asyncio.to_thread()`.

### Anti-Pattern 3: Circular Service Dependencies

**What:** ServiceA imports ServiceB which imports ServiceA.

**Why bad:** Python circular imports cause `ImportError` or `None` references.

**Instead:** The service layer has a clear dependency DAG:
- `call_lifecycle` → `billing_service`, `api_key_service`, `routing_config_cache`
- `billing_service` → `balance_tx_repository`, `user_repository`
- No service depends on `call_lifecycle`

### Anti-Pattern 4: Fat Controllers

**What:** Putting business logic, validation, and data transformation in controller functions.

**Why bad:** Untestable without HTTP, duplicated across admin/user when they share logic.

**Instead:** Controllers are thin — extract params, call service, return response. All logic lives in services.

---

## Connection Pooling and Session Management

### Database (SQLAlchemy AsyncEngine + aiomysql)

```
┌─────────────────────────────────────────────────────────┐
│ uvicorn (4 workers, each is a separate process)         │
│                                                         │
│  Worker 1: AsyncEngine(pool_size=10, max_overflow=20)   │
│  Worker 2: AsyncEngine(pool_size=10, max_overflow=20)   │
│  Worker 3: AsyncEngine(pool_size=10, max_overflow=20)   │
│  Worker 4: AsyncEngine(pool_size=10, max_overflow=20)   │
│                                                         │
│  Total max DB connections: 4 × 30 = 120                 │
│  MySQL max_connections: 151 (default) — fits            │
└─────────────────────────────────────────────────────────┘
```

Configuration:
- `pool_size=10`: baseline connections per worker
- `max_overflow=20`: burst capacity per worker
- `pool_pre_ping=True`: detect stale connections before use
- `pool_recycle=1800`: recycle connections every 30 min (MySQL wait_timeout safe)
- `pool_timeout=10`: fail fast if pool exhausted

### Redis (3 logical databases)

| Redis DB | Purpose | Access Pattern |
|----------|---------|----------------|
| db/0 | Primary: sessions, token blacklist, rate limiting | High-frequency reads/writes |
| db/1 | ARQ worker queue | Background job dispatch |
| db/2 | Cache: routing config, API key validation results | Read-heavy, TTL-based |

Each worker maintains its own `redis.asyncio` connection pool (default 10 connections per pool). Total: 4 workers × 3 pools × 10 = 120 Redis connections max.

### HTTP Client Pool (for inference-service only)

```python
InternalHttpPool:
    max_connections=100
    max_keepalive_connections=20
    default_timeout=10.0
```

This is the only outbound HTTP pool in the consolidated service. It handles:
- `POST /internal/v1/classify` (inference classification requests)
- `GET /internal/logs` (log aggregation from inference-service)

### SDK Client Pool (for upstream LLM providers)

```python
SdkClientPool:
    max_size=64  # LRU cache of OpenAI/Anthropic client instances
```

Each unique (base_url, api_key) combination gets a cached client. Clients are reused across requests to the same provider channel.

---

## Suggested Build Order

The build order follows dependency chains — each phase produces a testable artifact.

```
Phase 1: Scaffold + Common Layer + DB
    │     (empty app that boots, /health passes)
    │     No business logic, just infrastructure.
    │
    ▼
Phase 2: Admin + User Services (no relay)
    │     (all admin/user endpoints work)
    │     Validates: auth, billing, CRUD, audit
    │     Eliminates: all admin↔user HTTP gateways
    │
    ▼
Phase 3: Relay Integration
    │     (LLM proxy endpoints work end-to-end)
    │     Validates: full relay lifecycle
    │     Eliminates: router→user HTTP calls, CallLogBuffer, ConfigManager polling
    │     Depends on: Phase 2 (billing_service, api_key_service must exist)
    │
    ▼
Phase 4: Update inference-service
    │     (point inference at new api-service)
    │     Minimal change: env var update only
    │     Depends on: Phase 2 (internal/routing_config endpoint must exist)
    │
    ▼
Phase 5: Deploy + Validate
          (production cutover)
          Depends on: Phase 3 + 4 complete
```

### Why This Order

1. **Phase 1 first** because everything depends on the DB engine, Redis connections, and common utilities.
2. **Phase 2 before Phase 3** because relay depends on `billing_service` and `api_key_service` which are user-service logic. Also, the `controllers/internal/routing_config.py` endpoint (needed by inference-service in Phase 4) depends on `routing_setting_service` and `pool_service` from admin-service.
3. **Phase 3 after Phase 2** because `call_lifecycle` calls `BillingService.consume_for_call_log()` and `ApiKeyService.validate_by_hash()` — these must already be migrated.
4. **Phase 4 can start after Phase 2** (not Phase 3) because inference-service only needs the internal routing config endpoint, which is an admin-domain service.
5. **Phase 5 last** because it requires all functionality to be working.

### Critical Path

```
Phase 1 (2-3d) → Phase 2 (3-4d) → Phase 3 (3-4d) → Phase 5 (2-3d)
                                  ↗
                    Phase 4 (0.5d)
```

Phase 4 can run in parallel with Phase 3 once Phase 2 is complete.

---

## Scalability Considerations

| Concern | Current (100 users) | At 1K users | At 10K users |
|---------|--------------------:|------------:|-------------:|
| DB connections | 120 max (4 workers × 30) | Same config works | Consider PgBouncer-style proxy or reduce pool_size |
| Relay throughput | ~50 req/s per worker | ~200 req/s total | Add workers (8) or horizontal scale |
| API Key cache | 2048 entries, 60s TTL | Sufficient | Increase to 8192 or use Redis-backed cache |
| Routing config | 1 Redis key, 60s TTL | No change needed | No change needed |
| Memory per worker | ~350MB | ~400MB | ~500MB (larger caches) |
| Background tasks | asyncio.create_task | Works fine | Consider dedicated ARQ worker for call_log writes |

### Horizontal Scaling Path (future)

If the single 2h4g server becomes insufficient:
1. Add more uvicorn workers (up to CPU core count × 2)
2. Move to a larger server (4h8g)
3. Split relay to a separate process on same machine (share DB)
4. Only if truly needed: split back to separate services (unlikely at <10K users)

---

## Sources

- Existing codebase: `services/router-service/`, `services/admin-service/`, `services/user-service/`
- Project docs: `docs/architecture-refactoring.md`, `docs/architecture-refactoring-detail.md`
- FastAPI dependency injection patterns (official documentation)
- SQLAlchemy 2.x async session management patterns
- new-api (songquanpeng/new-api) layered monolith structure (Go reference, adapted to Python/FastAPI)
