# Domain Pitfalls: Microservice Consolidation (4 -> 2 Services)

**Domain:** FastAPI microservice-to-modular-monolith consolidation
**Project:** EucalAI Backend (admin + user + router -> api-service)
**Researched:** 2026-05-18
**Confidence:** HIGH (based on direct codebase analysis)

---

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or extended downtime.

---

### Pitfall 1: SQLAlchemy Session Scope Leakage in Fire-and-Forget Tasks

**What goes wrong:** The current `CallLogBuffer` uses HTTP to write logs asynchronously. The refactored design replaces this with `asyncio.create_task(_write_call_log(...))`. If the fire-and-forget task reuses the request-scoped `AsyncSession` (from `Depends(get_db)`), the session may already be closed or rolled back by the time the task executes. Worse, concurrent access to the same session from the request handler and the background task causes `InvalidRequestError` or silent data corruption.

**Why it happens:** In FastAPI, `Depends(get_db)` yields a session tied to the request lifecycle. When the response is sent, the session closes. A background task spawned during the request outlives this scope.

**Consequences:**
- `sqlalchemy.exc.InvalidRequestError: This session is in 'inactive' state`
- Silent loss of call logs (the task fails but the response already returned)
- Intermittent failures under load (race between session close and task execution)

**Prevention:**
- Background tasks MUST create their own session via `get_db_context()` (the async context manager pattern already exists in `common/db/runtime.py`)
- Never pass a request-scoped `db` session into `asyncio.create_task()`
- The architecture doc's `_write_call_log` example correctly uses `get_db_context()` — enforce this pattern in code review

**Detection:**
- `InvalidRequestError` in logs after relay requests
- Call logs missing for successful requests
- Errors appearing only under concurrent load

**Phase:** Phase 3 (Relay integration) — when replacing `CallLogBuffer` with direct DB writes

---

### Pitfall 2: Database Connection Pool Exhaustion After Merge

**What goes wrong:** Currently, admin-service and user-service each have their own connection pool (default `pool_size=10, max_overflow=20`). After merging into a single process with 4 uvicorn workers, the combined service needs to handle all admin, user, AND relay traffic through one pool. Relay traffic is bursty and high-frequency. With 4 workers x (10 + 20) = 120 potential connections, plus fire-and-forget tasks creating additional sessions, the MySQL `max_connections` (default 151) can be exhausted.

**Why it happens:** Each uvicorn worker forks its own SQLAlchemy engine with its own pool. The relay path now adds DB queries (API key validation, billing, call log writes) that previously went through HTTP. The total DB load multiplies.

**Consequences:**
- `TimeoutError: QueuePool limit of size 10 overflow 20 reached`
- All requests block waiting for connections
- Cascading failure: relay requests timeout, upstream LLM responses are wasted

**Prevention:**
- Calculate pool budget: 4 workers x pool_size must stay under MySQL `max_connections` minus headroom for ARQ worker and admin tools
- Recommended: `pool_size=5, max_overflow=10` per worker (4 workers = 60 max connections + ARQ worker = ~70 total)
- Set MySQL `max_connections=150` explicitly
- Add connection pool monitoring (log pool checkout time > 1s as warning)
- The API key TTL cache (2048 entries, 60s TTL) is critical — it prevents a DB query per relay request

**Detection:**
- `QueuePool limit reached` in SQLAlchemy logs
- Increasing p99 latency on all endpoints simultaneously
- MySQL `SHOW PROCESSLIST` showing many sleeping connections

**Phase:** Phase 1 (Scaffold) — pool sizing must be decided before any traffic hits the merged service

---

### Pitfall 3: Snowflake ID Collision After Worker ID Unification

**What goes wrong:** Currently admin-service uses `SNOWFLAKE_WORKER_ID=2` and user-service uses `SNOWFLAKE_WORKER_ID=1`. After merging, if the combined service uses a single worker_id, and multiple uvicorn workers generate IDs concurrently, collisions occur because the Snowflake algorithm assumes one generator per worker_id.

