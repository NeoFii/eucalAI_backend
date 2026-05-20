---
phase: 05-admin-domain-controllers
plan: 05-01
subsystem: admin-domain
tags: [admin, auth, bootstrap, hmac, schemas-hoist, gating, foundation]
requires: []
provides:
  - api_service.common.schemas (BaseResponse, ErrorResponse, DateTimeModel, ApiResponse[T])
  - api_service.common.http.internal_signing (HMAC signature primitives — single source)
  - api_service.common.internal (HMAC sender — get_internal_json + circuit breaker)
  - api_service.common.core.exceptions (AdminConflictException 409, AdminPermissionDeniedException 403)
  - api_service.core.policies (require_active_admin, require_super_admin)
  - api_service.schemas.admin.{auth,admin_user,audit_log} (admin domain request/response schemas)
  - api_service.services.admin.{auth_service,bootstrap_service,audit_service}
  - api_service.controllers.admin (admin_router with /auth/* mounted; Wave 2 anchors)
  - lifespan registration of super_admin_bootstrap at priority=25
affects:
  - Phase 4 schemas/controllers (D-04 hoist — import path rewrite)
  - core/router.py (admin_router mount)
  - main.py (super_admin_bootstrap lifespan hook)
  - tests/conftest.py (mock_admin / mock_super_admin / mock_cache_redis / mock_internal_client fixtures)
tech-stack:
  added: []
  patterns:
    - D-04 hoist (single common schema source for unified envelopes)
    - D-02b explicit audit (record then commit at caller; flush-only inside audit service)
    - D-08 cookie path '/' (Next.js page middleware compatibility)
    - Pitfall 1 (HMAC signing primitives deduped into common/http/internal_signing.py)
    - Pitfall 6 (lifespan priority discipline)
    - Pitfall 8 (legacy envelope class names erased)
    - Pitfall 11+12 (api_service.* import rewrites; get_db_session → get_db)
    - Pitfall 13 (safe_audit_commit wrapper NOT ported)
    - Pitfall 14 (admin guards in core/policies.py)
    - Pitfall 15 (admin exception classes registered)
key-files:
  created:
    - services/api-service/api_service/common/schemas.py
    - services/api-service/api_service/common/http/internal_signing.py
    - services/api-service/api_service/common/internal.py
    - services/api-service/api_service/controllers/admin/__init__.py
    - services/api-service/api_service/controllers/admin/auth.py
    - services/api-service/api_service/services/admin/__init__.py
    - services/api-service/api_service/services/admin/auth_service.py
    - services/api-service/api_service/services/admin/bootstrap_service.py
    - services/api-service/api_service/services/admin/audit_service.py
    - services/api-service/api_service/schemas/admin/__init__.py
    - services/api-service/api_service/schemas/admin/auth.py
    - services/api-service/api_service/schemas/admin/admin_user.py
    - services/api-service/api_service/schemas/admin/audit_log.py
    - services/api-service/tests/test_admin_auth.py
    - services/api-service/tests/test_admin_bootstrap.py
    - services/api-service/tests/test_schemas_hoist.py
  modified:
    - services/api-service/api_service/common/http/internal_auth.py (dedupe — imports from internal_signing)
    - services/api-service/api_service/common/core/exceptions.py (+AdminConflictException, +AdminPermissionDeniedException)
    - services/api-service/api_service/core/config.py (+5 admin/circuit-breaker settings keys)
    - services/api-service/api_service/core/policies.py (+require_active_admin, +require_super_admin)
    - services/api-service/api_service/core/router.py (mount admin_router)
    - services/api-service/api_service/main.py (super_admin_bootstrap @ priority=25)
    - services/api-service/api_service/schemas/__init__.py (re-export from common.schemas)
    - services/api-service/api_service/schemas/common.py (deprecated empty stub)
    - services/api-service/api_service/schemas/auth.py (rewrite — BaseResponse)
    - services/api-service/api_service/schemas/billing.py (rewrite import path)
    - services/api-service/api_service/schemas/keys.py (rewrite import path)
    - services/api-service/api_service/schemas/model_catalog.py (rewrite import path)
    - services/api-service/api_service/controllers/auth.py (rewrite — BaseResponse)
    - services/api-service/api_service/controllers/billing.py (rewrite import path)
    - services/api-service/api_service/controllers/keys.py (rewrite — BaseResponse)
    - services/api-service/tests/conftest.py (admin fixtures + env defaults)
decisions:
  - D-01 admin endpoints under /api/v1/admin/* (foundation laid; auth.router mounted)
  - D-02b explicit audit per mutation (record + commit at caller; no decorator)
  - D-04 unified BaseResponse/ErrorResponse/DateTimeModel/ApiResponse[T] in common.schemas
  - D-08 cookie path "/" (overrides CONTEXT specifics suggestion — Next.js middleware needs it)
  - Pitfall 1 — signing primitives moved to common/http/internal_signing.py (single source)
  - Pitfall 6 — super_admin_bootstrap lifespan priority=25 (after DB=20, before Redis=30)
  - Pitfall 8 — legacy per-domain envelope class names erased; grep returns zero matches
  - Pitfall 13 — safe_audit_commit wrapper NOT ported
  - Wave 2 anchors present in controllers/admin/__init__.py AND schemas/admin/__init__.py
metrics:
  duration: ~1.5h
  completed_date: 2026-05-19
---

# Phase 5 Plan 05-01: Admin Auth + Bootstrap + Schemas Hoist Summary

Gating plan for Phase 5 — hoisted shared response envelopes to `api_service.common.schemas`, ported the HMAC sender + signing-primitive dedupe, added admin exceptions and admin policy guards, ported admin auth + bootstrap + bare AdminAuditService, mounted `admin_router` at `/api/v1/admin/`, and registered super-admin bootstrap as a lifespan hook at priority 25.

## Outcome (one-liner)

Phase 5's gating contract is in place: every symbol Plans 05-02 and 05-03 need to import resolves (D-04 unified envelopes, HMAC sender, AdminAuditService, admin policies, admin exceptions, the two Wave 2 anchor blocks). ADMIN-01 (admin auth) and ADMIN-12 (super-admin bootstrap) are fully covered by green tests.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1a | D-04 hoist (`common/schemas.py`) + Phase 4 import rewrite + `test_schemas_hoist.py` behaviors 1–4 | `519a5dd` |
| 1b | HMAC sender port + Pitfall 1 signing dedupe + admin exceptions + admin policies + 5 settings keys + `test_schemas_hoist.py` behaviors 5–9 | `160156f` |
| 2  | Admin auth controller (5 endpoints) + AdminAuthService + AdminBootstrapService + AdminAuditService + admin schemas + admin_router wiring + lifespan registration + `test_admin_auth.py` (5 tests) + `test_admin_bootstrap.py` (3 tests) | `58ca146` |

## VALIDATION Slots Covered (9 slots)

- `test_login_sets_cookies` — T-5-01 (cookie path=/, HttpOnly)
- `test_lockout` — T-5-02 (login_locked_until set after N failures)
- `test_logout_blacklists` — T-5-03 (blacklist_token awaited for BOTH access + refresh JTIs)
- `test_refresh_rotates` — refresh rotates both tokens, blacklists old refresh jti
- `test_change_password_invalidates` — T-5-04 (password hash updated, both JTIs blacklisted)
- `test_first_time_create` — ADMIN-12 (fresh DB → create super admin, audit row written)
- `test_idempotent` — ADMIN-12 (active super admin exists → no lock, no insertion)
- `test_optional` — ADMIN-12 (BOOTSTRAP_SUPERADMIN_ENABLED=False + REQUIRE_ON_STARTUP=False → graceful; True → RuntimeError)
- `test_phase4_imports_rewritten` — D-04 hoist verification (legacy alias ImportError, new path resolves)

Plus 5 supporting behavior tests in `test_schemas_hoist.py` (BaseResponse defaults, list-wrap preservation, ApiResponse generic, HMAC sender imports resolve, signing primitives deduped, admin exceptions present, admin policies are coroutines, 5 settings keys exist).

## Requirements Addressed

- **ADMIN-01** — full (admin login/logout/refresh/me/change-password operate against cookies; lockout + blacklist + rotation + password-change session invalidation all tested green).
- **ADMIN-12** — full (super-admin bootstrap creates on fresh DB, is idempotent on subsequent starts, respects `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP`).
- **Cross-cutting D-04** — hoist enacted; Phase 4 user files rewritten; legacy per-domain envelope class names erased.

## Decisions Enacted

- **D-01** admin endpoints under `/api/v1/admin/` prefix — `admin_router` mounted with `prefix="/admin"`; included into `api_router` without an extra prefix kwarg (would double-prefix).
- **D-02b** explicit audit-around-commit — `AdminAuditService.record(...)` flushes only; the calling service/controller commits the whole transaction. No `safe_audit_commit` wrapper (Pitfall 13).
- **D-04** unified `BaseResponse` / `ErrorResponse` / `DateTimeModel` / `ApiResponse[T]` live in `api_service.common.schemas`. Phase 4 files rewritten to use the new path.
- **D-08** admin cookie path `"/"` (overrides CONTEXT specifics suggestion `/api/v1/admin`) — Next.js page middleware needs to read the cookie before any /api request fires.
- **D-07 plan 1 of 3** — gating plan landed (Plans 05-02 / 05-03 may now proceed).

## Pitfalls Addressed

| Pitfall | Resolution |
|---------|------------|
| 1 — HMAC sender + signing dedupe | `common/http/internal_signing.py` is the single source; both sender (`common/internal.py`) and receiver (`common/http/internal_auth.py`) import from it. `inspect.getsource()` of either confirms no local `def _build_internal_signature`. |
| 2 — Audit transactional semantics | `AdminAuditService.record` uses `await db.flush()`; the caller commits. No try/except swallow. |
| 6 — Lifespan priority | `super_admin_bootstrap` registered at priority=25 (after DB=20, before Redis=30). |
| 7 — D-04 list-wrap preservation | `DateTimeModel.serialize_model` retains `list(data.items())` snapshot iteration. |
| 8 — Unified BaseResponse | Legacy per-domain envelope class names erased; `grep -rE "AuthBaseResponse|AuthErrorResponse|AdminBaseResponse" services/api-service/api_service/` returns no matches. |
| 11+12 — Import path rewrites | All admin-domain `from common.X` / `from utils.X` / `from services.X` / `from repositories.X` rewritten to `from api_service.*`. Verified by grep. |
| 13 — safe_audit_commit NOT ported | `grep -c safe_audit_commit services/api-service/api_service/services/admin/auth_service.py` returns 0. |
| 14 — Admin guards in `core/policies.py` | `require_active_admin` and `require_super_admin` added alongside the existing `require_active_user`. Both wrap `get_current_admin` (Phase 3 D-06). |
| 15 — Admin exception classes | `AdminConflictException` (409) and `AdminPermissionDeniedException` (403) registered in `common/core/exceptions.py`. |
| CONTEXT D-08 (was O-1) | `ADMIN_COOKIE_PATH = "/"` constant present in `controllers/admin/auth.py`; load-bearing source comment ported verbatim. |
| O-4 — AdminAuditCategory Literal | All 8 source members preserved (`all`, `governance`, `auth`, `user_management`, `model_catalog`, `routing_config`, `voucher`, `pool`). |

## Wave 2 Anchor Contract

The two anchor comment blocks needed for deterministic Wave 2 inserts are present in BOTH files:

```
# === Plan 05-02 imports (Wave 2) ===
# === Plan 05-03 imports (Wave 2) ===
```

- `services/api-service/api_service/controllers/admin/__init__.py` — Plans 05-02 / 05-03 will insert router includes below their anchor.
- `services/api-service/api_service/schemas/admin/__init__.py` — Plans 05-02 / 05-03 will insert schema re-exports below their anchor.

Both files contain the strings verbatim so the Wave 2 Edit calls have a unique `old_string` match.

## Task Split (Warning 4 Remediation)

Per the plan checker's Warning 4, the original Task 1 was split into:

- **Task 1a** — D-04 hoist + Phase 4 import rewrite + 4 behavior tests. ~12 files. Small blast radius; "land it green" gate for Task 1b.
- **Task 1b** — HMAC sender + signing dedupe + admin exceptions + admin policies + 5 settings keys + 5 behavior tests. ~6 files. Builds on Task 1a's green test suite.
- **Task 2** — Admin auth controller + 3 services + 3 schema modules + admin_router wiring + lifespan registration + 8 ADMIN-01/ADMIN-12 tests. ~15 files. Largest task; gated by Task 1b.

Each task kept within the ~10–30 % context budget while preserving the Wave 1 gating contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking issue] `api_service.core.enums` does not exist**

- **Found during:** Task 2 (porting `bootstrap_service.py`).
- **Issue:** The plan's `bootstrap_service.py` rewrite block specifies `from api_service.core.enums import AdminRole, AdminStatus`, but the api-service package layout puts the enums under `api_service.models.enums` (verified by `ls services/api-service/api_service/core/`).
- **Fix:** Rewrote the import to `from api_service.models.enums import AdminRole, AdminStatus`. The `core/policies.py` admin-guard addition uses the same path. Documented in the module docstring of `bootstrap_service.py`.
- **Files modified:** `services/api-service/api_service/services/admin/bootstrap_service.py`, `services/api-service/api_service/core/policies.py`.

**2. [Rule 3 — Blocking issue] `AdminAuditLogRepository` class renamed to `AuditLogRepository`**

- **Found during:** Task 2 (porting `audit_service.py`).
- **Issue:** The plan's `audit_service.py` interfaces block references `AdminAuditLogRepository`, but Phase 3 ships the merged repository under the name `AuditLogRepository` (verified via `repositories/__init__.py`). Both classes expose the same `.add` and `.list_logs` API.
- **Fix:** Imported `AuditLogRepository` directly from `api_service.repositories.audit_log_repository` (NOT via the `repositories.__init__` aggregator). Updated `audit_service.py` module docstring to mention the rename. Both `record` and `list_logs` use the renamed class.
- **Files modified:** `services/api-service/api_service/services/admin/audit_service.py`.

**3. [Rule 3 — Blocking issue] Pydantic Settings env-var validation in tests**

- **Found during:** Task 1a (running `test_schemas_hoist.py`).
- **Issue:** `ApiServiceSettings` validates `JWT_SECRET_KEY` length ≥ 32 and `INTERNAL_SECRET` length ≥ 32 at startup, raising `ValidationError` if either is unset. Existing tests set these per-file via `os.environ.setdefault(...)`. The new schemas-hoist test triggers settings instantiation transitively via `core.policies → core.dependencies.user → core.config`.
- **Fix:** Centralised the env-var defaults in `tests/conftest.py` at module-import time, BEFORE pytest loads test modules. This also pays down boilerplate in existing test files (they still keep their per-file setdefault calls, which are no-ops once conftest runs first).
- **Files modified:** `services/api-service/tests/conftest.py`.

### Settings override note (not a deviation — documented)

`INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD` and `INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS` already exist on `BaseServiceSettings` with defaults 3 / 30.0 (float). The plan requires admin-domain defaults of 5 / 30 (int). The override in `ApiServiceSettings` shadows the parent class defaults; Pydantic treats the subclass values as the canonical settings. `int = 30` vs parent's `float = 30.0` is intentional — admin-domain consumers expect integer seconds and the equality test (`== 30`) passes against both representations.

## Authentication Gates

None encountered during execution.

## Known Stubs

None — all admin auth and bootstrap code paths are wired end-to-end. Plan 05-02 and 05-03 will replace the remaining gateway HTTP calls with direct service-to-service Python calls; those are out of scope for this plan.

## Threat Flags

None — all threats in the plan's `<threat_model>` register (T-5-01 through T-5-D04 + T-5-HMAC + T-5-BOOT-1/2) are mitigated or accepted as documented in the plan. No new threat surfaces introduced.

## Pre-existing Test Failure (NOT my regression)

`tests/test_health.py::test_ready_returns_200` fails on the worktree base (commit `652dd8c`) because the test exercises `/ready` which requires a live DB + Redis. The failure is environmental and was already present before Plan 05-01 work began. Confirmed via `git stash + run + stash pop` against the base commit. The test is excluded with `--deselect tests/test_health.py::test_ready_returns_200` in regression runs; all 134 other tests pass.

## Self-Check: PASSED

- [x] `api_service/common/schemas.py` exists and exports `BaseResponse`, `ErrorResponse`, `DateTimeModel`, `ApiResponse`.
- [x] `api_service/common/http/internal_signing.py` exists; sender and receiver both import `_build_internal_signature` from it (verified via `inspect.getsource`).
- [x] `api_service/common/internal.py` exports `get_internal_client`, `get_internal_json`, `request_internal_json`, `close_internal_clients`, `reset_internal_circuit_breakers`, plus the 4 error classes.
- [x] `api_service/common/core/exceptions.py` defines `AdminConflictException` (409) and `AdminPermissionDeniedException` (403).
- [x] `api_service/core/policies.py` exports `require_active_admin` and `require_super_admin` as coroutine functions.
- [x] `api_service/core/config.py` has all 5 new settings keys with documented defaults.
- [x] `api_service/services/admin/{auth_service,bootstrap_service,audit_service}.py` all import cleanly.
- [x] `api_service/schemas/admin/{auth,admin_user,audit_log}.py` all import cleanly; `AdminAuditCategory` has the full 8-member literal.
- [x] `api_service/controllers/admin/{__init__,auth}.py` mount the 5 endpoints `/admin/auth/{login,logout,refresh,me,change-password}`.
- [x] `api_service/core/router.py` includes `admin_router`; final mount paths confirmed `/api/v1/admin/auth/*`.
- [x] `api_service/main.py` registers `super_admin_bootstrap` at priority=25.
- [x] Wave 2 anchors present (4 grep matches across 2 files).
- [x] No legacy `api_service.schemas.common` imports remain in `api_service/`.
- [x] No `AuthBaseResponse` / `AuthErrorResponse` / `AdminBaseResponse` references remain in `api_service/`.
- [x] No `safe_audit_commit` references remain in `services/admin/auth_service.py`.
- [x] Test suite green: 134 passed, 1 pre-existing infrastructure-dependent test deselected.
- [x] Three commits on the worktree branch: `519a5dd`, `160156f`, `58ca146`.
