---
phase: "06"
plan: "01"
subsystem: relay-auth-billing
tags: [relay, auth, billing, redis, cache, api-key]
dependency_graph:
  requires: [phase-04-api-key-service, phase-05-routing-settings]
  provides: [require_api_key, RelayBillingService, ValidatedApiKey, invalidate_api_key_cache]
  affects: [relay/routing, relay/call_log_writer, core/config]
tech_stack:
  added: []
  patterns: [three-tier-cache, redis-decrby-atomic, trust-quota-bypass, fire-and-forget-fallback]
key_files:
  created:
    - services/api-service/api_service/relay/__init__.py
    - services/api-service/api_service/relay/auth.py
    - services/api-service/api_service/relay/billing.py
    - services/api-service/tests/test_relay_auth.py
    - services/api-service/tests/test_relay_billing.py
  modified:
    - services/api-service/api_service/core/config.py
decisions:
  - "D-04 TRUST_QUOTA=10_000_000 as env config in ApiServiceSettings"
  - "D-06 all Redis ops wrapped in try/except with fallback"
  - "Lazy init for Redis user:quota via DB query + SET with 300s TTL"
metrics:
  duration: "337s"
  completed: "2026-05-19T06:16:51Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 19
  files_created: 5
  files_modified: 1
---

# Phase 6 Plan 01: API Key Auth + Relay Billing Summary

JWT-free API Key 三级验证 (TTLCache -> Redis -> DB) + new-api 风格预扣费/结算/退款计费服务

## One-liner

API Key 本地三级鉴权 + Redis DECRBY 原子预扣费/结算/退款，消除所有 user-service HTTP 调用

## Tasks Completed

| # | Name | Commit | Key Files |
|---|------|--------|-----------|
| 1 | relay package + config + ValidatedApiKey + require_api_key | c69799d | relay/auth.py, core/config.py |
| 2 | RelayBillingService pre-consume / settle / refund | 2e7ec17 | relay/billing.py |

## Verification Results

```
19 passed in 0.51s
```

All 19 tests pass (7 auth + 12 billing). Covers:
- Cache hit / Redis hit / DB fallback / Redis down / missing header / invalid key / invalidation
- Balance Redis hit / DB fallback / estimate known / estimate unknown / trusted / normal / insufficient / settle trusted / settle underpaid / settle overpaid / refund / Redis down degradation

## Deviations from Plan

None - plan executed exactly as written.

## Decisions Made

1. **TRUST_QUOTA placement**: Added as `ApiServiceSettings.TRUST_QUOTA = 10_000_000` alongside other relay config (D-04)
2. **Redis balance lazy init TTL**: 300s for `user:quota:{user_id}` on first DB-to-Redis write-back (balances Open Question 2)
3. **estimate_cost minimum**: Returns `max(int(cost), 1)` to avoid zero pre-consume for very cheap models

## Key Implementation Details

- `require_api_key` is a FastAPI dependency that extracts Bearer/X-Api-Key, computes SHA256 hash, and checks three tiers
- `ValidatedApiKey` is a `@dataclass(slots=True)` with all fields needed for downstream relay logic
- `invalidate_api_key_cache(key_hash)` supports D-07 active invalidation when admin disables a key
- `RelayBillingService` uses all `@staticmethod` methods with explicit `cache_redis` parameter
- Redis DECRBY atomic operation prevents read-modify-write race conditions (T-06-02)
- Negative balance check after DECRBY with immediate INCRBY rollback

## Self-Check: PASSED