**Why it happens:** The `SnowflakeGenerator` uses `instance = datacenter_id * 32 + worker_id` to produce unique IDs. With 4 uvicorn workers (separate processes), each process creates its own generator with the same instance ID. The Snowflake algorithm's millisecond-sequence counter resets per process, so two processes generating IDs in the same millisecond produce identical IDs.

**Consequences:**
- `IntegrityError: Duplicate entry` on INSERT
- Silent data overwrites if using `INSERT ... ON DUPLICATE KEY UPDATE`
- Intermittent failures that are nearly impossible to reproduce in dev (requires concurrent requests)

**Prevention:**
- Assign unique worker_id per uvicorn worker process. Use `os.getpid() % 32` or pass worker index via environment variable
- Alternative: use `multiprocessing.current_process()._identity` to derive unique instance
- Alternative: switch to UUIDv7 for new tables (time-ordered, no coordination needed) — but this requires schema changes, so defer to post-consolidation
- For the merge: keep worker_id=1 for user-domain tables, worker_id=2 for admin-domain tables, and assign worker_id=3 for relay-domain tables (call logs). Route ID generation through domain-specific generators.

**Detection:**
- `IntegrityError` on primary key columns
- Only manifests under concurrent load with multiple workers
- Test with `--workers 4` and concurrent request scripts

**Phase:** Phase 1 (Scaffold) — must be solved in `main.py` lifespan before any model writes

---

### Pitfall 4: Database Migration Data Loss During Merge

**What goes wrong:** The plan calls for `mysqldump` from `eucal_ai_admin` and `eucal_ai_user` into a new `eucal_ai` database. If the dump is taken while services are still writing, or if the import order causes foreign key violations, data is lost or the import fails partway through.

