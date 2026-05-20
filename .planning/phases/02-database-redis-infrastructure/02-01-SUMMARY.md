# Plan 02-01 Summary: SQLAlchemy async engine and session factory

**Status:** Complete
**Commits:** 4 atomic commits on `refactor/merge-api-service`

---

## What Was Done

### Task 1 — `api_service/core/db.py`
Created the DB runtime module that instantiates `ServiceDatabaseRuntime(Base)` and exports convenience functions: `create_engine`, `get_engine`, `init_session_factory`, `get_db`, `get_db_context`, `close_db`, plus `Base`.

### Task 2 — `api_service/db.py`
Created a thin Alembic proxy module (5 lines) that re-exports `Base` so `_env_shared.py`'s `importlib.import_module(f"{service_package}.db")` resolves correctly.

### Task 3 — Pool defaults override
Added `DATABASE_POOL_SIZE = 5` and `DATABASE_MAX_OVERFLOW = 10` to `ApiServiceSettings`, overriding the base defaults of 10/20. This ensures 4 workers x 15 = 60 max connections, safely within MySQL's 151 limit on the 2h4g server. Also fixed pre-existing ruff lint warnings (UP035/UP045).

### Task 4 — Lifespan + /ready + Snowflake
- Registered `"database"` resource at priority=20 with proper init/shutdown functions.
- Replaced the placeholder `/ready` endpoint with a real DB health check via `build_readiness_response` (returns 503 when DB is unreachable).
- Fixed `_init_snowflake` to use `os.getpid() % 32` instead of a static config value, preventing Snowflake ID collisions across uvicorn worker processes.

---

## Verification

All checks passed:
- `from api_service.core.db import get_db, close_db, create_engine, get_engine, init_session_factory, get_db_context, Base` — OK
- `api_service.db.Base.metadata` accessible — OK
- `settings.DATABASE_POOL_SIZE == 5`, `settings.DATABASE_MAX_OVERFLOW == 10` — OK
- `registry._resources` contains `"database"` at priority=20 with shutdown_fn — OK
- `_init_snowflake` uses `os.getpid() % 32` — OK
- `ruff check` passes on all modified files — OK

---

## Files Created
- `services/api-service/api_service/core/db.py`
- `services/api-service/api_service/db.py`

## Files Modified
- `services/api-service/api_service/core/config.py`
- `services/api-service/api_service/main.py`

---

## Decisions Applied
- D-04: pool_size=5, max_overflow=10
- D-12: Single Base + single ServiceDatabaseRuntime instance
- D-13: Base from `api_service.common.infra.db.base`
- D-16: DB engine priority=20 in lifespan registry
- D-09/D-10: os.getpid() % 32 for per-process Snowflake worker_id
