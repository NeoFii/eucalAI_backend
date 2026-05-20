---
phase: 09-integration-testing
plan: 02
subsystem: relay-cache-propagation
tags: [integration-test, admin, relay, cache, redis]
dependency_graph:
  requires: [09-01]
  provides: [admin-relay-cache-propagation-tests]
  affects: [relay, admin-service]
tech_stack:
  added: []
  patterns: [session-factory-direct, explicit-cleanup, redis-version-poll]
key_files:
  created:
    - services/api-service/tests/integration/test_admin_relay_cache.py
  modified: []
decisions:
  - "Used session_factory directly instead of transaction-rollback db_session because check_and_reload opens its own session"
  - "Explicit DELETE cleanup in finally blocks for data isolation"
  - "Seeded RoutingSetting tier_model_map rows to satisfy normalize_runtime_config validation"
metrics:
  duration: 218s
  completed: 2026-05-19T15:51:08Z
  tasks: 1/1
  files_created: 1
  files_modified: 0
  test_count: 5
---

# Phase 09 Plan 02: Admin -> Relay Cache Propagation Tests Summary

Cross-domain integration tests proving admin config writes propagate through Redis version-based invalidation to RoutingConfigCache reload.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Admin -> relay cache propagation tests | 789dcf7 | tests/integration/test_admin_relay_cache.py |

## Test Coverage

| Test | Scenario | Verifies |
|------|----------|----------|
| test_add_model_route_propagates | D-15 #1 | New model+PMC -> version INCR -> check_and_reload -> model_channels updated |
| test_disable_channel_propagates | D-15 #2 | Pool.is_enabled=False -> version INCR -> check_and_reload -> channels removed |
| test_modify_price_propagates | D-15 #3 | ModelCatalog.sale_input_per_million change -> version INCR -> model_prices updated |
| test_version_unchanged_no_reload | T-09-05 | No DB reload when Redis version key unchanged (prevents reload storm) |
| test_redis_version_increment_on_admin_write | D-06 | _bump_version() correctly INCRs routing_config:version |

## Deviations from Plan

None - plan executed exactly as written.

## Implementation Notes

- Tests bypass the per-test transaction-rollback `db_session` fixture because `RoutingConfigCache.check_and_reload()` opens its own session via `session_factory`. Committed data must be visible to the reload session.
- Cleanup uses explicit DELETE statements in `finally` blocks, ordered by FK constraints.
- Each test creates its own `RoutingConfigCache` instance to avoid cross-test state leakage.
- `RoutingSetting` rows for `tier_1_model` through `tier_5_model` are seeded because `normalize_runtime_config` requires all 5 tiers to be non-empty.

## Self-Check: PASSED
