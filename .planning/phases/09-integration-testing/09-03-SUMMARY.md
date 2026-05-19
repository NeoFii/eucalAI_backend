---
phase: "09"
plan: "03"
subsystem: api-service/tests
tags: [integration-test, resource-constraint, snowflake, concurrency]
dependency_graph:
  requires: [09-01]
  provides: [resource-validation, snowflake-concurrency-proof]
  affects: [api-service]
tech_stack:
  added: []
  patterns: [asyncio-concurrency-test, subprocess-process-management, psutil-memory-measurement]
key_files:
  created:
    - services/api-service/tests/integration/test_resource_concurrency.py
  modified:
    - services/api-service/pyproject.toml
decisions:
  - "Used asyncio coroutines (not threads) for snowflake concurrency tests — matches production pattern where uvicorn workers are separate processes each running a single-threaded event loop"
  - "Cross-worker test uses ThreadPoolExecutor with separate generator instances — simulates separate processes with different worker_ids"
  - "Registered 'slow' pytest marker in pyproject.toml to suppress warnings"
metrics:
  duration: "345s"
  completed: "2026-05-19T15:52:40Z"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 1
---

# Phase 9 Plan 3: Resource Constraint & Snowflake Concurrency Tests Summary

Resource constraint validation proving 4-worker uvicorn stays under 1.5GB RSS, plus Snowflake ID zero-collision proof under concurrent async load for both worker_id configurations.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Memory limit + Snowflake concurrency tests | d0edca6 | tests/integration/test_resource_concurrency.py |

## Implementation Details

### Part A: Memory Limit Test (D-09, D-10)

`test_four_workers_memory_under_limit` (marked `@pytest.mark.slow`):
- Spawns real uvicorn with 4 workers via subprocess
- Polls `/health` for startup (30s timeout)
- Sends 20 concurrent warmup requests
- Measures total RSS via psutil (parent + children)
- Asserts < 1.5GB
- try/finally ensures process cleanup (T-09-06 mitigation)

### Part B: Snowflake ID Concurrency Tests (D-11, D-12)

`test_snowflake_worker1_no_collision`:
- Configures global generator with worker_id=1, datacenter_id=1
- 4 asyncio coroutines each generate 10000 IDs via `generate_snowflake_id()`
- Yields control every 1000 IDs to simulate real async interleaving
- Asserts 40000 unique IDs (zero collisions)

`test_snowflake_worker2_no_collision`:
- Same pattern with worker_id=2

`test_snowflake_cross_worker_no_collision`:
- Generates 10000 IDs with worker_id=1 and 10000 with worker_id=2 (separate generator instances in separate threads)
- Asserts combined 20000 IDs have zero overlap

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Concurrency model mismatch**
- **Found during:** Task 1 initial implementation
- **Issue:** Plan suggested ThreadPoolExecutor for worker1/worker2 tests, but `SnowflakeGenerator` from the `snowflake` library is not thread-safe (Python generator `next()` is not atomic). Multiple threads sharing one instance or multiple instances with same instance_id produce collisions.
- **Fix:** Used asyncio coroutines with `asyncio.sleep(0)` yields for worker1/worker2 tests (matches production pattern: single-threaded event loop per process). Cross-worker test uses ThreadPoolExecutor with separate generator instances (each thread = separate process simulation).
- **Files modified:** services/api-service/tests/integration/test_resource_concurrency.py
- **Commit:** d0edca6

**2. [Rule 3 - Blocking] Missing pytest marker registration**
- **Found during:** Task 1 verification
- **Issue:** `@pytest.mark.slow` produced `PytestUnknownMarkWarning`
- **Fix:** Added `markers` config to `[tool.pytest.ini_options]` in pyproject.toml
- **Files modified:** services/api-service/pyproject.toml
- **Commit:** d0edca6

## Known Stubs

None — all tests are fully implemented with real assertions.

## Self-Check: PASSED

- [x] services/api-service/tests/integration/test_resource_concurrency.py exists
- [x] Commit d0edca6 found in git log
- [x] 09-03-SUMMARY.md created
