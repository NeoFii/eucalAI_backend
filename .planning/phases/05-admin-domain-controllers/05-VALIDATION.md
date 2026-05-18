---
phase: 5
slug: admin-domain-controllers
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-19
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

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

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (TBD by planner) | 01 | 0 | ADMIN-01 | T-5-01 | Admin login sets `admin_access_token` httpOnly cookie | integration | `pytest tests/test_admin_auth.py::test_login_sets_cookies -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 01 | 0 | ADMIN-01 | T-5-02 | Login locks account after 5 failures (`login_locked_until` set) | integration | `pytest tests/test_admin_auth.py::test_lockout -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 01 | 0 | ADMIN-01 | T-5-03 | Admin logout blacklists JTI in Redis | integration | `pytest tests/test_admin_auth.py::test_logout_blacklists -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 01 | 0 | ADMIN-01 | — | Admin refresh rotates both access + refresh tokens | integration | `pytest tests/test_admin_auth.py::test_refresh_rotates -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 01 | 0 | ADMIN-01 | T-5-04 | Change-password invalidates all current tokens | integration | `pytest tests/test_admin_auth.py::test_change_password_invalidates -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 01 | 0 | ADMIN-12 | — | Bootstrap creates super-admin on fresh DB | integration | `pytest tests/test_admin_bootstrap.py::test_first_time_create -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 01 | 0 | ADMIN-12 | — | Bootstrap is idempotent on subsequent starts | integration | `pytest tests/test_admin_bootstrap.py::test_idempotent -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 01 | 0 | ADMIN-12 | — | Respects `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=False` | integration | `pytest tests/test_admin_bootstrap.py::test_optional -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 01 | 0 | (D-04) | — | Phase 4 imports resolve from `api_service.common.schemas` after hoist | shape test | `pytest tests/test_schemas_hoist.py::test_phase4_imports_rewritten -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-04 | T-5-05 | Pool create writes encrypted `api_key_enc` (no plaintext in DB) | integration | `pytest tests/test_admin_pools.py::test_create_encrypts_key -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-04 | — | Pool model add updates `pool_model_configs` | integration | `pytest tests/test_admin_pools.py::test_add_model -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-04 | — | Pool balance check decrypts + calls upstream | integration | `pytest tests/test_admin_pools.py::test_check_balances -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-05 | — | Model vendor create invalidates `mc:*` cache (D-05) | integration | `pytest tests/test_admin_model_catalog.py::test_create_vendor_invalidates_cache -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-05 | — | Model archive sets `is_active=False` (soft delete) | unit | `pytest tests/test_model_catalog_service.py::test_archive_soft_deletes -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | (D-05) | — | `mc:*` SCAN+DEL invocation on every model_catalog admin write | integration | `pytest tests/test_admin_model_catalog.py::test_invalidates_on_all_writes -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-06 | — | Routing setting update bumps `routing_config:version` (D-06) | integration | `pytest tests/test_admin_routing_settings.py::test_update_bumps_version -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-06 | — | Tier model validation rejects missing pool coverage | unit | `pytest tests/test_routing_setting_service.py::test_validate_rejects_unavailable -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | (D-06) | — | `routing_config:version` INCR after every routing_settings write | integration | `pytest tests/test_admin_routing_settings.py::test_version_incremented -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-08 | — | Audit log meta returns categories + action_labels | integration | `pytest tests/test_admin_audit.py::test_meta -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-08 | — | Audit list filters by category + actor_uid | integration | `pytest tests/test_admin_audit.py::test_list_filters -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 02 | 0 | ADMIN-08 | — | Action label update invalidates module cache | unit | `pytest tests/test_audit_service.py::test_update_label_invalidates_cache -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-03 | T-5-06 | `/api/v1/admin/users` lists users with zero HTTP proxy calls | integration | `pytest tests/test_admin_users.py::test_list_no_http -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-03 | — | Admin topup writes audit row + balance row in same transaction | integration | `pytest tests/test_admin_users.py::test_topup_atomic_with_audit -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-03 | T-5-07 | Reset-password revokes all user sessions | integration | `pytest tests/test_admin_users.py::test_reset_password_revokes_sessions -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-07 | — | Dashboard summary returns int fields from direct repo call | integration | `pytest tests/test_admin_dashboard.py::test_summary_no_http -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-07 | — | Dashboard rpm-trend respects `bucket_seconds` | integration | `pytest tests/test_admin_dashboard.py::test_rpm_trend_bucketing -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-09 | — | Voucher generate batch writes N codes + 1 audit row | integration | `pytest tests/test_admin_vouchers.py::test_generate_batch -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-09 | — | Voucher disable sets status to inactive | integration | `pytest tests/test_admin_vouchers.py::test_disable -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-10 | — | Route monitor list paginates from `call_logs` | integration | `pytest tests/test_admin_route_monitor.py::test_list -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-10 | — | Route monitor compare returns siblings by `input_hash` | integration | `pytest tests/test_admin_route_monitor.py::test_compare -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-11 | — | Service logs returns local RingBuffer entries | integration | `pytest tests/test_admin_service_logs.py::test_local_only -x` | ❌ W0 | ⬜ pending |
| (TBD by planner) | 03 | 0 | ADMIN-11 | T-5-08 | Service logs degrades gracefully when inference unreachable | integration | `pytest tests/test_admin_service_logs.py::test_partial_on_failure -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Test files all need creation. Phase 5 extends Phase 4's `tests/` directory and `conftest.py`:

- [ ] `tests/test_admin_auth.py` — covers ADMIN-01 (login/logout/refresh/me/change-password + lockout)
- [ ] `tests/test_admin_bootstrap.py` — covers ADMIN-12 (first-time create + idempotent + optional flag)
- [ ] `tests/test_schemas_hoist.py` — shape test for D-04 import rewrite (Phase 4 imports must resolve from new location)
- [ ] `tests/test_admin_users.py` — covers ADMIN-03 (14 endpoint paths; no HTTP proxy)
- [ ] `tests/test_admin_pools.py` — covers ADMIN-04 (16 endpoints; provider key encryption; upstream HTTP mock)
- [ ] `tests/test_admin_model_catalog.py` — covers ADMIN-05 + D-05 cache invalidation (SCAN+DEL on every write)
- [ ] `tests/test_admin_routing_settings.py` — covers ADMIN-06 + D-06 INCR (`routing_config:version`)
- [ ] `tests/test_admin_dashboard.py` — covers ADMIN-07
- [ ] `tests/test_admin_audit.py` — covers ADMIN-08
- [ ] `tests/test_admin_vouchers.py` — covers ADMIN-09
- [ ] `tests/test_admin_route_monitor.py` — covers ADMIN-10
- [ ] `tests/test_admin_service_logs.py` — covers ADMIN-11 + D-03 (RingBuffer + inference HTTP)
- [ ] `tests/test_admin_management.py` — admin-on-admin account CRUD (ADMIN-08 adjacent)
- [ ] `tests/test_pool_service.py` — unit (parameterized: 4 provider balance response shapes per RESEARCH Pitfall 9)
- [ ] `tests/test_audit_service.py` — unit (module cache invalidation per ADMIN-08)
- [ ] `tests/test_routing_setting_service.py` — unit (validate_tier_model_coverage logic)
- [ ] `tests/test_model_catalog_service.py` — unit (soft-delete archive)
- [ ] `tests/conftest.py` — **EXTEND** Phase 4's: add `mock_admin`, `mock_super_admin`, `mock_cache_redis`, `mock_internal_client` fixtures

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Admin frontend can call `/api/v1/admin/auth/login` and read `admin_access_token` cookie from response | ADMIN-01 | Cross-repo end-to-end requires actual admin frontend deployment; cookie path decision (RESEARCH O-1) needs browser-side verification of Next.js middleware reading the cookie | After staging deploy: open admin UI in browser → login → DevTools Application tab → confirm `admin_access_token` cookie exists, has `httpOnly=true`, `SameSite=Lax`, and is sent on subsequent `/api/v1/admin/*` requests |
| Bootstrap super-admin login on a freshly migrated environment | ADMIN-12 | Requires actual ENV vars + fresh DB at deploy time | Stage deploy: set `ADMIN_BOOTSTRAP_USERNAME` + `ADMIN_BOOTSTRAP_PASSWORD` env vars → start api-service → confirm log line "super-admin bootstrap complete" → login via admin UI |
| inference-service `/internal/logs` endpoint reachable from api-service over HMAC (RESEARCH O-3) | ADMIN-11 | Requires both services running with shared HMAC secret in staging | Staging: `curl -X GET https://api-service/api/v1/admin/service-logs?services=inference-service` with admin token → confirm response includes inference entries (not partial-warning) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (18 test files listed above)
- [ ] No watch-mode flags
- [ ] Feedback latency < 25s (admin-only quick run)
- [ ] `nyquist_compliant: true` set in frontmatter (planner finalizes)

**Approval:** pending
