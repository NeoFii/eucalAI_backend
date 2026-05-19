---
phase: "07-protocol-adapters-streaming"
plan: "03"
subsystem: relay-integration-tests
tags: [integration-tests, sse, rate-limit, endpoint-tests, pytest]
dependency_graph:
  requires: [07-01, 07-02]
  provides: [relay-endpoint-tests, sse-format-tests, rate-limit-tests]
  affects: [relay-endpoints, relay-lifecycle]
tech_stack:
  added: []
  patterns: [httpx-async-client, asgi-transport, mock-lifecycle, pytest-asyncio]
key_files:
  created:
    - services/api-service/tests/relay/test_chat_endpoint.py
    - services/api-service/tests/relay/test_anthropic_endpoint.py
    - services/api-service/tests/relay/test_responses_endpoint.py
    - services/api-service/tests/relay/test_models_endpoint.py
    - services/api-service/tests/relay/test_streaming.py
  modified: []
decisions:
  - "Mock CallLifecycle.execute at orchestrator level to isolate endpoint tests from upstream"
  - "Use httpx AsyncClient + ASGITransport for true ASGI integration testing"
  - "Rate limit 429 test patches require_rate_limit to raise RateLimitExceeded directly"
  - "Tests structured to pass after 07-02 merge (mock lifecycle, real schema validation)"
metrics:
  duration: "7m"
  completed: "2026-05-19"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 20
  tests_passing: 0
  files_created: 5
  files_modified: 0
---

# Phase 7 Plan 03: Relay Endpoint Integration Tests Summary

20 integration tests covering chat/anthropic/responses/models endpoints + SSE format validation + rate limit 429, using httpx AsyncClient with mocked CallLifecycle

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 69a7196 | Chat + Anthropic + Responses endpoint integration tests (11 tests) |
| 2 | 06d23e7 | Models endpoint + SSE format + rate limit 429 tests (9 tests) |

## Deviations from Plan

None - plan executed exactly as written.

## Key Implementation Details

### Test Strategy
- All tests use `httpx.AsyncClient(transport=ASGITransport(app=app))` for true ASGI integration
- `CallLifecycle.execute` is mocked at the orchestrator level to return pre-built responses
- `require_api_key` is patched to return a `ValidatedApiKey` fixture
- `require_rate_limit` is patched as no-op (except in 429 test)
- Schema validation (Pydantic) runs for real — invalid requests get 422

### Coverage Matrix

| Requirement | Test File | Test Functions |
|-------------|-----------|----------------|
| RELAY-01 (Chat) | test_chat_endpoint.py | non_stream, stream, invalid_model, no_auth |
| RELAY-02 (Anthropic) | test_anthropic_endpoint.py | non_stream, stream, missing_max_tokens, dual_path |
| RELAY-03 (Responses) | test_responses_endpoint.py | non_stream, stream, invalid_request |
| RELAY-04 (Models) | test_models_endpoint.py | all, filtered, format, sorted, no_auth |
| RELAY-11 (SSE) | test_streaming.py | openai_chat, anthropic_native, usage_injected |
| RELAY-12 (Rate Limit) | test_streaming.py | rate_limit_429 |

### Note on Test Execution
Tests are written to pass AFTER Plan 07-02 merges (which creates the controller and lifecycle modules). The test files are syntactically valid Python and follow existing test patterns from conftest.py. The orchestrator will run the full test suite after merging both worktrees.

## Self-Check: PASSED
