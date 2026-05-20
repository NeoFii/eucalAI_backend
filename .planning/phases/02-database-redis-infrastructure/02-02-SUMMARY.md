# Plan 02-02 Summary: Redis connection pools (3 logical DBs)

**Status:** Complete
**Executed:** 2026-05-19
**Commit:** feat(02-02): register Redis db/0 and Cache Redis db/2 lifespan resources

## What Was Done

1. **Redis db/0 lifespan resource** — Registered `_init_redis` / `_shutdown_redis` at priority=30, calling `init_redis(settings.REDIS_URL)` and `close_redis()` respectively.

2. **Cache Redis db/2 lifespan resource** — Registered `_init_cache_redis` / `_shutdown_cache_redis` at priority=30, calling `init_cache_redis(settings.CACHE_REDIS_URL)` and `close_cache_redis()` respectively.

3. **Upgraded /ready endpoint** — Now checks DB + Redis db/0 + Cache Redis db/2. Uses `_combined_redis_check` that sequentially pings both pools. Any failure returns 503 with descriptive error.

## Anti-Goals Respected

- No pool created for db/1 (ARQ worker manages its own)
- No modifications to `common/infra/redis.py` or `cache.py`
- No `max_connections` parameter set

## Verification

- Lifespan registry contains `redis` and `cache_redis` resources (priority=30, shutdown_fn set)
- Priority order: logging(0) → snowflake(10) → database(20) → redis(30) → cache_redis(30)
- `ruff check` passes clean

## Files Modified

- `services/api-service/api_service/main.py` — Added Redis/Cache Redis init/shutdown functions and upgraded /ready endpoint

## Next

Plan 02-03: Snowflake ID with per-worker safety
