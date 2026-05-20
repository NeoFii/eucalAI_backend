---
phase: "06"
plan: "03"
subsystem: relay-routing-orchestration
tags: [relay, channel-selector, inference-client, call-log, routing, lifespan]
dependency_graph:
  requires: [06-01-relay-auth-billing, 06-02-routing-config-cache]
  provides: [ChannelSelector, ChannelAffinityStore, InferenceClient, route_and_resolve, create_call_log, update_call_log_and_settle, init_relay_globals]
  affects: [relay/routing, core/lifespan, Phase-7-protocol-adapters]
tech_stack:
  added: []
  patterns: [weighted-round-robin, circuit-breaker, fire-and-forget-create-task, singleton-registry]
key_files:
  created:
    - services/api-service/api_service/relay/channel_selector.py
    - services/api-service/api_service/relay/channel_affinity.py
    - services/api-service/api_service/relay/inference_client.py
    - services/api-service/api_service/relay/call_log_writer.py
    - services/api-service/api_service/relay/routing.py
    - services/api-service/api_service/relay/dependencies.py
    - services/api-service/tests/test_channel_selector.py
    - services/api-service/tests/test_inference_client.py
    - services/api-service/tests/test_call_log_writer.py
  modified:
    - services/api-service/api_service/core/lifespan.py
decisions:
  - "D-18: Full port of ChannelSelector + ChannelAffinityStore + route_and_resolve from router-service"
  - "D-19: InferenceClient retains HTTP call to inference-service with circuit breaker"
  - "D-20: Per-worker independent ChannelSelector state (threading.Lock kept as-is)"
  - "D-22: ChannelAffinityStore TTL=300s (CONTEXT.md override from source 3600)"
  - "D-23: _get_rate_limited_accounts returns empty frozenset — full rate limiter deferred to Phase 7"
  - "register_relay_resources bundles all relay singletons into single lifespan resource at priority=20"
metrics:
  duration: "581s"
  completed: "2026-05-19T11:34:27Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 17
  files_created: 9
  files_modified: 1
---

# Phase 06 Plan 03: Routing Orchestration + Channel Selection Summary

ChannelSelector weighted RR + InferenceClient circuit breaker + CallLog fire-and-forget + route_and_resolve 编排 + relay 单例管理 + lifespan 注册

## One-liner

完整移植 ChannelSelector/InferenceClient/ChannelAffinity，实现 route_and_resolve 编排和 CallLog 直写，relay 核心基础设施就绪

## Tasks Completed

| # | Name | Commit | Key Files |
|---|------|--------|-----------|
| 1 | ChannelSelector + ChannelAffinity + InferenceClient port | 195eedb | relay/channel_selector.py, relay/channel_affinity.py, relay/inference_client.py |
| 2 | CallLogWriter + routing.py + dependencies + lifespan wiring | cf8ed95 | relay/call_log_writer.py, relay/routing.py, relay/dependencies.py, core/lifespan.py |

## Implementation Details

### Task 1: ChannelSelector + ChannelAffinity + InferenceClient

Ported verbatim from router-service with minimal adjustments:

- **ChannelSelector** (155 lines): weighted round-robin with priority-tier descent, failure cooldown, auto-disable after 5 consecutive failures (300s cooldown), health cache exclusion, rate-limited account exclusion. threading.Lock kept as-is per Claude's Discretion.
- **ChannelAffinityStore** (54 lines): Redis + in-memory LRU cache. TTL changed from 3600 to 300 per D-22 (CONTEXT.md override).
- **InferenceClient** (182 lines): httpx.AsyncClient with retry on 5xx/connection errors, circuit breaker (threshold=3, cooldown=30s). X-Inference-Secret header never logged (T-06-10).

### Task 2: CallLogWriter + Routing + Dependencies + Lifespan

- **call_log_writer.py**: Fire-and-forget via asyncio.create_task (D-14). Independent sessions (D-15). Two-step: create pending record, then update+settle. Billing settle retries 3x (D-16). Update and settle in same task (D-17).
- **routing.py**: route_and_resolve() with explicit dependency parameters (no module-level singletons in function signature). Validates model against user_facing_aliases (T-06-13). Falls back to tier-3 model on inference failure. Affinity cache lookup/store integrated.
- **dependencies.py**: Module-level singleton getters (get_routing_config_cache, get_inference_client, get_channel_selector, get_affinity_store). init_relay_globals() sets all at once. shutdown_relay() closes InferenceClient.
- **lifespan.py**: Added register_relay_resources() that bundles all relay init into a single LifespanRegistry resource at priority=20. Initializes RoutingConfigCache (must succeed, D-12), InferenceClient, ChannelSelector, ChannelAffinityStore.

## Verification Results

```
44 passed in 1.75s
```

Full relay test suite (6 test files): test_relay_auth (7) + test_relay_billing (12) + test_config_cache (8) + test_channel_selector (7) + test_inference_client (5) + test_call_log_writer (5) = 44 tests.

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

1. **_get_rate_limited_accounts returns empty frozenset**: Phase 6 does not implement per-account RPM checking (D-23 says channel-level only). Full rate limiter deferred to Phase 7.
2. **register_relay_resources as single resource**: Instead of 4 separate lifespan registrations, bundled into one at priority=20 for simpler ordering and atomic init/shutdown.
3. **routing.py uses explicit parameters**: route_and_resolve accepts config_cache, inference_client, channel_selector, affinity_store as kwargs rather than calling module-level getters internally — enables easier testing and explicit dependency injection.

## Self-Check: PASSED

- [x] services/api-service/api_service/relay/channel_selector.py exists
- [x] services/api-service/api_service/relay/channel_affinity.py exists
- [x] services/api-service/api_service/relay/inference_client.py exists
- [x] services/api-service/api_service/relay/call_log_writer.py exists
- [x] services/api-service/api_service/relay/routing.py exists
- [x] services/api-service/api_service/relay/dependencies.py exists
- [x] services/api-service/tests/test_channel_selector.py exists
- [x] services/api-service/tests/test_inference_client.py exists
- [x] services/api-service/tests/test_call_log_writer.py exists
- [x] Commit 195eedb exists
- [x] Commit cf8ed95 exists
