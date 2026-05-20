# Phase 4 — Deferred Items

Out-of-scope issues discovered during plan execution. Not caused by the current task's changes.

| # | Item | Discovered During | Root Cause | Suggested Fix |
|---|------|-------------------|------------|---------------|
| 1 | `tests/test_health.py::test_ready_returns_200` fails (503 instead of 200) | 04-01 Task 1 verification | Test's `client` fixture creates `ASGITransport(app=app)` without running the FastAPI lifespan, so DB/Redis/CacheRedis are never initialised. `/ready` checks them and returns 503. Pre-existing issue from Phase 2 baseline; reproducible at `bacd92c` before any Phase 4 changes. | Either (a) wrap the test fixture with `async with LifespanManager(app)` from `asgi-lifespan`, or (b) mock the health check callables. Tracked separately from Phase 4 user-domain scope. |
