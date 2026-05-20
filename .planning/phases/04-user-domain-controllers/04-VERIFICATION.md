---
phase: 04-user-domain-controllers
verified: 2026-05-19T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
gaps: []
human_verification:
  - test: "Logout endpoint silently succeeds on backend errors (CR-01 from 04-REVIEW)"
    expected: "When AuthService.logout raises a non-SessionNotFoundException error (DB outage, deadlock, integrity violation), the API should propagate the failure to the client (HTTP 5xx) — not return 200 'logged out' while leaving the session row alive on the server."
    why_human: "Goal-backward parity check: source user-service had the same broad `except Exception:` swallow at this site. Phase 4 ported it verbatim per D-03 ('1:1 source parity'). Operator must decide whether 'works identically' includes preserving this hazard or whether Phase 4 should diverge here. Manual verification: simulate a DB failure during /auth/logout in a staging environment and observe (a) the HTTP response code, (b) the user_sessions row state. Then compare to current user-service behavior (`services/user-service/src/controllers/auth.py`)."
  - test: "Refresh-token rotation TOCTOU window — client cookies cleared while server-side session still valid (CR-02 from 04-REVIEW)"
    expected: "If AuthService.refresh_access_token raises mid-execution (e.g. hash_password_async fails after token_jti has been set but before db.commit), the server-side session row should also be revoked — not just rolled back. Otherwise the user is locked out client-side but their captured refresh token still works on the server."
    why_human: "Requires triggering an exception inside the refresh-token mutation block in a live system. No deterministic unit-test path exists for the partial-update window. Verify by running staging with hash_password_async injected to raise after the first awaitable, then checking user_sessions.token_jti against the cleared cookie value."
  - test: "ARQ pool readiness probe gap (CR-03 from 04-REVIEW)"
    expected: "/ready should fail when ARQ Redis db/1 is unreachable, because /auth/send-email-code will fail at runtime. Currently /ready only checks DB + Redis db/0 + Cache Redis db/2."
    why_human: "Verify by stopping Redis db/1 in staging, calling /ready (should be 503), then calling /auth/send-email-code (should be 503 or queue-down error). If /ready returns 200 while send-email-code fails, the K8s/load-balancer probe will route traffic to a broken pod. This is a deployment-level concern outside automated test scope."
  - test: "Phase 4 endpoint contract matches user-service behavior across all 27 paths under load"
    expected: "Each of the 27 endpoints (10 /auth/* + 5 /keys/* + 8 /billing/* + 4 /models* + /model-vendors) returns the same status code, response envelope, cookie behavior, and error-mapping as the current user-service under realistic traffic."
    why_human: "Mocked unit/integration tests pass but cannot prove on-the-wire parity. Run side-by-side parallel deployment (user-service vs api-service) and replay representative traffic, comparing responses field-by-field. This is the standard pre-cutover validation per ROADMAP Phase 10 / DEPL-03 expectation."
  - test: "SMTP delivery actually reaches the user mailbox via ARQ worker (USER-06 end-to-end)"
    expected: "POST /auth/send-email-code enqueues the job; the ARQ worker (`arq api_service.core.worker.WorkerSettings`) starts, picks up the job, calls _send_smtp_sync with SMTP credentials from settings, and the recipient receives a 6-digit code email within ~10 seconds."
    why_human: "Tests cover the enqueue path (test_email_send.py::test_enqueues_arq) but not the worker side. SMTP requires real credentials, network, and a recipient mailbox. Verify in staging with a test SMTP server (or mailtrap.io) by running the worker, hitting /auth/send-email-code, and confirming receipt."
  - test: "MIN_TOPUP_AMOUNT / MAX_TOPUP_AMOUNT dead config decision (WR-04 from 04-REVIEW)"
    expected: "Decide whether the two settings (declared in config.py:58-59 but never referenced in any service or controller) should be (a) removed from config now, or (b) left for Phase 5 admin-topup endpoint to wire."
    why_human: "Dead config is a maintenance hazard but not a Phase 4 functional regression — the user-facing /topup-orders is read-only (per 04-02 SUMMARY 'Deviations from Plan'), so the bounds are not currently enforceable. Owner must decide the disposition before Phase 5 adds an admin POST that could topup arbitrary amounts."
