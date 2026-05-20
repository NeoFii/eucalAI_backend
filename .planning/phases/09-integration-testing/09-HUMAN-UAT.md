---
status: partial
phase: 09-integration-testing
source: [09-VERIFICATION.md]
started: 2026-05-20T08:15:00Z
updated: 2026-05-20T08:15:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Full E2E Relay Test Suite
expected: Run `pytest tests/integration/test_relay_e2e.py -v` with live MySQL + Redis + inference-service. All 10 tests pass (3 protocols x stream/non-stream + billing + logging + error cases).
result: [pending]

### 2. Memory Limit Test (4 workers under 1.5GB)
expected: Run `pytest tests/integration/test_resource_concurrency.py::test_four_workers_memory_under_limit -v`. 4-worker uvicorn total RSS < 1.5GB.
result: [pending]

### 3. Admin Cache Propagation Tests
expected: Run `pytest tests/integration/test_admin_relay_cache.py -v` with live MySQL + Redis. All 5 tests pass verifying admin config -> Redis version INCR -> cache reload pipeline.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
