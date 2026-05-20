# Codebase Concerns

**Analysis Date:** 2026-05-20

## Tech Debt

**Duplicated Common Layer Across Legacy Services (MEDIUM):**
- Issue: 5 copies of `internal.py` (405–589 lines each), 5 copies of `observability.py` (460 lines each), 8 copies of `exceptions.py` across services
- Files: `services/admin-service/src/common/internal.py`, `services/user-service/src/common/internal.py`, `services/router-service/src/common/internal.py`, `services/inference-service/src/common/internal.py`, `services/api-service/api_service/common/internal.py`
- Impact: Bug fixes must be applied to all copies; drift between copies causes inconsistent behavior. ~2,650 lines of duplicated internal HTTP client code alone.
- Fix approach: Legacy services (admin-service, user-service, router-service) should be decommissioned once api-service merge is complete. Until then, freeze legacy copies.

**RoutingConfigCache.check_and_reload Never Called in Production (HIGH):**
- Issue: The `check_and_reload` method exists and is tested but never invoked in any controller, middleware, or dependency
- Files: `services/api-service/api_service/relay/config_cache.py:66`, `services/api-service/api_service/controllers/relay/chat.py`
- Impact: Routing configuration loaded at startup is never refreshed. Admin changes to pools, models, or routing settings require a full service restart to take effect.
- Fix approach: Add a per-request middleware or FastAPI dependency that calls `check_and_reload(session_factory)` on the hot path (lightweight Redis GET per request).

**TODO Items Blocking Phase 5 Completion (MEDIUM):**
- Issue: 3 explicit TODO(phase-5) markers indicate deferred functionality
- Files: `services/api-service/api_service/core/config.py:90`, `services/api-service/api_service/services/auth_service.py:100`, `services/api-service/api_service/services/model_catalog_service.py:60`
- Impact: DEFAULT_USER_RPM is hardcoded; model catalog cache invalidation on admin writes is missing; system_settings table is not read dynamically.
- Fix approach: Implement admin-domain cache invalidation (INCR routing_config:version on write) and dynamic settings read.

**SDK Client Pool Eviction Without Close (HIGH):**
- Issue: When `SdkClientPool` evicts LRU clients via `popitem(last=False)`, the evicted `AsyncOpenAI`/`AsyncAnthropic` client is never closed
- Files: `services/api-service/api_service/relay/sdk_clients.py:30`, `services/api-service/api_service/relay/sdk_clients.py:42`
- Impact: Leaked HTTP connections accumulate over time. Under high cardinality of (base_url, api_key) pairs, this causes file descriptor exhaustion.
- Fix approach: Call `await client.close()` on evicted clients. Since eviction happens inside a sync `threading.Lock`, schedule close via `asyncio.get_event_loop().call_soon_threadsafe()` or restructure to use async lock.

## Known Bugs

**Balance Check Always Fails — principal.balance Never Populated (CRITICAL):**
- Symptoms: `_check_balance` in `CallLifecycle` checks `self.principal.balance <= 0`, but `ValidatedApiKey.balance` defaults to 0 and is never set during auth flow
- Files: `services/api-service/api_service/relay/lifecycle/orchestrator.py:96`, `services/api-service/api_service/relay/auth.py:44`
- Trigger: Every relay request hits `_check_balance` which returns 402 because balance is always 0
- Workaround: Either the balance check is dead code that never executes (bypassed by some other mechanism not found), or this is a blocking bug. The `RelayBillingService.get_balance()` exists but is never called before the check.

## Security Considerations

**PROVIDER_SECRET_MASTER_KEY Not Validated at Startup (HIGH):**
- Risk: If `PROVIDER_SECRET_MASTER_KEY` is empty (default), all pool account API keys fail to decrypt silently. The routing config loads with zero channels, causing all relay requests to fail with routing errors.
- Files: `services/api-service/api_service/core/config.py:38`, `services/api-service/api_service/relay/config_cache.py:178-198`
- Current mitigation: `RoutingConfigCache.start()` raises RuntimeError if no model_channels found, but only at startup.
- Recommendations: Add explicit startup validation that `PROVIDER_SECRET_MASTER_KEY` is a valid 64-char hex string when relay is enabled.