---

# Phase 4: User Domain Controllers — Verification Report

**Phase Goal:** All user-facing endpoints (auth, API keys, billing, models) work identically to current user-service
**Verified:** 2026-05-19
**Status:** human_needed (all automated must-haves verified; six items require human attestation before cutover)
**Re-verification:** No — initial verification

## Goal Achievement

The phase goal is **feature parity** with the current user-service. All 27 user-facing endpoints are mounted, all declared must-haves (USER-01 / USER-04 / USER-05 / USER-06) are implemented, every plan's grep-verifiable gates hold up against the live codebase, and 115/115 Phase 4 tests pass. The phase goal is materially achieved.

The `human_needed` status reflects that "works identically" is a behavioral claim that ultimately requires either side-by-side traffic replay or live SMTP/Redis validation to confirm — neither is reachable with automated checks. Three CR findings from `04-REVIEW.md` describe code patterns ported verbatim from user-service (per D-03 "1:1 source parity"); operator must decide whether parity itself satisfies the goal or whether Phase 4 should diverge to fix pre-existing user-service bugs.

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can register, login, logout, and refresh tokens via cookie-based JWT | VERIFIED | 10 /auth/* endpoints mounted; `controllers/auth.py:56` `APIRouter(tags=["认证"])` exposes register/login/login-with-code/logout/refresh/me/change-password/reset-password/send-email-code/verify-email; `_set_auth_cookies` (lines 68-86) sets HttpOnly + Secure + SameSite cookies; `AuthService.refresh_access_token` (lines 243-247) rotates token_jti + refresh_token_hash + expires_at + commits. Tests `test_auth_register.py`, `test_auth_login.py`, `test_auth_logout.py`, `test_auth_refresh.py`, `test_auth_me.py`, `test_auth_change.py`, `test_auth_reset.py` — 9 tests green. /auth/me asserts user_id absent + uid present (`tests/test_auth_me.py:68`). |
| 2 | User can create/list/revoke API keys | VERIFIED | 5 /keys endpoints mounted; `controllers/keys.py:20` `APIRouter(prefix="/keys")`. `ApiKeyService.create` returns `(api_key, raw_plaintext)`; `ApiKeyService.delete` does soft-delete (`api_key.deleted_at = now()` at line 130). Security invariant verified live: `ApiKeyItem.model_fields` has `key_prefix` but neither `key` nor `key_hash`; `ApiKeyCreateData.model_fields == {"key", "item"}`. Tests `test_keys.py::test_create_returns_plaintext_once`, `test_keys.py::test_list_no_secrets`, `test_api_key_service.py::test_delete_is_soft` — all green. |
| 3 | User can query balance, transaction history, and usage statistics | VERIFIED | 8 /billing endpoints mounted; `controllers/billing.py:36` `APIRouter(prefix="/billing")`. `BalanceResponseData.available_balance` `@computed_field` verified live (`balance=1000, frozen_amount=100 → available_balance=900`). `MAX_BILLING_RANGE_DAYS = 90` enforced via `ListParams.validate_time_range` (`_build_list_params` at lines 43-64). 14 `for_update=True` call sites across `balance_service.py` (11) + `voucher_service.py` (3) preserve SELECT FOR UPDATE row locking. Voucher idempotency: `billing_repo.exists_by_ref(tx_type=VOUCHER_REDEEM, ref_type='voucher_code', ref_id=str(code.id))` at `voucher_service.py:169`. Tests `test_billing_balance.py`, `test_billing_tx.py`, `test_voucher.py::test_redeem_idempotent`, `test_topup.py`, `test_usage.py::test_range_capped`, `test_usage_stat_service.py::test_granularity_switch_at_48h` — all green. |
| 4 | Public model catalog endpoint returns available models | VERIFIED | 4 model catalog endpoints mounted (`/model-vendors`, `/models/categories`, `/models`, `/models/{slug}`); `controllers/model_catalog.py:27` `APIRouter(tags=["model-catalog"])`. `ModelCatalogReadService` (D-07 class name, NOT `ModelCatalogService`) uses `cache_get_or_fetch` with `mc:` prefix, TTLs 300/300/120/300. `active_only=True` hardcoded at every repository call (4 sites). Slug pattern `^[a-z0-9][a-z0-9._-]*$` enforced at route level (`controllers/model_catalog.py:88`). Tests `test_model_catalog.py::test_cache_hits`, `test_filter`, `test_404` — all green. No HTTP gateway: `grep "model_catalog_gateway|httpx|admin-service"` in both files returns 0. |
| 5 | Email service sends verification and password reset emails | VERIFIED (enqueue path) | `EmailService.send_verification_code` (`email_service.py:53-98`) is a staticmethod class (Pitfall 4 — no module-level singleton). Writes verification code row, commits, then `pool.enqueue_job(_JOB_SEND_VERIFICATION_EMAIL, ...)` (D-02). ARQ worker registered at lifespan priority=40 (`main.py:135-136`). `_JOB_SEND_VERIFICATION_EMAIL == "send_verification_email" == send_verification_email.__name__` (Pitfall 9). Worker functions list contains 5 entries: 4 cron jobs + send_verification_email. SMTP delivery itself runs inside `_send_smtp_sync` (jobs.py) inside the worker process. Tests `test_email_send.py` (3 tests) + `test_email_verify.py` (2 tests) — all green. End-to-end SMTP delivery awaits human verification (mailbox receipt). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `services/api-service/api_service/controllers/auth.py` | 10 /auth/* endpoints + cookie helpers + 用户标识规范 | VERIFIED | 403 lines, `router = APIRouter(tags=["认证"])`, 10 endpoint paths confirmed via FastAPI introspection. `USER_COOKIE_PATH = "/"` preserved (Pitfall 6). `_set_auth_cookies` / `_clear_auth_cookies` defined. `BillingRepository.stat_get_user_tpm_last_minute` used at /auth/me (line 296). `settings.DEFAULT_USER_RPM` at line 298 (D-09). No `system_settings_gateway`, no `get_db_session`. |
| `services/api-service/api_service/controllers/keys.py` | 5 /keys endpoints + plaintext-once on create + soft-delete | VERIFIED | 106 lines, `router = APIRouter(prefix="/keys", tags=["keys"])`. POST returns `{"key": raw_key, "item": ApiKeyItem.model_validate(key)}` — plaintext exposed once. DELETE → `ApiKeyService.delete` (soft). All endpoints `Depends(require_active_user)`. |
| `services/api-service/api_service/controllers/billing.py` | 8 /billing endpoints + 90-day cap + key-ownership pre-check | VERIFIED | 340 lines, `router = APIRouter(prefix="/billing", tags=["billing"])`. `MAX_BILLING_RANGE_DAYS = 90` at line 40. `ApiKeyService.verify_key_ownership` called on every endpoint accepting `api_key_id`. `ApiCallLogItem.from_orm_instance` used in usage/logs. |
| `services/api-service/api_service/controllers/model_catalog.py` | 4 public endpoints (no auth) + slug regex | VERIFIED | 97 lines, `router = APIRouter(tags=["model-catalog"])`. No `Depends(require_active_user)` (public). Slug pattern `^[a-z0-9][a-z0-9._-]*$` + max_length=120 on Path param. Replaces user-service HTTP gateway with direct service call. |
| `services/api-service/api_service/services/auth_service.py` | AuthService with register/login/logout/refresh_access_token/change_password/reset_password/verify_email + session helpers + D-09 + D-11 | VERIFIED | Imports `settings.DEFAULT_USER_RPM` at line 101 (D-09 — no `system_settings_gateway`). UserRepository session method renames applied: `get_session_by_token_jti`, `list_active_sessions_for_user`, `revoke_session`, `add_session`. Refresh-token rotation preserved verbatim (lines 244-247). |
| `services/api-service/api_service/services/email_service.py` | EmailService staticmethod class + D-02 ARQ enqueue + D-11 inner commit | VERIFIED | 156 lines. No `__init__`, no module-level `email_service = EmailService()` (Pitfall 4 — `grep -E "^email_service\s*=" ` returns 0). `pool.enqueue_job(_JOB_SEND_VERIFICATION_EMAIL, ...)` at line 96 (D-02). D-11 marker comment + inner `await db.commit()` at lines 141-147. |
| `services/api-service/api_service/services/api_key_service.py` | ApiKeyService with create/list/update/disable/delete/verify_key_ownership/validate_by_hash/_refresh_status + soft delete | VERIFIED | 197 lines. `delete` at lines 127-131 sets `api_key.deleted_at = now()` (soft); never calls `db.delete`. `create` returns `(api_key, raw_key)` tuple. `_refresh_status` branches preserved. |
| `services/api-service/api_service/services/balance_service.py` | BalanceService with all 7 wallet-mutation methods + SELECT FOR UPDATE + ref_id idempotency | VERIFIED | 11 `for_update=True` call sites confirmed by grep. `BillingRepository.add_tx` + `exists_by_ref` used (no `BalanceTxRepository` / `TopupOrderRepository` references). All wallet mutations: consume_for_call_log, freeze, settle, refund, topup, redeem_code (delegate), admin_adjust. |
| `services/api-service/api_service/services/voucher_service.py` | VoucherService with normalize_code + redeem (ref_id idempotency + for_update lock) | VERIFIED | `normalize_code = raw.strip().lower()` (Pitfall 10). `VoucherRepository` class name used (Phase 3 rename). 3 `for_update=True` sites. `exists_by_ref` short-circuit before balance mutation. |
| `services/api-service/api_service/services/topup_order_service.py` | TopupOrderService with BillingRepository.topup_* routing | VERIFIED | `_generate_order_no` returns "TP" + YYYYMMDD + 8 chars. All `BillingRepository.topup_*` call sites use renamed methods. |
| `services/api-service/api_service/services/usage_stat_service.py` | UsageStatService with 9 stat_* call sites + 48h granularity switch + no double-filter | VERIFIED | All `BillingRepository.stat_*` call sites confirmed (no `UsageStatRepository` references). Pitfall 8 honored: no service-layer `error_code='invalid_model'` filter. 48h granularity branch present. |
| `services/api-service/api_service/services/model_catalog_service.py` | ModelCatalogReadService (D-07 class name) + cache_get_or_fetch + active_only=True | VERIFIED | Class name `ModelCatalogReadService` (D-07). 4 `cache_get_or_fetch` sites. 4 `active_only=True` sites. Cache constants match source gateway: `mc:` prefix, TTLs 300/300/120/300. TODO(phase-5) marker for D-05 deferral. No `httpx` / `model_catalog_gateway` / `admin-service` references. |
| `services/api-service/api_service/schemas/auth.py` | 16 request/response models + email/password validators + uid only (no user_id) | VERIFIED | All response data classes (`UserData`, `UserInfoResponseData`, `RegisterResponseData`) confirmed to lack `user_id` field via runtime inspection. 用户标识规范 enforced. |
| `services/api-service/api_service/schemas/keys.py` | ApiKeyItem (key_prefix only) + ApiKeyCreateData (plaintext key once) | VERIFIED | `ApiKeyItem.model_fields` has `key_prefix` but neither `key` nor `key_hash`. `ApiKeyCreateData.model_fields == {"key", "item"}`. |
| `services/api-service/api_service/schemas/billing.py` | BalanceResponseData with available_balance computed_field | VERIFIED | Live constructor: `BalanceResponseData(balance=1000, frozen_amount=100, ...).model_dump()["available_balance"] == 900`. `UsageAnalyticsRange = Literal["8h","24h","7d","30d"]`. `ApiCallLogItem.from_orm_instance` classmethod present. |
| `services/api-service/api_service/schemas/model_catalog.py` | 6 read-only classes (NO admin write schemas) | VERIFIED | 6 classes export; no `ModelVendorCreate` / `ModelVendorUpdate` / `SupportedModelCreate` / `AdminBaseResponse` (D-06 — Phase 5 territory). |
| `services/api-service/api_service/schemas/common.py` | ApiResponse[T] + DateTimeModel + AuthBaseResponse + AuthErrorResponse | VERIFIED | `list(data.items())` copy in DateTimeModel.serialize_model preserved (Pitfall 7). |
| `services/api-service/api_service/core/arq_pool.py` | init_arq_pool / close_arq_pool / get_arq_pool + WORKER_QUEUE_REDIS_URL parser | VERIFIED | All 4 functions present. Lifespan registered at priority=40 (`main.py:135-136`). |
| `services/api-service/api_service/core/worker.py` | WorkerSettings runnable via `arq api_service.core.worker.WorkerSettings` | VERIFIED | `WorkerSettings` class defined; `setattr` loop applies `get_worker_settings_kwargs()`. Worker boot path tested manually per 04-02 SUMMARY. |
| `services/api-service/api_service/core/jobs.py` | send_verification_email + 4 cron jobs + get_worker_settings_kwargs | VERIFIED | Live inspection: `functions == [aggregate_usage_stats, cleanup_expired_verification_codes, cleanup_expired_sessions, reconcile_balance_ledger, send_verification_email]`. `cron_jobs` has 4 entries. `_JOB_SEND_VERIFICATION_EMAIL == send_verification_email.__name__` (Pitfall 9). |
| `services/api-service/api_service/core/policies.py` | require_active_user dependency | VERIFIED | Callable; used by `controllers/auth.py` (/auth/me, change-password), `controllers/keys.py` (all 5), `controllers/billing.py` (all 8). |
| `services/api-service/api_service/core/router.py` | api_router mounts auth + keys + billing + model_catalog | VERIFIED | All 4 include_router calls present. Combined `app.routes` count under `/api/v1/*` = 27 (10+5+8+4) via individual router introspection. |
| 23 test files in `services/api-service/tests/` | covers T-04-01 .. T-04-23 | VERIFIED | 115 tests pass via `pytest tests/ -q --ignore=tests/test_health.py`. All 35 Phase-4 specific tests pass verbose. Deferred: `test_health.py::test_ready_returns_200` (pre-existing — documented in deferred-items.md). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `main.py` | `core/arq_pool.py` | `registry.register("arq_pool", ..., priority=40)` | WIRED | `main.py:135-136`. Priority 40 after Redis(30)+DB(20). |
| `services/email_service.py` | `core/arq_pool.py` + `core/jobs.send_verification_email` | `pool.enqueue_job("send_verification_email", email, code, purpose)` | WIRED | `email_service.py:96`. Job name string equals function `__name__`. |
| `core/jobs.py` | `core/worker.py` | `get_worker_settings_kwargs()["functions"]` | WIRED | Live: functions list has 5 entries including send_verification_email. |
| `controllers/auth.py` | `services/auth_service.py` | `AuthService.register/login/logout/refresh_access_token/change_password/reset_password/verify_email` | WIRED | All 10 endpoints call corresponding AuthService methods. |
| `controllers/auth.py` | `repositories/billing_repository.py` | `BillingRepository.stat_get_user_tpm_last_minute` at /auth/me | WIRED | `auth.py:296`. |
| `controllers/keys.py` | `services/api_key_service.py` | `ApiKeyService.list/create/update/disable/delete` | WIRED | 5 endpoints, 5 service methods. |
| `controllers/billing.py` | `services/{balance,topup_order,voucher,usage_stat}_service.py` | `BalanceService` / `TopupOrderService` / `VoucherService` / `UsageStatService` | WIRED | 8 endpoints distributed across 4 services. |
| `controllers/billing.py` | `services/api_key_service.py` | `ApiKeyService.verify_key_ownership` for `api_key_id` filter | WIRED | `billing.py:229, 264, 308`. |
| `controllers/model_catalog.py` | `services/model_catalog_service.py` | `ModelCatalogReadService.list_vendors/list_categories/list_models/get_model_by_slug` | WIRED | 4 endpoints, 4 service methods. |
| `services/model_catalog_service.py` | `common/infra/cache.py` | `cache_get_or_fetch(cache_key, _fetch, ttl)` | WIRED | 4 sites in service file. |
| `services/balance_service.py` | `repositories/billing_repository.py` | `BillingRepository.add_tx / exists_by_ref / list_tx_for_user / topup_get_for_user_by_order_no` | WIRED | 11+ call sites; no deleted `BalanceTxRepository` references. |
| `services/balance_service.py` | `repositories/user_repository.py` | `UserRepository.get_by_id(user_id, for_update=True)` | WIRED | 11 `for_update=True` call sites — every wallet mutation. |
| `services/voucher_service.py` | `repositories/voucher_repository.py` + `billing_repository.py` | `VoucherRepository` (Phase 3 rename) + `BillingRepository.exists_by_ref`/`add_tx` | WIRED | Idempotency: `voucher_service.py:169` checks `exists_by_ref` before `add_tx`. |
| `core/router.py` | 4 controllers | `api_router.include_router(auth/keys/billing/model_catalog.router)` | WIRED | All 4 include_router calls present at `core/router.py:12-15`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|----- ---|
| /auth/me UserInfoResponseData | current_tpm | `BillingRepository(db).stat_get_user_tpm_last_minute(user_id)` | Yes (DB query on api_call_logs) | FLOWING |
| /auth/me UserInfoResponseData | default_rpm | `settings.DEFAULT_USER_RPM` | Yes (config constant, value=20) | FLOWING |
| /keys list response | keys | `ApiKeyRepository.list_for_user(user_id)` | Yes (DB query on user_api_keys with `deleted_at IS NULL`) | FLOWING |
| /billing/balance BalanceResponseData | balance/frozen_amount/used_amount/total_requests/total_tokens | `BalanceService.get_balance(user_id)` → DB query | Yes | FLOWING |
| /billing/transactions PaginatedResponse | items | `BalanceService.list_transactions` → `BillingRepository.list_tx_for_user` (DB query) | Yes | FLOWING |
| /billing/usage list | items | `UsageStatService.get_user_stats` → `BillingRepository.stat_get_user_stats` (DB query) | Yes | FLOWING |
| /model-vendors payload | items | `ModelVendorRepository.list_vendors(active_only=True)` via `cache_get_or_fetch` | Yes (DB on cache miss, Redis on hit) | FLOWING |
| /models payload | items | `ModelCatalogRepository.list_models(active_only=True)` via `cache_get_or_fetch` | Yes | FLOWING |
| /models/{slug} payload | model dict | `ModelCatalogRepository.get_by_slug(slug, active_only=True)` | Yes (404 on None) | FLOWING |
| /auth/send-email-code | verification code | `EmailVerificationCode` row + ARQ enqueue → worker → SMTP | Real-data path present; **worker-side SMTP delivery requires human verification** | FLOWING (in process); HUMAN_VERIFY (mailbox receipt) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 4 test suite passes (115 tests, excludes deferred health test) | `cd services/api-service && pytest tests/ -q --ignore=tests/test_health.py` | `115 passed, 4 warnings in 0.92s` | PASS |
| All 10 /auth/* + 5 /keys + 8 /billing + 4 model-catalog paths registered | `python -c "from controllers import auth, keys, billing, model_catalog; print counts"` | 10/5/8/4 — total 27 | PASS |
| BalanceResponseData.available_balance computed correctly | `python -c "BalanceResponseData(balance=1000, frozen_amount=100, ...).model_dump()"` | `available_balance == 900` | PASS |
| ApiKeyItem hides plaintext + hash (security invariant) | `python -c "ApiKeyItem.model_fields"` | `key_prefix` present; `key`/`key_hash` absent | PASS |
| user_id absent from all auth response schemas (用户标识规范) | `python -c "for cls in [UserData, UserInfoResponseData, RegisterResponseData]: assert 'user_id' not in cls.model_fields"` | OK | PASS |
| ARQ worker functions list correct (5 entries: 4 crons + 1 email job) | `python -c "kw = get_worker_settings_kwargs(); print [f.__name__ for f in kw['functions']]"` | `['aggregate_usage_stats', 'cleanup_expired_verification_codes', 'cleanup_expired_sessions', 'reconcile_balance_ledger', 'send_verification_email']` | PASS |
| /ready ARQ check (CR-03) | `grep "arq" services/api-service/api_service/main.py` (looking for arq probe in /ready) | Not present — `/ready` checks DB + Redis db/0 + Cache Redis db/2 only | FAIL (informational — see human verification) |
| Deferred pre-existing health probe failure reproducible | `pytest tests/test_health.py -v` | `1 failed: assert 503 == 200` — pre-existing per `deferred-items.md`, not caused by Phase 4 | SKIP |

### Probe Execution

No `scripts/*/tests/probe-*.sh` discovered for this phase. Probe execution not applicable.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| USER-01 | 04-01 (declared) + 04-01 (addressed) | 用户注册/登录/登出/刷新 token 端点正常工作 | SATISFIED | 10 /auth/* endpoints mounted; 9 integration tests green; cookie-based JWT + HttpOnly + SameSite + refresh rotation. Edge cases (logout exception path, refresh TOCTOU window) flagged for human verification. |
| USER-04 | 04-02 (declared) + 04-02 (addressed) | 余额查询/交易记录/用量统计端点正常工作 | SATISFIED | 8 /billing endpoints mounted; 8 integration tests + 4 unit tests; `available_balance` computed; 90-day cap; voucher idempotency; 48h granularity switch. Topup-orders create is admin-only at source (deviation documented in 04-02 SUMMARY). |
| USER-05 | 04-03 (declared) + 04-03 (addressed) | 模型目录公开查询端点正常工作 | SATISFIED | 4 public model catalog endpoints; cache_get_or_fetch with mc:* keys + source-matching TTLs; active_only=True filter; slug regex. 3 integration tests green. HTTP gateway eliminated (direct repo calls). |
| USER-06 | 04-01 (declared) + 04-01 (addressed) | 邮件服务（注册验证、密码重置）正常工作 | SATISFIED (enqueue path) — HUMAN_VERIFY (SMTP delivery) | ARQ enqueue verified by `test_email_send.py::test_enqueues_arq`; D-11 inner commit verified by `test_email_verify.py::test_error_count`. Worker-side SMTP delivery (`_send_smtp_sync`) requires real mailbox test — listed in human_verification. |

**Note:** USER-03 (API Key CRUD) is mapped to Phase 3 in `REQUIREMENTS.md:115`, but the /keys controller endpoints are actually delivered in Phase 4-02. The 5 /keys endpoints satisfy USER-03 in addition to USER-04 — 04-02 SUMMARY: "the API-key CRUD half of USER-03 is also satisfied here". No orphaned requirements; coverage is additive.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `controllers/auth.py` | 243-244 | `except Exception: logger.exception(...)` — NO re-raise on logout failure | Warning (CR-01 from REVIEW) | Logout silently succeeds when AuthService.logout fails; session row remains active. **Ported verbatim from user-service source per D-03 — see human verification.** |
| `services/auth_service.py` | 244-247 | Refresh-token rotation TOCTOU — partial-update window | Warning (CR-02 from REVIEW) | Client cookies cleared while server-side session may still be valid if exception raised between token_jti set and commit. **Source-preserved pattern — see human verification.** |
| `main.py` | 196-220 | `/ready` does not check ARQ Redis db/1 | Warning (CR-03 from REVIEW) | K8s probe can mark pod ready while /auth/send-email-code will fail. **Deployment-level concern — see human verification.** |
| `core/config.py` | 58-59 | `MIN_TOPUP_AMOUNT` / `MAX_TOPUP_AMOUNT` declared but never referenced | Info (WR-04 from REVIEW) | Dead config — Phase 4 user-facing topup is read-only. **Phase 5 admin POST will need to wire these — see human verification.** |
| `controllers/auth.py` | 114, 153, 196 | `request.client.host` taken raw (no X-Forwarded-For handling) | Info (WR-06 from REVIEW) | IP audit / IP allowlist will see proxy IP, not user IP, when deployed behind reverse proxy. **Source-preserved pattern.** |
| `schemas/auth.py` | 18, 123-126, 194-200 | password `max_length=72` enforced in characters, not bytes (bcrypt 72-byte limit only checked on LoginRequest) | Info (WR-01 from REVIEW) | Multi-byte (e.g. Chinese) passwords may silently mishash on register/change/reset. **Source-preserved pattern.** |
| `services/auth_service.py` | 58-66 | `_get_dummy_hash` lazy init without async lock | Info (WR-09 from REVIEW) | Timing equalizer goal partially defeated by computation cost on first concurrent miss. **Source-preserved pattern.** |
| `controllers/model_catalog.py` | 30-96 | No `response_model` declared on JSONResponse-returning endpoints | Info (WR-07 from REVIEW) | OpenAPI docs lack response schemas. **Source-preserved pattern.** |
| `services/auth_service.py:5` + `controllers/auth.py:8` | Comments | Docstring references to deprecated `UsageStatRepository` and `SessionRepository` class names | Info | Documentation-only references; no executable code (Phase 3 D-04 rename respected in actual code). |

### Gaps Summary

No goal-blocking gaps identified. The phase goal (feature parity with user-service) is materially achieved across all 5 Roadmap Success Criteria. Every declared must-have is verified, every required artifact exists at substantive content level (not stub), every key link is wired, data flows from real DB queries (not hardcoded), and 115/115 Phase 4 tests pass.

**However**, the goal contains the word "identically" — a behavioral claim that has 6 components requiring human attestation:

1. **CR-01 / CR-02 / CR-03 from 04-REVIEW** — three real code patterns, but all three are present in the user-service source per D-03 "1:1 source parity". The owner must decide whether "identically" means preserving these pre-existing hazards or fixing them in Phase 4.
2. **End-to-end SMTP delivery (USER-06)** — automated tests verify ARQ enqueue, not worker-side send + mailbox receipt.
3. **Side-by-side parity validation** — the standard pre-cutover check (DEPL-03) requires running user-service and api-service in parallel and replaying traffic. Not in Phase 4 automated scope.
4. **MIN/MAX_TOPUP_AMOUNT dead-config disposition** — informational, but owner should decide before Phase 5 wires admin topup endpoint.

These six items appear in the `human_verification` block above and must be addressed in HUMAN-UAT.md or equivalent before Phase 10 cutover.

---

_Verified: 2026-05-19T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
