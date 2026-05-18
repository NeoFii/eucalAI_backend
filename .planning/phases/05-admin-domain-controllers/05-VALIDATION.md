---
phase: 5
slug: admin-domain-controllers
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-19
revised: 2026-05-19
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
>
> **Revision 2026-05-19 (plan-checker Warning 7):** Task IDs back-filled across all rows. Frontmatter `status` advanced from `draft` to `ready`; `nyquist_compliant` set to `true` (every test row has an automated command); `wave_0_complete` remains `false` until the test scaffolds are actually written during execute-phase Wave 0.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23+ |
| **Config file** | `services/api-service/pyproject.toml` `[tool.pytest.ini_options]` (Phase 4 04-01 installed; `asyncio_mode = "auto"`) |
| **Quick run command** | `cd services/api-service && pytest tests/ -x -q -k admin` |
| **Full suite command** | `cd services/api-service && pytest tests/ --cov=api_service --cov-report=term-missing` |
| **Estimated runtime** | ~15–25 seconds (admin-only); ~45–60 seconds (full suite with coverage) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q -k "admin and <module>"` (module-scoped, ~2–5s)
- **After every plan wave:** Run `pytest tests/ -x -q -k admin` (~15–20s)
- **Before `/gsd:verify-work`:** Full suite with `--cov-fail-under=80` must be green
- **Max feedback latency:** 25 seconds (admin-only test run)

---

## Per-Task Verification Map

Test files all need creation in Wave 0 (no Phase 5 test files exist yet). Phase 4 already created the `tests/` directory and `conftest.py`; Phase 5 extends with admin-specific fixtures (`mock_admin`, `mock_super_admin`, `mock_cache_redis`, `mock_internal_client`).

Task ID format: `05-{plan}-T{task}` where `{task}` is `1a`/`1b`/`2`/`3` (Plan 05-01 has a split first task per plan-checker Warning 4) or `0`/`1`/`2`/`3` (Plan 05-03 added a Wave 0 pre-flight per plan-checker Warning 6 Option B).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-T2 | 01 | 0 | ADMIN-01 | T-5-01 | Admin login sets `admin_access_token` httpOnly cookie | integration | `pytest tests/test_admin_auth.py::test_login_sets_cookies -x` | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 0 | ADMIN-01 | T-5-02 | Login locks account after 5 failures (`login_locked_until` set) | integration | `pytest tests/test_admin_auth.py::test_lockout -x` | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 0 | ADMIN-01 | T-5-03 | Admin logout blacklists JTI in Redis | integration | `pytest tests/test_admin_auth.py::test_logout_blacklists -x` | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 0 | ADMIN-01 | — | Admin refresh rotates both access + refresh tokens | integration | `pytest tests/test_admin_auth.py::test_refresh_rotates -x` | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 0 | ADMIN-01 | T-5-04 | Change-password invalidates all current tokens | integration | `pytest tests/test_admin_auth.py::test_change_password_invalidates -x` | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 0 | ADMIN-12 | — | Bootstrap creates super-admin on fresh DB | integration | `pytest tests/test_admin_bootstrap.py::test_first_time_create -x` | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 0 | ADMIN-12 | — | Bootstrap is idempotent on subsequent starts | integration | `pytest tests/test_admin_bootstrap.py::test_idempotent -x` | ❌ W0 | ⬜ pending |
| 05-01-T2 | 01 | 0 | ADMIN-12 | — | Respects `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=False` | integration | `pytest tests/test_admin_bootstrap.py::test_optional -x` | ❌ W0 | ⬜ pending |
| 05-01-T1a | 01 | 0 | (D-04) | — | Phase 4 imports resolve from `api_service.common.schemas` after hoist | shape test | `pytest tests/test_schemas_hoist.py::test_phase4_imports_rewritten -x` | ❌ W0 | ⬜ pending |
| 05-01-T1b | 01 | 0 | (D-04) | — | HMAC sender + admin exceptions + admin policies + 5 settings keys importable | shape test | `pytest tests/test_schemas_hoist.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 0 | ADMIN-04 | T-5-05 | Pool create writes encrypted `api_key_enc` (no plaintext in DB) | integration | `pytest tests/test_admin_pools.py::test_create_encrypts_key -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 0 | ADMIN-04 | — | Pool model add updates `pool_model_configs` | integration | `pytest tests/test_admin_pools.py::test_add_model -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 0 | ADMIN-04 | — | Pool balance check decrypts + calls upstream | integration | `pytest tests/test_admin_pools.py::test_check_balances -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 0 | ADMIN-04 | — | Pool `_extract_balance` returns micro-yuan for `total_remain` shape | unit | `pytest tests/test_pool_service.py::test_extract_balance_total_remain -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 0 | ADMIN-04 | — | Pool `_extract_balance` returns micro-yuan for `points` shape | unit | `pytest tests/test_pool_service.py::test_extract_balance_points -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 0 | ADMIN-04 | — | Pool `_extract_balance` returns micro-yuan for `balance` shape | unit | `pytest tests/test_pool_service.py::test_extract_balance_balance -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 0 | ADMIN-04 | — | Pool `_extract_balance` returns micro-yuan for `remain` shape | unit | `pytest tests/test_pool_service.py::test_extract_balance_remain -x` | ❌ W0 | ⬜ pending |
| 05-02-T1 | 02 | 0 | ADMIN-04 | — | Pool `_extract_balance` returns 0 for unknown response shape | unit | `pytest tests/test_pool_service.py::test_extract_balance_unknown_returns_zero -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | ADMIN-05 | — | Model vendor create invalidates `mc:*` cache (D-05) | integration | `pytest tests/test_admin_model_catalog.py::test_create_vendor_invalidates_cache -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | ADMIN-05 | — | Model archive sets `is_active=False` (soft delete) | unit | `pytest tests/test_model_catalog_service.py::test_archive_soft_deletes -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | (D-05) | — | `mc:*` SCAN+DEL invocation on every model_catalog admin write | integration | `pytest tests/test_admin_model_catalog.py::test_invalidates_on_all_writes -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | ADMIN-06 | — | Routing setting update bumps `routing_config:version` (D-06) | integration | `pytest tests/test_admin_routing_settings.py::test_update_bumps_version -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | ADMIN-06 | — | Tier model validation rejects missing pool coverage | unit | `pytest tests/test_routing_setting_service.py::test_validate_rejects_unavailable -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | ADMIN-06 | — | Tier model validation rejects missing routing_slug | unit | `pytest tests/test_routing_setting_service.py::test_validate_rejects_no_routing_slug -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | (Pitfall 4) | — | `resolve_for_internal` NOT ported (out of scope) | shape test | `pytest tests/test_routing_setting_service.py::test_resolve_for_internal_not_present -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | (D-06) | — | `routing_config:version` INCR after every routing_settings write | integration | `pytest tests/test_admin_routing_settings.py::test_version_incremented -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | ADMIN-08 | — | Admin-on-admin create raises AdminConflictException on duplicate email | unit | `pytest tests/test_admin_management.py::test_create_admin_email_conflict -x` | ❌ W0 | ⬜ pending |
| 05-02-T2 | 02 | 0 | (Pitfall 3) | — | `AdminAccountService` exists (rename from `AdminManagementService` complete) | shape test | `pytest tests/test_admin_management.py::test_account_service_renamed -x` | ❌ W0 | ⬜ pending |
| 05-02-T3 | 02 | 0 | ADMIN-08 | — | Audit log meta returns categories + action_labels | integration | `pytest tests/test_admin_audit.py::test_meta -x` | ❌ W0 | ⬜ pending |
| 05-02-T3 | 02 | 0 | ADMIN-08 | — | Audit list filters by category + actor_uid | integration | `pytest tests/test_admin_audit.py::test_list_filters -x` | ❌ W0 | ⬜ pending |
| 05-02-T3 | 02 | 0 | ADMIN-08 | — | Action label update invalidates module cache | unit | `pytest tests/test_audit_service.py::test_update_label_invalidates_cache -x` | ❌ W0 | ⬜ pending |
| 05-02-T3 | 02 | 0 | ADMIN-08 | — | Audit endpoints reject non-super-admin (require_super_admin guard) | integration | `pytest tests/test_admin_audit.py::test_audit_under_super_admin_guard -x` | ❌ W0 | ⬜ pending |
| 05-03-T0 | 03 | 0 | (cross-phase) | — | Phase 4 service classes (VoucherService, BalanceService, ApiKeyService, UsageStatService, AuthService) importable | gate | `python -c "from api_service.services.voucher_service import VoucherService; from api_service.services.balance_service import BalanceService; from api_service.services.api_key_service import ApiKeyService; from api_service.services.usage_stat_service import UsageStatService; from api_service.services.auth_service import AuthService"` | n/a | ⬜ pending |
| 05-03-T1 | 03 | 0 | ADMIN-03 | T-5-06 | `/api/v1/admin/users` lists users with zero HTTP proxy calls | integration | `pytest tests/test_admin_users.py::test_list_no_http -x` | ❌ W0 | ⬜ pending |
| 05-03-T1 | 03 | 0 | ADMIN-03 | — | Admin topup writes audit row + balance row in same transaction | integration | `pytest tests/test_admin_users.py::test_topup_atomic_with_audit -x` | ❌ W0 | ⬜ pending |
| 05-03-T1 | 03 | 0 | ADMIN-03 | T-5-07 | Reset-password revokes all user sessions | integration | `pytest tests/test_admin_users.py::test_reset_password_revokes_sessions -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 0 | ADMIN-07 | — | Dashboard summary returns int fields from direct repo call | integration | `pytest tests/test_admin_dashboard.py::test_summary_no_http -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 0 | ADMIN-07 | — | Dashboard rpm-trend respects `bucket_seconds` | integration | `pytest tests/test_admin_dashboard.py::test_rpm_trend_bucketing -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 0 | ADMIN-09 | — | Voucher generate batch writes N codes + 1 audit row | integration | `pytest tests/test_admin_vouchers.py::test_generate_batch -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 0 | ADMIN-09 | — | Voucher disable sets status to inactive | integration | `pytest tests/test_admin_vouchers.py::test_disable -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 0 | ADMIN-10 | — | Route monitor list paginates from `call_logs` | integration | `pytest tests/test_admin_route_monitor.py::test_list -x` | ❌ W0 | ⬜ pending |
| 05-03-T2 | 03 | 0 | ADMIN-10 | — | Route monitor compare returns siblings by `input_hash` | integration | `pytest tests/test_admin_route_monitor.py::test_compare -x` | ❌ W0 | ⬜ pending |
| 05-03-T3 | 03 | 0 | ADMIN-11 | — | Service logs returns local RingBuffer entries | integration | `pytest tests/test_admin_service_logs.py::test_local_only -x` | ❌ W0 | ⬜ pending |
| 05-03-T3 | 03 | 0 | ADMIN-11 | T-5-08 | Service logs degrades gracefully when inference unreachable | integration | `pytest tests/test_admin_service_logs.py::test_partial_on_failure -x` | ❌ W0 | ⬜ pending |
| 05-03-T3 | 03 | 0 | (D-03) | — | `_REMOTE_SERVICES` contains exactly one entry — only inference-service | shape test | `pytest tests/test_admin_service_logs.py::test_remote_services_only_inference -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Test files all need creation. Phase 5 extends Phase 4's `tests/` directory and `conftest.py`. The list below is exhaustive for the 3-plan structure post-revision (Plan 05-01 split into Tasks 1a + 1b + 2; Plan 05-03 gained a pre-flight Task 0).

- [ ] `tests/test_admin_auth.py` — covers ADMIN-01 (login/logout/refresh/me/change-password + lockout) — Plan 05-01 Task 2
- [ ] `tests/test_admin_bootstrap.py` — covers ADMIN-12 (first-time create + idempotent + optional flag) — Plan 05-01 Task 2
- [ ] `tests/test_schemas_hoist.py` — shape test for D-04 import rewrite (Phase 4 imports must resolve from new location) + HMAC sender / admin exceptions / admin policies / 5 new settings keys importable — Plan 05-01 Task 1a creates the file with 4 tests; Plan 05-01 Task 1b appends 5 more tests (9 tests total)
- [ ] `tests/test_admin_users.py` — covers ADMIN-03 (14 endpoint paths; no HTTP proxy) — Plan 05-03 Task 1
- [ ] `tests/test_admin_pools.py` — covers ADMIN-04 (16 endpoints; provider key encryption; upstream HTTP mock) — Plan 05-02 Task 1
- [ ] `tests/test_admin_model_catalog.py` — covers ADMIN-05 + D-05 cache invalidation (SCAN+DEL on every write) — Plan 05-02 Task 2
- [ ] `tests/test_admin_routing_settings.py` — covers ADMIN-06 + D-06 INCR (`routing_config:version`) — Plan 05-02 Task 2
- [ ] `tests/test_admin_dashboard.py` — covers ADMIN-07 — Plan 05-03 Task 2
- [ ] `tests/test_admin_audit.py` — covers ADMIN-08 — Plan 05-02 Task 3
- [ ] `tests/test_admin_vouchers.py` — covers ADMIN-09 — Plan 05-03 Task 2
- [ ] `tests/test_admin_route_monitor.py` — covers ADMIN-10 — Plan 05-03 Task 2
- [ ] `tests/test_admin_service_logs.py` — covers ADMIN-11 + D-03 (RingBuffer + inference HTTP) — Plan 05-03 Task 3
- [ ] `tests/test_admin_management.py` — admin-on-admin account CRUD (ADMIN-08 adjacent) — Plan 05-02 Task 2
- [ ] `tests/test_pool_service.py` — unit (parameterized: 4 provider balance response shapes per RESEARCH Pitfall 9 + 1 unknown-returns-zero) — Plan 05-02 Task 1
- [ ] `tests/test_audit_service.py` — unit (module cache invalidation per ADMIN-08) — Plan 05-02 Task 3
- [ ] `tests/test_routing_setting_service.py` — unit (validate_tier_model_coverage logic + resolve_for_internal absence) — Plan 05-02 Task 2
- [ ] `tests/test_model_catalog_service.py` — unit (soft-delete archive) — Plan 05-02 Task 2
- [ ] `tests/conftest.py` — **EXTEND** Phase 4's: add `mock_admin`, `mock_super_admin`, `mock_cache_redis`, `mock_internal_client` fixtures — Plan 05-01 Task 2

**Sequencing note:** every test file is scaffolded ahead of its implementing task within the same plan (RED-then-GREEN). When `workflow.tdd_mode` is enabled, the executor writes the failing test FIRST inside the task body (per the task `<behavior>` block), then the implementation. The Wave 0 list above is therefore advisory — the actual scaffolding happens task-by-task during execute-phase.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Admin frontend can call `/api/v1/admin/auth/login` and read `admin_access_token` cookie from response | ADMIN-01 | Cross-repo end-to-end requires actual admin frontend deployment; CONTEXT D-08 cookie path decision needs browser-side verification of Next.js middleware reading the cookie | After staging deploy: open admin UI in browser → login → DevTools Application tab → confirm `admin_access_token` cookie exists, has `httpOnly=true`, `SameSite=Lax`, `Path=/`, and is sent on subsequent `/api/v1/admin/*` requests |
| Bootstrap super-admin login on a freshly migrated environment | ADMIN-12 | Requires actual ENV vars + fresh DB at deploy time | Stage deploy: set `ADMIN_BOOTSTRAP_USERNAME` + `ADMIN_BOOTSTRAP_PASSWORD` env vars → start api-service → confirm log line "super-admin bootstrap complete" → login via admin UI |
| inference-service `/internal/logs` endpoint reachable from api-service over HMAC (O-3) | ADMIN-11 | Requires both services running with shared HMAC secret in staging; Plan 05-03 Task 3 code-time grep verifies the path constant `INFERENCE_LOGS_PATH` is set to whichever variant inference-service serves today, but the actual reachability test requires both services co-deployed | Staging: `curl -X GET https://api-service/api/v1/admin/service-logs?services=inference-service` with admin token → confirm response includes inference entries (not partial-warning) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (Plan 05-03 Task 0 is a gate; remaining tasks all have automated verify per `verify.plan-structure` check 2026-05-19)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (18 test files + extended conftest.py listed above)
- [x] No watch-mode flags
- [x] Feedback latency < 25s (admin-only quick run)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready (2026-05-19, plan-checker Warning 7 remediation complete). `wave_0_complete` remains `false` — flip to `true` after Wave 0 scaffolding actually runs during execute-phase.