**Broad Exception Swallowing in Relay Hot Path (MEDIUM):**
- Risk: 65 instances of `except Exception:` in api-service, many without binding the exception. In the relay path, errors are silently swallowed (fail-open design), which is intentional for Redis but masks real bugs.
- Files: `services/api-service/api_service/relay/auth.py:141,177`, `services/api-service/api_service/relay/config_cache.py:57,73,190`, `services/api-service/api_service/relay/billing.py:51,68,126,159,182`
- Current mitigation: `logger.debug()` on some paths, but many have no logging at all.
- Recommendations: Add structured error logging with error type classification. At minimum, log exception class name even in fail-open paths.

**Decrypted API Keys Held in Memory (LOW):**
- Risk: `_build_model_channels()` decrypts all pool account API keys and stores them in a plain dict in `RoutingConfigCache._cached_config`. These remain in process memory indefinitely.
- Files: `services/api-service/api_service/relay/config_cache.py:187-205`
- Current mitigation: None. Keys are in plaintext in the worker process memory.
- Recommendations: Accept as necessary for performance (decrypting per-request would be too slow). Ensure process memory is not swapped to disk (`mlockall` or container memory limits).

## Performance Bottlenecks

**Fire-and-Forget Tasks Without Backpressure (MEDIUM):**
- Problem: `create_call_log` and `update_call_log_and_settle` use `asyncio.create_task()` without any queue depth limit
- Files: `services/api-service/api_service/relay/call_log_writer.py:27,52`
- Cause: Under burst traffic, unbounded task creation can exhaust memory. Each task holds a DB session reference.
- Improvement path: Add a bounded semaphore or use an internal asyncio.Queue with a fixed-size worker pool for DB writes.

**Threading Lock in Async Hot Path (MEDIUM):**
- Problem: `ChannelSelector` and `SdkClientPool` use `threading.Lock()` which blocks the event loop thread during contention
- Files: `services/api-service/api_service/relay/channel_selector.py:43`, `services/api-service/api_service/relay/sdk_clients.py:19`
- Cause: These were ported from a multi-threaded context. In uvicorn with multiple workers, each worker is single-threaded async, so the lock is rarely contended — but it's architecturally wrong.
- Improvement path: Replace with `asyncio.Lock()` for correctness, or remove locks entirely since each uvicorn worker runs a single event loop thread.

**Snowflake Worker ID Collision Risk (LOW):**
- Problem: `worker_id = os.getpid() % 32` can collide across workers if PIDs are close (e.g., PIDs 100 and 132 both map to worker_id=4)
- Files: `services/api-service/api_service/main.py:41`
- Cause: uvicorn spawns workers with sequential PIDs, so `pid % 32` is usually unique for 4 workers. But after restarts, PID reuse can cause collisions.
- Improvement path: Use uvicorn worker index (via environment variable or `--worker-id` flag) instead of PID modulo.

## Fragile Areas

**Relay Billing Lifecycle (Redis + DB Dual-Write):**
- Files: `services/api-service/api_service/relay/billing.py`, `services/api-service/api_service/relay/call_log_writer.py`, `services/api-service/api_service/relay/lifecycle/finalize.py`
- Why fragile: The billing flow spans Redis (pre-consume/settle) and DB (persist). If Redis succeeds but DB fails, the user's Redis balance is decremented but no ledger record exists. The `reconcile_balance_ledger` cron job detects drift but does not auto-fix.
- Safe modification: Always test billing changes with the full lifecycle (stream + non-stream). Verify that `finalize_stream` runs even on client disconnect (asyncio.shield is in place).
- Test coverage: `tests/test_relay_billing.py` and `tests/test_call_log_writer.py` exist but do not test Redis+DB failure combinations.