**Why it happens:**
- `mysqldump --single-transaction` provides a consistent snapshot for InnoDB, but if the dump takes minutes and the service keeps writing, the new DB will be behind
- If tables have cross-database references (they don't currently, but future migrations might add them), import order matters
- Alembic `stamp head` on the merged DB assumes all migrations from both services are compatible — but the two services have independent migration histories

**Consequences:**
- Missing transactions/call logs created between dump and cutover
- Alembic confusion: merged DB has no migration history, future migrations may try to recreate existing tables
- If rollback is needed, data written to `eucal_ai` after cutover must be manually synced back

**Prevention:**
- Use a maintenance window: stop all services, dump, import, verify row counts, start new service
- If zero-downtime is required: set up MySQL replication from old DBs to new DB, then cut over
- Create a fresh Alembic migration that represents the "merged baseline" state — use `alembic stamp` with a custom revision that documents the merge
- Verify row counts: `SELECT COUNT(*) FROM each_table` in both source and target
- Keep old databases read-only (not dropped) for at least 7 days post-cutover

**Detection:**
- Row count mismatch between source and target
- Alembic `current` showing unexpected state
- Users reporting missing data after cutover

**Phase:** Phase 1 (DB merge script) and Phase 5 (production deployment)

---

### Pitfall 5: Billing Race Condition When Relay Moves In-Process

**What goes wrong:** Currently, billing (balance deduction) happens via HTTP from router-service to user-service. The HTTP call is serialized — one request at a time per user. After merging, multiple concurrent relay requests for the same user can hit `BalanceService.consume_for_call_log()` simultaneously. The existing `SELECT ... FOR UPDATE` pattern works, but the lock contention increases dramatically because relay requests are now in the same process and share the same DB pool.

**Why it happens:** The current architecture naturally serializes billing per user because HTTP round-trips add ~20ms between requests. In-process, requests arrive at the DB within microseconds of each other. The `FOR UPDATE` row lock on the `users` table becomes a bottleneck for high-frequency users.

**Consequences:**
- Lock wait timeouts for users making rapid API calls
- Increased p99 latency on relay requests (waiting for row lock)
- Potential deadlocks if billing and call-log writes acquire locks in different orders

**Prevention:**
- The existing idempotency check (`exists_by_ref` with `request_id`) prevents double-charging — this is correct
- Consider batching billing updates: accumulate costs in Redis and flush to DB periodically (similar to the old CallLogBuffer pattern but for billing)
- Set `innodb_lock_wait_timeout` to a reasonable value (5s, not default 50s) to fail fast
- Monitor lock wait time: `SHOW ENGINE INNODB STATUS` for lock contention
- For MVP: the current pattern is acceptable at current scale (the architecture doc mentions low traffic). Flag for optimization if p99 > 100ms on billing

**Detection:**
- `Lock wait timeout exceeded` errors in MySQL
- Relay p99 latency spikes correlated with specific users
- Deadlock detection in MySQL error log

**Phase:** Phase 3 (Relay integration) — when `call_lifecycle.py` starts calling `BillingService` directly

---

## Moderate Pitfalls

---

### Pitfall 6: Import Path Chaos During Migration

**What goes wrong:** All three services use relative imports like `from common.utils.jwt import ...`, `from models import User`, `from services.auth_service import ...`. After merging, these paths collide. Both admin and user have `services/auth_service.py`, `core/config.py`, `core/dependencies.py`, etc.

**Prevention:**
- Rename before copying: `auth_service.py` -> `user_auth_service.py` / `admin_auth_service.py` (the architecture doc already plans this)
- Use a migration checklist: for each file copied, grep all `from X import Y` and update
- Run `ruff check` after each file migration to catch import errors immediately
- Do NOT attempt to merge incrementally while keeping old services running — the import namespaces will conflict if both exist in the same Python path

**Phase:** Phase 2 (admin + user merge) — the bulk of import refactoring happens here

---

### Pitfall 7: CORS Origin Merge Breaks One Frontend

**What goes wrong:** admin-service and user-service have different `ALLOWED_HOSTS` lists. After merging, if the CORS config only includes one set of origins, the other frontend gets blocked. Additionally, the router-service (which becomes relay endpoints) may not have had CORS at all (API Key auth, not browser-based), but if admin-frontend makes requests to relay endpoints for testing, CORS must cover it.

**Prevention:**
- Merge all origins from both services into a single `ALLOWED_HOSTS` list
- Verify: admin-frontend origin + user-frontend origin + localhost variants for dev
- Test CORS preflight (`OPTIONS`) for both frontends against the merged service before cutover
- The relay endpoints (`/v1/chat/completions` etc.) should NOT have restrictive CORS — they're called by server-side code with API keys, not browsers

**Phase:** Phase 2 (when setting up `main.py` middleware) and Phase 5 (deployment verification)

---

### Pitfall 8: Redis Key Namespace Collision

**What goes wrong:** The three services use different Redis databases (user: db/0 + db/2, admin: db/3, router: separate URL). After merging into one service, if all Redis usage converges to the same db, key names may collide. For example, both admin and user might use keys like `rate_limit:{ip}` or `session:{id}`.

**Prevention:**
- Keep the existing Redis DB separation: db/0 for main operations, db/1 for ARQ worker queue, db/2 for cache
- Audit all Redis key patterns across services before merging:
  - user-service: `user_session:*`, `email_code:*`, `api_key_cache:*`
  - admin-service: `token_blacklist:*`, `health_check:*`
  - router-service: `rate_limit:*`, `affinity:*`, `channel_health:*`
- Add service-domain prefix if any collision is found
- The architecture doc's `RoutingConfigCache` uses `routing_config:full` — verify no existing key uses this pattern

**Phase:** Phase 1 (when unifying Redis connections) and Phase 3 (when adding relay Redis usage)

---

### Pitfall 9: Lifespan Initialization Order Dependencies

**What goes wrong:** The merged service has a complex startup sequence: Snowflake init -> DB engine -> session factory -> Redis connections -> schema validation -> bootstrap superadmin -> routing config cache -> SDK client pool -> rate limiter -> channel selector -> affinity store. If any step fails or is ordered wrong, the service starts in a broken state.

**Prevention:**
- Document the initialization DAG explicitly in `main.py`
- Fail fast: if any critical resource (DB, Redis) is unavailable at startup, raise immediately — don't start accepting traffic
- The router-service currently degrades gracefully when Redis is unavailable (falls back to in-memory). Preserve this behavior for rate limiting and affinity, but NOT for the routing config cache (which needs Redis or DB)
- Add a `/ready` endpoint that checks all critical dependencies before the load balancer sends traffic
- Test startup with each dependency unavailable to verify error messages are clear

**Phase:** Phase 1 (scaffold `main.py`) — the lifespan function is the first thing written

---

### Pitfall 10: TTL Cache Stale Data in `require_api_key`

**What goes wrong:** The architecture doc proposes a `TTLCache(maxsize=2048, ttl=60)` for API key validation. If an admin disables a user or revokes an API key, the cache serves stale data for up to 60 seconds. During this window, a revoked key can still make API calls.

**Why it happens:** The old HTTP-based validation had no caching (every request hit user-service). The new in-process cache trades consistency for performance.

**Prevention:**
- Accept the 60s window as a tradeoff (document it for admins)
- Add a cache invalidation hook: when admin disables a key or user, delete the specific cache entry
- Since admin and relay are now in the same process, this is trivial: `_api_key_cache.pop(key_hash, None)` in the admin controller
- Consider reducing TTL to 30s for the initial release, then tune based on hit rate
- Add a "force revoke" admin action that also adds the key hash to a Redis blacklist (checked before cache)

**Detection:**
- Admin reports that disabled keys still work for ~1 minute
- Security audit flags the gap

**Phase:** Phase 3 (when implementing `require_api_key` with cache)

---

### Pitfall 11: `asyncio.create_task` Swallowing Exceptions Silently

**What goes wrong:** The refactored call log writes use `asyncio.create_task(_write_call_log(...))`. If the task raises an exception, it's only logged when the task is garbage collected (Python emits "Task exception was never retrieved"). In practice, these warnings are easy to miss, and call logs silently fail.

**Why it happens:** Fire-and-forget tasks have no caller awaiting them. The current `CallLogBuffer` has explicit retry logic (up to 3 retries). The new pattern loses this resilience.

**Prevention:**
- Wrap all fire-and-forget tasks in a try/except that logs failures explicitly (the architecture doc's example does this correctly)
- Add a metric/counter for failed call log writes
- Consider a lightweight in-process queue (`asyncio.Queue` + consumer task) instead of raw `create_task` — this preserves ordering and allows batch writes if needed later
- Add a periodic health check that compares "relay requests served" vs "call logs written" — alert if divergence > 1%

**Detection:**
- "Task exception was never retrieved" warnings in stderr
- Call log count diverging from request count
- Missing call logs for specific time windows

**Phase:** Phase 3 (relay integration)

---

### Pitfall 12: Alembic Migration History Conflict

**What goes wrong:** admin-service and user-service each have their own `migrations/versions/` directory with independent revision chains. After merging into a single Alembic instance, the `alembic_version` table in the new `eucal_ai` database needs a single head. If both chains are imported, Alembic sees multiple heads and refuses to run.

**Prevention:**
- Do NOT import old migration files into the new service
- Create a single "baseline" migration that represents the merged schema as-is
- Use `alembic stamp <revision>` to mark the merged DB as being at this baseline
- All future migrations start from this single head
- Keep old migration directories in the archived service directories for reference only
- Document: "migrations before revision X were from the pre-merge era"

**Phase:** Phase 1 (Alembic setup in scaffold)

---

## Minor Pitfalls

---

### Pitfall 13: Uvicorn Worker Memory Pressure on 4GB Server

**What goes wrong:** The architecture doc budgets 4 workers x ~350MB = 1.4GB for api-service. After adding relay logic (SDK client pool with 64 max clients, routing config cache, rate limiter state), actual memory per worker may exceed 350MB. With MySQL (512MB) + Redis (128MB) + ARQ worker (400MB), the 4GB server has only ~560MB headroom.

**Prevention:**
- Start with 2 workers, measure actual RSS per worker under load
- Set `SDK_CLIENT_POOL_MAX_SIZE=32` (halve from 64) — each httpx client holds connection pools
- Use `--limit-max-requests 10000` in uvicorn to prevent memory leaks from accumulating
- Monitor with `docker stats` or `ps aux --sort=-rss`
- Have a fallback plan: reduce to 2 workers + increase pool_size per worker

**Phase:** Phase 5 (deployment tuning)

---

### Pitfall 14: Middleware Ordering After Merge

**What goes wrong:** Each service has its own middleware stack (CORS, observability/request-ID, request context). After merging, if middleware is added in the wrong order, request context isn't available when needed, or CORS headers are missing on error responses.

**Prevention:**
- FastAPI middleware executes in reverse order of `app.add_middleware()` calls
- Correct order (last added = first executed): CORS -> Observability (request ID) -> Request Context
- Test: make a request that triggers an exception handler — verify CORS headers are present on the error response
- Test: verify `X-Request-ID` header appears on all responses including 4xx/5xx

**Phase:** Phase 1 (scaffold `main.py`)

---

### Pitfall 15: Admin Token Blacklist Not Shared Across Workers

**What goes wrong:** The admin-service uses `token_blacklist.py` to track revoked admin JWTs. If this blacklist is stored in-memory (process-local), revoking a token in one uvicorn worker doesn't affect the other 3 workers.

**Prevention:**
- Verify the blacklist implementation uses Redis (not in-memory dict)
- If it uses Redis: no issue, all workers share the same Redis
- If it uses in-memory: migrate to Redis-backed blacklist before merge
- The existing `common/token_blacklist.py` likely uses Redis (given the Redis dependency) — verify during Phase 2

**Phase:** Phase 2 (when migrating admin auth)

---

## Phase-Specific Warnings

| Phase | Likely Pitfall | Mitigation |
|-------|---------------|------------|
| Phase 1: Scaffold + DB merge | Snowflake ID collision (#3), Pool exhaustion (#2), Alembic conflict (#12) | Assign per-worker IDs, size pools conservatively, create clean baseline migration |
| Phase 2: Admin + User merge | Import path chaos (#6), CORS breakage (#7), Token blacklist scope (#15) | Rename-before-copy strategy, merge ALLOWED_HOSTS, verify Redis-backed blacklist |
| Phase 3: Relay integration | Session scope leakage (#1), Billing race (#5), Stale cache (#10), Silent task failures (#11) | Own-session-per-task pattern, monitor lock contention, add cache invalidation hooks |
| Phase 4: Inference update | Minimal risk | Just URL change — verify HMAC secret matches |
| Phase 5: Deployment | Data loss during migration (#4), Memory pressure (#13), Middleware order (#14) | Maintenance window, start with 2 workers, test middleware stack |

---

## Pre-Merge Validation Checklist

Before cutting over to the merged service:

- [ ] Row counts match between source DBs and merged DB
- [ ] All 3 auth flows work (user JWT, admin JWT, API key)
- [ ] CORS preflight passes for both frontends
- [ ] Snowflake IDs are unique across 4 concurrent workers (load test)
- [ ] Call logs are written for every relay request (no silent drops)
- [ ] Admin can disable a user/key and it takes effect within 60s
- [ ] Memory per worker stays under 400MB under load
- [ ] DB connection pool doesn't exhaust under concurrent relay + admin traffic
- [ ] Rollback procedure tested: can revert to old services within 5 minutes

---

## Sources

- Direct codebase analysis of `services/admin-service/`, `services/user-service/`, `services/router-service/`
- Architecture refactoring document: `docs/architecture-refactoring.md`
- SQLAlchemy async session lifecycle: `common/db/runtime.py` pattern
- Snowflake ID configuration: `core/config.py` across services (worker_id=1 vs 2)
- Balance service locking: `services/balance_service.py` FOR UPDATE pattern
- CallLogBuffer implementation: `services/calllog_buffer.py` retry/buffer logic
