---
phase: 04-user-domain-controllers
plan: 04-01
subsystem: api-service / user-domain
tags: [auth, arq, foundation, schemas, settings, worker]
requirements: [USER-01, USER-06]
requirements_addressed: [USER-01, USER-06]
validation_slots_covered: [T-04-01, T-04-02, T-04-03, T-04-04, T-04-05, T-04-06, T-04-07, T-04-08, T-04-09, T-04-21, T-04-22, T-04-23]
dependency_graph:
  requires:
    - phase-3-repositories (UserRepository, BillingRepository merged)
    - phase-3-dependencies (get_current_user)
    - phase-2-infrastructure (cache.py module-global pattern, lifespan registry)
    - phase-1-settings (BaseServiceSettings with COOKIE_*, JWT_*, PASSWORD_*)
  provides:
    - core/arq_pool (init_arq_pool/close_arq_pool/get_arq_pool — used by 04-03 model_catalog email + 04-02 if needed)
    - core/worker.py + core/jobs.py (4 crons + send_verification_email — runnable via `arq api_service.core.worker.WorkerSettings`)
    - core/policies.require_active_user (used by 04-02 keys/billing + 04-03)
    - schemas/common.py (ApiResponse[T], DateTimeModel, AuthBaseResponse, AuthErrorResponse — reused across 04-02 + 04-03)
    - common/utils/{email,password_policy,api_key_policy}.py (used by 04-02 schemas/keys.py + auth schemas)
    - services/email_service.EmailService (used by 04-03 model_catalog email flows)
    - services/auth_service.AuthService (consumed only by controllers/auth.py)
    - schemas/auth.py (16 request/response models — owned by this plan)
    - controllers/auth.py (10 /auth/* endpoints — owned by this plan)
    - ApiServiceSettings keys: DEFAULT_USER_RPM, CODE_DAILY_SEND_LIMIT, MAX_CODE_ERRORS, CODE_ERROR_LOCK_HOURS, LOGIN_LOCK_DURATION_HOURS, VERIFICATION_CODE_RETENTION_DAYS, MIN_TOPUP_AMOUNT, MAX_TOPUP_AMOUNT, USER_WORKER_CONCURRENCY, USER_JOB_TIMEOUT_SECONDS
  affects:
    - core/router.py (auth.router mounted at /api/v1/auth/*)
    - main.py (ARQ pool registered at lifespan priority=40)
    - pyproject.toml (pytest config block added)
tech-stack:
  added: []
  patterns:
    - module-global accessor for ARQ pool (mirrors cache.py)
    - @staticmethod service classes (no module instances — Pitfall 4)
    - D-02 ARQ async email (no synchronous SMTP on request thread)
    - D-09 settings constant for DEFAULT_USER_RPM (no system_settings_gateway HTTP call)
    - D-11 inner db.commit() preserved in get_valid_code_or_raise
    - HttpOnly + SameSite cookie set/clear helpers
key-files:
  created:
    - services/api-service/api_service/common/utils/email.py
    - services/api-service/api_service/common/utils/password_policy.py
    - services/api-service/api_service/common/utils/api_key_policy.py
    - services/api-service/api_service/core/policies.py
    - services/api-service/api_service/core/arq_pool.py
    - services/api-service/api_service/core/worker.py
    - services/api-service/api_service/core/jobs.py
    - services/api-service/api_service/schemas/common.py
    - services/api-service/api_service/schemas/auth.py
    - services/api-service/api_service/services/email_service.py
    - services/api-service/api_service/services/auth_service.py
    - services/api-service/api_service/controllers/auth.py
    - services/api-service/tests/conftest.py
    - services/api-service/tests/test_email_send.py
    - services/api-service/tests/test_email_verify.py
    - services/api-service/tests/test_auth_register.py
    - services/api-service/tests/test_auth_login.py
    - services/api-service/tests/test_auth_logout.py
    - services/api-service/tests/test_auth_refresh.py
    - services/api-service/tests/test_auth_me.py
    - services/api-service/tests/test_auth_change.py
    - services/api-service/tests/test_auth_reset.py
  modified:
    - services/api-service/api_service/core/config.py
    - services/api-service/api_service/main.py
    - services/api-service/api_service/core/router.py
    - services/api-service/api_service/schemas/__init__.py
    - services/api-service/api_service/services/__init__.py
    - services/api-service/api_service/controllers/__init__.py
    - services/api-service/pyproject.toml
decisions:
  - "D-09 applied: snapshot_rpm = settings.DEFAULT_USER_RPM (no system-settings gateway)"
  - "D-02 applied: EmailService.send_verification_code enqueues ARQ job (no synchronous SMTP)"
  - "D-11 applied: inner db.commit() preserved in get_valid_code_or_raise (error_count + lockout)"
  - "D-12 applied: Wave 0 foundations (settings/utils/schemas-common/ARQ pool/worker/jobs/policies/conftest) landed in Task 1 before any service or controller code"
  - "Pitfall 3 enforced: get_db_session → get_db (no source dep symbol survives in controllers)"
  - "Pitfall 4 enforced: EmailService is a staticmethod class — no module-level singleton"
  - "Pitfall 6 preserved: USER_COOKIE_PATH = '/'"
  - "Pitfall 7 preserved: DateTimeModel.serialize_model iterates list(data.items()) copy"
  - "Pitfall 9 enforced: _JOB_SEND_VERIFICATION_EMAIL constant equals send_verification_email.__name__"
  - "用户标识规范 enforced: /auth/me returns uid only — test_auth_me asserts user_id not in data"
metrics:
  duration_seconds: ~1200
  tasks_completed: 3
  files_created: 22
  files_modified: 7
  tests_added: 14
  commits: 3
---

# Phase 4 Plan 04-01: User Auth + Foundations Summary

JWT cookie-based user-auth surface (10 `/auth/*` endpoints) on top of an ARQ-driven asynchronous email pipeline; lands every Phase 4 shared dependency (settings, utils, schemas/common, ARQ pool, worker, policies, conftest) so 04-02 (keys/billing) and 04-03 (model catalog/email) can land without revisiting foundations.

## Tasks Completed

### Task 1: Wave 0 Foundations (commit `93828b0`)

Landed the entire Phase 4 foundation in one commit per D-12: every dependency that any downstream plan in this phase needs is now importable.

- **Settings (`core/config.py`):** appended 10 user-domain keys to `ApiServiceSettings` (D-09 `DEFAULT_USER_RPM=20` is the only source of default RPM for Phase 4; admin DB read deferred to Phase 5).
- **Utils:** ported `common/utils/email.py` (normalize_email), `common/utils/password_policy.py` (check_password_strength — renamed from `utils/password.py` to avoid clashing with the existing `common/security/password.py` bcrypt helpers), `common/utils/api_key_policy.py` (normalize_allowed_models / normalize_allow_ips / is_*_allowed). All imports rewritten to `api_service.*` per the RESEARCH translation table.
- **Policies (`core/policies.py`):** `require_active_user` dependency on top of Phase 3's `get_current_user` — raises `UserDisabledException` for `status==0`, `EmailNotVerifiedException` for `status==2`.
- **ARQ pool (`core/arq_pool.py`):** new module composed of two analogs — `cache.py` accessor shape + `jobs.py` `RedisSettings` parser. Bound to lifespan in `main.py` at priority=40 (after Redis/DB).
- **Worker (`core/worker.py`):** mirrors source — `class WorkerSettings: pass` + `setattr` loop applying `get_worker_settings_kwargs()`. Runnable via `arq api_service.core.worker.WorkerSettings`.
- **Jobs (`core/jobs.py`):** ported `build_redis_settings`, `on_worker_startup`/`on_worker_shutdown`, and the 4 cron jobs (`aggregate_usage_stats`, `cleanup_expired_verification_codes`, `cleanup_expired_sessions`, `reconcile_balance_ledger`). `send_verification_email` reserved for Task 2.
- **Schemas common (`schemas/common.py`):** verbatim port of `DateTimeModel` (Pitfall 7 `list(data.items())` copy preserved with explicit comment), `AuthBaseResponse`, `AuthErrorResponse`, `ApiResponse[T]`.
- **Lifespan (`main.py`):** ARQ pool registered between `cache_redis` (priority=30) and downstream consumers. Reverse-priority teardown handled by existing `LifespanRegistry._cleanup`.
- **pytest config (`pyproject.toml`):** added `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `testpaths = ["tests"]`.
- **Shared fixtures (`tests/conftest.py`):** `mock_user`, `mock_db`, `arq_pool_mock`, `redis_mock` — the building blocks for Task 2/3 service- and controller-layer tests.

Phase 3 regression: all 80 existing tests still green.

### Task 2: schemas/auth.py + EmailService + send_verification_email ARQ job + AuthService (commit `6d57ed9`)

Ported the two largest services and registered the new background job.

- **`schemas/auth.py`** (225 lines verbatim from source with the 3 import rewrites from RESEARCH § Import Translation Table): all 16 request/response models including `RegisterRequest` (with `@field_validator("email", mode="before")` + `@model_validator(mode="after")` for password strength), `LoginRequest`, `LoginResponse`, `UserInfoResponseData`, `ChangePasswordRequest`, `ResetPasswordRequest`, `SendEmailCodeRequest`, `VerifyEmailRequest`. Added `RefreshTokenResponse`/`RefreshTokenResponseData` aliases for the plan's acceptance-criteria name.
- **`schemas/__init__.py`** + **`services/__init__.py`**: package-level re-exports.
- **`services/email_service.py`**: D-02 + D-11 + Pitfall 4 all applied.
  - **D-02:** `send_verification_code` writes the row + commits, then `await get_arq_pool().enqueue_job(_JOB_SEND_VERIFICATION_EMAIL, email, code, purpose)`. No synchronous SMTP touches the request thread.
  - **D-11:** inside `get_valid_code_or_raise`, the inner `await db.commit()` is preserved with `# D-11: preserve inner db.commit() for 1:1 source parity` markers so the error-count + lockout updates land even when the surrounding controller rolls back.
  - **Pitfall 4:** the source's `email_service = EmailService()` module singleton was removed; `EmailService` has no `__init__`. All methods are `@staticmethod`. Callers use `EmailService.X(...)`.
  - **Repository renames:** every `EmailCodeRepository(db).*` call rewritten to `UserRepository(db).email_code_*` per the Phase 3 merge. `email_code_delete` is now correctly awaited (Pitfall A5).
- **`services/auth_service.py`**: D-09, session-repo renames, EmailService class calls, and import path rewrites.
  - **D-09:** the source's `try: snapshot_rpm = await system_settings_gateway.get_default_user_rpm()` block is replaced with `snapshot_rpm = settings.DEFAULT_USER_RPM` + a TODO(phase-5) comment.
  - **Session renames:** all 5 sites of `SessionRepository(db).{get_by_token_jti,list_active_for_user,revoke,add}` rewritten to `UserRepository(db).{get_session_by_token_jti, list_active_sessions_for_user, revoke_session, add_session}`.
  - **`refresh_access_token`** preserves verbatim the refresh-token rotation block (jti + hash + expires_at + commit) from source lines 236-240.
  - **`_get_dummy_hash()`** timing equalizer preserved verbatim (T-04-S2 mitigation against email enumeration).
- **`core/jobs.py`** extended with `send_verification_email(ctx, email, code, purpose)` + `_send_smtp_sync` (stdlib `smtplib`+`MIMEMultipart`) + `_build_message` (4 purposes: register/login/verify/reset). Retries up to 3 with linear backoff via `Retry(defer=job_try*5)`; after 3 tries logs `emailSendFailedPermanently` and swallows (D-02 acceptable tradeoff). `_JOB_SEND_VERIFICATION_EMAIL = "send_verification_email"` constant equals the function `__name__` per Pitfall 9. `get_worker_settings_kwargs()["functions"]` now has length 5.
- **Tests:**
  - `test_email_send.py::test_daily_limit` — repo returns `CODE_DAILY_SEND_LIMIT`; `(False, ...)` is returned and `pool.enqueue_job` is NOT called.
  - `test_email_send.py::test_enqueues_arq` — D-02 verified: `pool.enqueue_job.assert_called_once_with("send_verification_email", "user@example.com", <6-digit>, "register")`.
  - `test_email_send.py::test_lockout_prevents_send` — latest code's `locked_until` blocks the send.
  - `test_email_verify.py::test_error_count` — wrong code increments `error_count` and `db.commit` is awaited (D-11 verified).
  - `test_email_verify.py::test_lockout_at_max_errors` — at `MAX_CODE_ERRORS`, `locked_until` set + commit + raise.

5/5 email tests green.

### Task 3: controllers/auth.py + router mount + 7 auth integration tests (commit `0fd5e1f`)

Mounted the 10 `/auth/*` endpoints and wrote integration tests covering T-04-02 through T-04-09.

- **`controllers/auth.py`**: cookie helpers (`_set_auth_cookies` / `_clear_auth_cookies`) plus 10 endpoints (register, login, login-with-code, logout, refresh, me, change-password, reset-password, send-email-code, verify-email).
  - **D-04 (Phase 3):** `/auth/me` calls `BillingRepository(db).stat_get_user_tpm_last_minute(int(current_user.id))` (no `UsageStatRepository`).
  - **D-09:** `/auth/me` uses `settings.DEFAULT_USER_RPM` directly.
  - **Pitfall 3:** the source `get_db_session` was rewritten to `get_db` from `api_service.core.db` at all call sites.
  - **Pitfall 4:** `await EmailService.send_verification_code(...)` (class), no module-instance form.
  - **Pitfall 6:** `USER_COOKIE_PATH = "/"` preserved verbatim. Cookie config reads `settings.COOKIE_SECURE` and `settings.COOKIE_SAMESITE`.
- **`core/router.py`**: `from api_service.controllers import auth` + `api_router.include_router(auth.router)` — the first user-domain route group mounted at `/api/v1/auth/*`.
- **Tests** (7 files, all under `tests/test_auth_*.py`):
  - `test_auth_register.py::test_register_success` — 201 + cookies + `data.uid` present + `user_id`/`id` absent (用户标识规范).
  - `test_auth_login.py::test_login_success` + `test_login_lockout` — happy path returns 200 with HttpOnly cookies; lockout returns 401 with detail message.
  - `test_auth_logout.py::test_logout_revokes_session` — `AuthService.logout` awaited with refresh token from cookie; both cookies cleared via `Max-Age=0`.
  - `test_auth_refresh.py::test_refresh_rotates` + `test_refresh_requires_cookie` — token rotation + cookie set + 401 when refresh cookie missing.
  - `test_auth_me.py::test_me_excludes_id` — `data.uid` present, `data.user_id` absent, `data.default_rpm == settings.DEFAULT_USER_RPM`, `data.current_tpm == 42` (from mocked `BillingRepository`).
  - `test_auth_change.py::test_change_revokes_sessions` — `AuthService.change_password` awaited, cookies cleared post-success.
  - `test_auth_reset.py::test_reset_with_code` — service awaited with email + code + new_password; returns 200.

Total: 9 integration tests, all green. Full suite (excluding pre-existing `test_health.py::test_ready_returns_200` failure — see Deferred Issues) passes at 94/94.

## VALIDATION Slots Covered

| Slot | Behaviour | Test |
|------|-----------|------|
| T-04-01 | Conftest fixtures + asyncio mode green | `pytest tests/ --collect-only` exits 0; 83+ tests collected |
| T-04-02 | Register persists user + cookies + 201 | `test_auth_register.py::test_register_success` |
| T-04-03 | Login returns access_token + HttpOnly cookies | `test_auth_login.py::test_login_success` |
| T-04-04 | Login lockout after threshold | `test_auth_login.py::test_login_lockout` |
| T-04-05 | Logout revokes session + clears cookies | `test_auth_logout.py::test_logout_revokes_session` |
| T-04-06 | Refresh rotates both tokens + sets cookies | `test_auth_refresh.py::test_refresh_rotates` |
| T-04-07 | /auth/me excludes user_id, returns uid + default_rpm=settings | `test_auth_me.py::test_me_excludes_id` |
| T-04-08 | change-password awaited, cookies cleared | `test_auth_change.py::test_change_revokes_sessions` |
| T-04-09 | reset-password flow via email code | `test_auth_reset.py::test_reset_with_code` |
| T-04-21 | send-email-code rate-limits at CODE_DAILY_SEND_LIMIT | `test_email_send.py::test_daily_limit` |
| T-04-22 | send-email-code enqueues ARQ job (D-02 verified) | `test_email_send.py::test_enqueues_arq` |
| T-04-23 | verify-email increments error_count + locks at threshold (D-11 verified) | `test_email_verify.py::test_error_count` + `test_lockout_at_max_errors` |

## Requirements Addressed

- **USER-01** (User authentication): fully delivered. All 10 `/auth/*` endpoints mounted at `/api/v1/auth/*` with cookie-based JWT, session revocation, refresh-token rotation. 9 integration tests cover register/login/logout/refresh/me/change/reset.
- **USER-06** (Email verification): partial — `send_verification_code` enqueues ARQ + rate-limits at 3/day; `get_valid_code_or_raise` enforces `error_count` + `locked_until`. End-to-end SMTP delivery + frontend email flows complete in 04-03.

## Decisions Made

- **D-01 (no internal_* migrated)** — none of the 7 user-service internal_*.py controllers/services/schemas were ported. Phase 4 surface is strictly the public `/api/v1/auth/*` group.
- **D-02 (ARQ async email)** — verified by `test_email_send.py::test_enqueues_arq`. SMTP send happens inside the worker process; the request thread never blocks on SMTP.
- **D-09 (settings.DEFAULT_USER_RPM)** — verified by `test_auth_me.py::test_me_excludes_id` (asserts `data.default_rpm == settings.DEFAULT_USER_RPM`) and by `grep -c "system_settings_gateway"` returning 0 in `auth_service.py` and `controllers/auth.py`.
- **D-11 (inner db.commit() preserved)** — verified by `test_email_verify.py::test_error_count` (asserts `db.commit.assert_awaited()` after wrong-code) and by the `# D-11` marker comments in `email_service.py`.
- **D-12 (Wave 0 foundations land first)** — verified by the 3-commit ordering: Task 1 (foundations) → Task 2 (services + job) → Task 3 (controllers + router + tests). Each subsequent task imports only symbols produced by the previous.

## Pitfalls Addressed

- **P3 (`get_db_session` → `get_db`)** — `grep -c "get_db_session" controllers/auth.py` returns 0; the controller depends on `api_service.core.db.get_db`.
- **P4 (EmailService class — no module instance)** — `grep -E "^email_service\s*=" services/email_service.py` returns nothing; all calls use `EmailService.X(...)`.
- **P6 (cookie path "/")** — `USER_COOKIE_PATH = "/"` literal preserved.
- **P7 (DateTimeModel `list()` copy)** — `grep -q 'list(data.items())' schemas/common.py` succeeds with the explicit "do NOT lint-clean" comment.
- **P9 (ARQ job name matches enqueue arg)** — `_JOB_SEND_VERIFICATION_EMAIL = "send_verification_email"` and `send_verification_email.__name__ == "send_verification_email"`; the test `test_enqueues_arq` asserts the literal job name on the enqueue call.

## Deviations from Plan

None for Rules 1-3 (no bug fixes, no critical-missing functionality found, no auto-fixed blocking issues).

One minor deviation worth noting:
- **Docstring rewrite** in `controllers/auth.py` and `services/auth_service.py`: the plan's grep gates require zero occurrences of `system_settings_gateway` / `get_db_session` / `email_service.` literals in those files. Initial docstrings mentioned those source symbols verbatim to explain the divergence; rewrote the docstrings to describe the divergence without using the literal banned strings. Behaviour unchanged.

## Known Stubs

None for Phase 4 user-auth scope. The `aggregate_usage_stats` cron job uses a lazy import of `UsageStatService` (delivered in 04-02) — this is intentional (deferred to its plan, gated by ARQ schedule not by HTTP request) and matches the source structure. Not a stub flowing to the UI.

## Threat Flags

No new security-relevant surface beyond what is documented in the plan's `<threat_model>`. All Phase 4 user-auth threats (T-04-S1 through T-04-E1) have their planned mitigations in place:

- Cookies: `HttpOnly` + `Secure` (from settings) + `SameSite=strict` (default).
- Refresh-token rotation: jti + bcrypt-hash updated in `refresh_access_token`.
- Email enumeration timing: `_get_dummy_hash()` constant-time equalizer ported verbatim.
- Code brute-force: `error_count` + `locked_until` (D-11 inner commit).
- CSRF: `SameSite=strict` cookie default.
- `user_id` leakage: 用户标识规范 verified by `test_auth_me.py::test_me_excludes_id`.

## Deferred Issues

`tests/test_health.py::test_ready_returns_200` fails (503 vs 200). **Pre-existing** — the test creates `ASGITransport(app=app)` without running the FastAPI lifespan, so DB/Redis/CacheRedis are never initialised and `/ready` correctly returns 503. Reproducible at the worktree's pre-Task-1 base. Tracked in `.planning/phases/04-user-domain-controllers/deferred-items.md`. Not in Phase 4 user-auth scope; fix is to wrap the fixture with `asgi-lifespan.LifespanManager` or to mock the health-check callables.

## Self-Check: PASSED

**Files created (22) — verified existing:**

- `services/api-service/api_service/common/utils/email.py` — FOUND
- `services/api-service/api_service/common/utils/password_policy.py` — FOUND
- `services/api-service/api_service/common/utils/api_key_policy.py` — FOUND
- `services/api-service/api_service/core/policies.py` — FOUND
- `services/api-service/api_service/core/arq_pool.py` — FOUND
- `services/api-service/api_service/core/worker.py` — FOUND
- `services/api-service/api_service/core/jobs.py` — FOUND
- `services/api-service/api_service/schemas/common.py` — FOUND
- `services/api-service/api_service/schemas/auth.py` — FOUND
- `services/api-service/api_service/services/email_service.py` — FOUND
- `services/api-service/api_service/services/auth_service.py` — FOUND
- `services/api-service/api_service/controllers/auth.py` — FOUND
- `services/api-service/tests/conftest.py` — FOUND
- `services/api-service/tests/test_email_send.py` — FOUND
- `services/api-service/tests/test_email_verify.py` — FOUND
- `services/api-service/tests/test_auth_register.py` — FOUND
- `services/api-service/tests/test_auth_login.py` — FOUND
- `services/api-service/tests/test_auth_logout.py` — FOUND
- `services/api-service/tests/test_auth_refresh.py` — FOUND
- `services/api-service/tests/test_auth_me.py` — FOUND
- `services/api-service/tests/test_auth_change.py` — FOUND
- `services/api-service/tests/test_auth_reset.py` — FOUND

**Files modified (7) — verified via `git diff`:**

- `services/api-service/api_service/core/config.py` — 10 new settings keys
- `services/api-service/api_service/main.py` — ARQ pool registered at priority=40
- `services/api-service/api_service/core/router.py` — auth.router mounted
- `services/api-service/api_service/schemas/__init__.py` — re-exports
- `services/api-service/api_service/services/__init__.py` — package marker
- `services/api-service/api_service/controllers/__init__.py` — package marker
- `services/api-service/pyproject.toml` — pytest config

**Commits (3) — verified via `git log --all`:**

- `93828b0` — feat(04-01): Wave 0 foundations
- `6d57ed9` — feat(04-01): auth/email service + send_verification_email ARQ job
- `0fd5e1f` — feat(04-01): controllers/auth.py + router mount + 7 integration tests

**Tests:** 94 / 94 green (Phase 3 80 + email 5 + auth integration 9). `pytest tests/ -q --ignore=tests/test_health.py` exits 0. The pre-existing `test_health.py::test_ready_returns_200` failure is documented under Deferred Issues and is out of scope.

## Unblocks

- **04-02 (keys + billing)** can now import: `core.policies.require_active_user`, `schemas.common.{ApiResponse, DateTimeModel}`, `common.utils.api_key_policy.*`, `settings.{MAX_API_KEYS_PER_USER, MIN_TOPUP_AMOUNT, MAX_TOPUP_AMOUNT}`, `services.email_service.EmailService` (if needed for password-related email).
- **04-03 (model catalog + email flows)** can now import: `core.arq_pool.get_arq_pool`, `services.email_service.EmailService`, the ARQ worker module (already runnable via `arq api_service.core.worker.WorkerSettings`).