**Stream Finalization on Client Disconnect:**
- Files: `services/api-service/api_service/relay/lifecycle/stream.py:76-87`, `services/api-service/api_service/relay/lifecycle/finalize.py:103-109`
- Why fragile: When a client disconnects mid-stream, `asyncio.CancelledError` propagates. The `finally` block calls `finalize_stream` which uses `asyncio.shield` to protect billing writes. If the event loop is shutting down simultaneously, the shielded task may still be cancelled.
- Safe modification: Test with `httpx` client that disconnects mid-stream. Verify billing settle completes.
- Test coverage: `tests/relay/test_streaming.py` exists but client-disconnect scenarios need verification.

## Scaling Limits

**Single MySQL Instance (2h4g Server):**
- Current capacity: 4 workers × (5 pool_size + 10 max_overflow) = 60 max connections per worker = 240 total possible (exceeds MySQL default 151)
- Limit: MySQL `max_connections=151` default will reject connections under load
- Scaling path: Either reduce pool_size to 3 (4×(3+5)=32 per worker, 128 total) or increase MySQL max_connections. The config defaults (pool_size=5, max_overflow=10) are reasonable for normal load but the ARQ worker also opens its own pool.

**In-Process TTLCache for API Key Validation:**
- Current capacity: 2048 entries, 60s TTL
- Limit: With >2048 concurrent active API keys, cache thrashing causes every request to hit Redis/DB
- Scaling path: Increase `RELAY_TOKEN_CACHE_MAXSIZE` or add a second tier with longer TTL for validated-but-stale entries.

## Dependencies at Risk

**passlib + bcrypt Version Pinning (MEDIUM):**
- Risk: `bcrypt>=3.2.0,<4.0.0` is pinned because passlib has compatibility issues with bcrypt 4.x. passlib is in maintenance mode with no clear timeline for bcrypt 4.x support.
- Impact: Cannot upgrade to bcrypt 4.x (which has performance improvements and security fixes). Eventually passlib may become unmaintained.
- Migration plan: Monitor passlib releases. If abandoned, migrate to `argon2-cffi` or use bcrypt directly without passlib wrapper.

**python-jose Maintenance Status (LOW):**
- Risk: python-jose has infrequent updates. The `cryptography` backend is stable but the library itself may become unmaintained.
- Impact: No immediate risk, but long-term may need migration to PyJWT.
- Migration plan: Monitor. If security vulnerabilities are found, switch to PyJWT (API is similar).

## Missing Critical Features

**No External Monitoring/Metrics (HIGH):**
- Problem: No Prometheus, Datadog, Sentry, or any external observability integration. Only internal structured logging and an in-memory ring buffer.
- Blocks: Cannot detect production issues proactively. No alerting on error rate spikes, latency degradation, or resource exhaustion.

**No Graceful Degradation on DB Failure (MEDIUM):**
- Problem: If MySQL goes down, all requests fail immediately. The relay path has Redis fail-open for caching, but the call_log_writer and balance_service require DB.
- Blocks: Zero-downtime guarantee during DB maintenance windows.

## Test Coverage Gaps

**Relay End-to-End with Real Upstream (HIGH):**
- What's not tested: Full relay lifecycle with actual OpenAI/Anthropic SDK calls (mocked in all existing tests)
- Files: `services/api-service/tests/relay/`, `services/api-service/tests/integration/test_relay_e2e.py`
- Risk: Protocol conversion bugs, streaming chunk format issues, and SDK version incompatibilities go undetected
- Priority: High — this is the core revenue path

**Redis + DB Failure Combination in Billing (MEDIUM):**
- What's not tested: Scenarios where Redis succeeds but DB fails (or vice versa) during billing settle
- Files: `services/api-service/tests/test_relay_billing.py`, `services/api-service/tests/test_call_log_writer.py`
- Risk: Balance drift between Redis and DB goes undetected until daily reconciliation cron
- Priority: Medium — reconciliation cron exists as safety net

**Legacy Service Decommission Verification (MEDIUM):**
- What's not tested: No automated verification that api-service covers 100% of legacy service endpoints
- Files: Legacy services under `services/admin-service/`, `services/user-service/`, `services/router-service/`
- Risk: Missing endpoints discovered only after cutover
- Priority: Medium — manual UAT exists in phase 09

---

*Concerns audit: 2026-05-20*
