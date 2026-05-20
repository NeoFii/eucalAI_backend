---
phase: 09-integration-testing
plan: 01
subsystem: relay
tags: [integration-test, e2e, relay, billing, call-log]
dependency_graph:
  requires: [api-service relay lifecycle, DB models, Redis cache]
  provides: [E2E relay test suite, integration test infrastructure]
  affects: [services/api-service/tests/integration/]
tech_stack:
  added: []
  patterns: [ASGITransport test client, transaction rollback isolation, seed fixtures]
key_files:
  created:
    - services/api-service/tests/integration/__init__.py
    - services/api-service/tests/integration/conftest.py
    - services/api-service/tests/integration/test_relay_e2e.py
  modified: []
decisions:
  - "Transaction rollback per test for DB isolation (D-04 pattern)"
  - "ASGITransport buffers full response — SSE tests parse resp.text"
  - "Rate limiting disabled in integration tests via env var"
  - "Seed routing config uses encrypted API key with test master key"
metrics:
  duration_seconds: 403
  completed: "2026-05-19T15:42:18Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 0
---

# Phase 9 Plan 01: E2E Relay Integration Tests Summary

Integration test infrastructure + 10 E2E relay tests covering all 3 protocols in stream/non-stream modes with balance and log verification.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Integration test conftest with real DB/Redis fixtures | b2cfe3e | conftest.py (337 lines) |
| 2 | E2E relay flow tests for 3 protocols | 4d76f04 | test_relay_e2e.py (314 lines) |

## What Was Built

### conftest.py — Integration Test Infrastructure
- Session-scoped: engine (eucal_ai_test), session_factory, cache_redis (db/2), queue_redis (db/1)
- Function-scoped: db_session (transaction rollback), app_client (ASGITransport + overrides)
- Seed fixtures: user, api_key (SHA-256 hash), routing_config (vendor/model/pool/account/pmc)
- init_relay: wires RoutingConfigCache, InferenceClient, ChannelSelector, SdkClientPool
- seed_balance_in_redis: sets user balance in Redis hot path

### test_relay_e2e.py — 10 E2E Test Cases
1. OpenAI Chat non-stream: validates choices, message.content, usage tokens
2. OpenAI Chat stream: validates SSE format, delta chunks, [DONE] marker
3. Anthropic Messages non-stream: validates content[0].text, usage.input_tokens
4. Anthropic Messages stream: validates message_start/content_block_delta/message_stop
5. OpenAI Responses non-stream: validates output array
6. OpenAI Responses stream: validates response.created/response.completed events
7. Balance deduction: verifies Redis balance decreases after relay
8. Call log persistence: verifies ApiCallLog row in DB after relay
9. Invalid API key: returns 401
10. Insufficient balance: returns 402

## Deviations from Plan

None - plan executed exactly as written.

## Decisions Made

- Rate limiting disabled via `RATE_LIMIT_ENABLED=false` env var to avoid test flakiness
- `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=false` to skip admin bootstrap in tests
- Used `pytest_asyncio.fixture` decorator (not `pytest.fixture`) per pytest-asyncio 0.24 strict mode

## Known Stubs

None — all fixtures wire real components; tests depend on live infrastructure.

## Self-Check: PASSED

- [x] services/api-service/tests/integration/__init__.py exists
- [x] services/api-service/tests/integration/conftest.py exists (337 lines >= 100)
- [x] services/api-service/tests/integration/test_relay_e2e.py exists (314 lines >= 200)
- [x] Commit b2cfe3e exists (Task 1)
- [x] Commit 4d76f04 exists (Task 2)
- [x] 10 tests collected successfully
