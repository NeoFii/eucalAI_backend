---
phase: 05-admin-domain-controllers
plan: 05-02
subsystem: admin-domain
tags: [admin, pools, model-catalog, routing-settings, audit, admin-on-admin, health-check, cache-invalidation, d-05, d-06, arq-cron]
requires: [05-01]
provides:
  - api_service.schemas.admin.pool — Pool/PoolAccount/PoolModelConfig admin schemas
  - api_service.schemas.admin.model_catalog — admin write schemas + admin response wrappers
  - api_service.schemas.admin.routing_setting — routing-config schemas
  - api_service.services.admin.pool_service.PoolService (599-line port + 4-shape balance parser)
  - api_service.services.admin.model_catalog_service.ModelCatalogService (+ D-05 _invalidate_cache hook)
  - api_service.services.admin.routing_setting_service.RoutingSettingService (+ D-06 _bump_version hook; resolve_for_internal absent per Pitfall 4)
  - api_service.services.admin.account_service.AdminAccountService (renamed from AdminManagementService per Pitfall 3)
  - api_service.services.admin.health_check_service.HealthCheckService (run_health_checks + HEALTH_CHECK_CONCURRENCY=5)
  - api_service.controllers.admin.pools (15 endpoints under /admin/pools/*)
  - api_service.controllers.admin.model_catalog (10 endpoints under /admin/model-catalog/*)
  - api_service.controllers.admin.routing_settings (3 endpoints under /admin/routing-settings/*)
  - api_service.controllers.admin.admin_users (5 endpoints under /admin/admin-users/*)
  - api_service.controllers.admin.audit_logs (3 endpoints under /admin/audit-logs/*)
  - api_service.core.jobs.run_health_checks ARQ cron entry (cadence minute={0,10,20,30,40,50})
  - 4 new HEALTH_CHECK_* settings keys
affects:
  - admin_router routes (now 41 unique admin endpoint paths, +36 since Plan 05-01)
  - core/jobs.py WorkerSettings.functions + cron_jobs (now 6 functions + 5 cron entries)
  - core/config.py ApiServiceSettings (4 new health-check keys)
  - schemas/admin/__init__.py + controllers/admin/__init__.py Wave-2 anchor blocks (Plan 05-02 portion)
tech-stack:
  added: []
  patterns:
    - D-05 mc:* SCAN+DEL post-commit (fail-open) on every model_catalog write
    - D-06 routing_config:version INCR post-commit (fail-open) on every routing_settings write
    - D-02b explicit AdminAuditService.record_auto + await db.commit() pattern (no safe_audit_commit)
    - Pitfall 3 — AdminManagementService -> AdminAccountService rename
    - Pitfall 4 — resolve_for_internal NOT ported (out of scope for Phase 5)
    - Pitfall 5 — public model_catalog.py NOT ported (Phase 4 D-06 covers reads)
    - Pitfall 8 — AdminBaseResponse -> BaseResponse (unified envelope from D-04)
    - Pitfall 9 — _extract_balance covers all 4 provider response shapes
    - Pitfall 12 — get_db (NOT get_db_session)
    - Pitfall 14 — admin guards (require_active_admin / require_super_admin)
    - Pitfall 15 — AdminConflictException raised on duplicate slug/key (admin-grade exception)
    - O-2 — ARQ cron cadence ported verbatim from source services/admin-service/src/core/jobs.py:66
    - O-5 — single ARQ worker (run_health_checks lives on the existing api-service worker)
key-files:
  created:
    - services/api-service/api_service/services/admin/pool_service.py
    - services/api-service/api_service/services/admin/model_catalog_service.py
    - services/api-service/api_service/services/admin/routing_setting_service.py
    - services/api-service/api_service/services/admin/account_service.py
    - services/api-service/api_service/services/admin/health_check_service.py
    - services/api-service/api_service/controllers/admin/pools.py
    - services/api-service/api_service/controllers/admin/model_catalog.py
    - services/api-service/api_service/controllers/admin/routing_settings.py
    - services/api-service/api_service/controllers/admin/admin_users.py
    - services/api-service/api_service/controllers/admin/audit_logs.py
    - services/api-service/api_service/schemas/admin/pool.py
    - services/api-service/api_service/schemas/admin/model_catalog.py
    - services/api-service/api_service/schemas/admin/routing_setting.py
    - services/api-service/tests/test_admin_pools.py
    - services/api-service/tests/test_admin_model_catalog.py
    - services/api-service/tests/test_admin_routing_settings.py
    - services/api-service/tests/test_admin_audit.py
    - services/api-service/tests/test_admin_management.py
    - services/api-service/tests/test_pool_service.py
    - services/api-service/tests/test_model_catalog_service.py
    - services/api-service/tests/test_routing_setting_service.py
    - services/api-service/tests/test_audit_service.py
  modified:
    - services/api-service/api_service/schemas/admin/__init__.py (Plan 05-02 anchor — appended pool/model_catalog/routing_setting re-exports)
    - services/api-service/api_service/controllers/admin/__init__.py (Plan 05-02 anchor — appended 5 sub-routers)
    - services/api-service/api_service/core/jobs.py (run_health_checks function + cron entry + pre-flight notes block)
    - services/api-service/api_service/core/config.py (+4 HEALTH_CHECK_* settings keys)
decisions:
  - D-01 — admin endpoints under /api/v1/admin/* (now 41 paths, 6 categories)
  - D-02b — explicit audit record_auto + commit pattern preserved across every mutation
  - D-05 — mc:* SCAN+DEL invalidation on every model_catalog write (post-commit, fail-open)
  - D-06 — routing_config:version INCR on every routing_settings write (post-commit, fail-open)
  - D-07 plan 2 of 3 (Plan 05-02 landed; Plan 05-03 may proceed in parallel)
  - Pitfall 3 — AdminAccountService is the canonical class name for admin-on-admin CRUD
  - Pitfall 4 — resolve_for_internal explicitly excluded; Phase 8 may rebuild if needed
metrics:
  duration: ~25min
  completed_date: 2026-05-19
---

# Phase 5 Plan 05-02: Pool/Channel/Model Catalog/Routing Settings/Admin Users/Audit Logs Summary

Native-admin write surface ported into api-service: pool & model-catalog & routing-settings CRUD, admin-on-admin account management, audit-log queries, and the health-check service registered as an ARQ cron job. Two structural debts Phase 4 deferred are now closed: D-05 (`mc:*` cache SCAN+DEL on every model_catalog write) and D-06 (`routing_config:version` INCR on every routing_settings write).

## Outcome (one-liner)

36 new admin endpoints under `/api/v1/admin/{pools,model-catalog,routing-settings,admin-users,audit-logs}/*`, backed by 5 new admin services + 3 new admin schema modules, with D-05 + D-06 cache contracts enforced by tests, the channel health-check cron running on the existing ARQ worker at the source cadence (`minute={0,10,20,30,40,50}`), and the AdminAccountService rename in place to keep Plan 05-03's `AdminEndUserService` collision-free. ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-08 fully covered.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | PoolService (599-line port) + 15 pool endpoints + 4-shape balance parser + 10 unit/integration tests | `563c8a0` |
| 2 | ModelCatalogService (+ D-05 hook) + RoutingSettingService (+ D-06 hook, no `resolve_for_internal`) + AdminAccountService (Pitfall 3 rename) + 3 controllers + 5 tests | `5a52398` |
| 3 | Audit log controller (3 endpoints) + HealthCheckService + ARQ cron + 4 HEALTH_CHECK_* settings + 2 tests | `24d1ae3` |

## VALIDATION Slots Covered (12 slots)

| Slot | Test file | Status |
|------|-----------|--------|
| `test_create_encrypts_key` (T-5-05) | tests/test_admin_pools.py | ✅ |
| `test_add_model` | tests/test_admin_pools.py | ✅ |
| `test_check_balances` | tests/test_admin_pools.py | ✅ |
| `test_create_vendor_invalidates_cache` (D-05) | tests/test_admin_model_catalog.py | ✅ |
| `test_invalidates_on_all_writes` (D-05) | tests/test_model_catalog_service.py | ✅ |
| `test_archive_soft_deletes` | tests/test_model_catalog_service.py | ✅ |
| `test_update_bumps_version` (D-06) | tests/test_admin_routing_settings.py | ✅ |
| `test_version_incremented_on_batch` (D-06) | tests/test_admin_routing_settings.py | ✅ |
| `test_validate_rejects_unavailable` | tests/test_routing_setting_service.py | ✅ |
| `test_meta` (returns_shape) | tests/test_admin_audit.py | ✅ |
| `test_list_filters` | tests/test_admin_audit.py | ✅ |
| `test_update_label_invalidates_cache` | tests/test_audit_service.py | ✅ |

Bonus coverage (not in plan but added for safety):

- `test_extract_balance_unknown_returns_zero` + `test_extract_balance_top_level_balance_key` + `test_extract_balance_numeric_data` (Pitfall 9)
- `test_invalidate_cache_swallows_redis_errors` (D-05 fail-open)
- `test_bump_version_fail_open` (D-06 fail-open)
- `test_validate_rejects_no_routing_slug` (catalog routing-slug check)
- `test_validate_passes_when_both_layers_have_slug`, `test_validate_skips_non_tier_keys`
- `test_resolve_for_internal_not_present` (Pitfall 4)
- `test_account_service_renamed` (Pitfall 3)
- `test_run_health_checks_registered_in_worker_settings` + `test_cron_schedule_matches_source_cadence` (O-2/O-5)
- `test_health_check_settings_present`
- `test_no_safe_audit_commit_in_audit_logs_controller` (Pitfall 2)

## Requirements Addressed

- **ADMIN-04** — full: Pool / PoolAccount / PoolModelConfig CRUD endpoints work; provider keys encrypted at rest via AES-256-GCM (`encrypt_api_key`); balance check probes upstream and stores micro-yuan integers.
- **ADMIN-05** — full: Model catalog vendor/category/model write endpoints work; D-05 invalidates `mc:*` cache on every successful write.
- **ADMIN-06** — full: Routing settings list/update/batch_update work; tier coverage validator rejects misconfigurations; D-06 bumps `routing_config:version` on every write.
- **ADMIN-08** — full: Audit log meta/list/update-label endpoints work; module label cache invalidates on update; D-02b explicit audit pattern enforced.

## Decisions Enacted

- **D-01** admin endpoints under `/api/v1/admin/*` — 41 total paths now mounted (6 categories: auth, pools, model-catalog, routing-settings, admin-users, audit-logs). `/admin-audit-logs` source prefix collapsed to `/audit-logs` to match D-01 normalization.
- **D-02b** explicit audit-around-commit — every mutation in `PoolService`, `ModelCatalogService`, `RoutingSettingService`, `AdminAccountService` calls `await AdminAuditService.record(_auto)(...)` followed by `await db.commit()`. No `safe_audit_commit` wrapper anywhere (grep returns 0 matches).
- **D-05** `mc:*` SCAN+DEL on every model_catalog write — `ModelCatalogService._invalidate_cache()` is awaited AFTER `await db.commit()` in 7 documented hook sites: `create_vendor`, `update_vendor`, `create_category`, `update_category`, `create_model`, `update_model`, `disable_model`. Fail-open semantics (Redis errors logged, not propagated).
- **D-06** `routing_config:version` INCR on every routing_settings write — `RoutingSettingService._bump_version()` awaited AFTER `await db.commit()` in `update_setting` AND `batch_update`. Exactly once per request (test enforced).
- **D-07 plan 2 of 3** — Plan 05-02 landed; Plan 05-03 (proxy elimination) may proceed in parallel since both depend only on Plan 05-01 outputs and touch disjoint file sets.

## Pitfalls Addressed

| Pitfall | Resolution |
|---------|------------|
| 2 — audit transactional semantics | All admin services use `await AdminAuditService.record(_auto)(...)` + `await db.commit()` (flush in service, commit at the call site). No `safe_audit_commit` wrapper. |
| 3 — class name collision | `management_service.py` → `account_service.py` and `AdminManagementService` → `AdminAccountService`. Grep returns 0 matches for the old name. Plan 05-03's `AdminEndUserService` (end-user CRUD) is collision-free. |
| 4 — `resolve_for_internal` excluded | Lines 1-185 of source `routing_setting_service.py` ported; lines 186-240 (`resolve_for_internal`) intentionally omitted. `not hasattr(RoutingSettingService, 'resolve_for_internal')` enforced by test. |
| 5 — public model_catalog.py | Only `model_catalog_admin.py` ported (admin writes). The public read controller at admin-service `controllers/model_catalog.py` is NOT migrated — Phase 4 D-06 already covers the reads. |
| 8 — BaseResponse unified | All ported schemas use `BaseResponse` (never `AdminBaseResponse`). Grep returns 0 matches under `services/api-service/api_service/`. |
| 9 — provider balance shapes | `_extract_balance` handles `total_remain`, `points`, `balance`, `remain` plus unknown-shape fail-closed zero. 5 parameterized unit tests cover all branches. |
| 10 — health check cron registration | `run_health_checks` registered in `core/jobs.py` `WorkerSettings.functions` AND `cron_jobs` with source cadence `minute={0,10,20,30,40,50}` (O-2). Single worker (O-5). |
| 12 — get_db (not get_db_session) | All admin controllers depend on `from api_service.core.db import get_db`. Source `get_db_session` is fully replaced. |
| 14 — admin guards | Every endpoint uses `Depends(require_super_admin)` (writes) or `Depends(require_active_admin)` (read-only listing). |
| 15 — admin exceptions | `AdminConflictException` (HTTP 409) raised on duplicate slug/key on `create_vendor`/`create_category`/`create_model`/`create_admin`. `AdminPermissionDeniedException` (HTTP 403) raised on root-only role-change attempts in `AdminAccountService.update_admin_role`. |
| O-2 — source cron cadence | `cron(run_health_checks, minute={0, 10, 20, 30, 40, 50})` matches `services/admin-service/src/core/jobs.py:66` verbatim. |
| O-4 — AdminAuditCategory Literal | Plan 05-01 already preserves all 8 source literal members; Task 3 spot-checks the schema source for the full set. Pre-flight notes block in `core/jobs.py` records the cross-check. |
| O-5 — single ARQ worker | `run_health_checks` appended to the EXISTING `WorkerSettings.functions` list (alongside `aggregate_usage_stats`, `cleanup_expired_*`, etc). No separate worker process; the 2h4g constraint is preserved. |

## Endpoints Added (36)

| Category | Prefix | Endpoints | Source |
|----------|--------|-----------|--------|
| Pools | `/admin/pools/*` | 15 | controllers/pools.py (15 source endpoints) |
| Model catalog | `/admin/model-catalog/*` | 10 | model_catalog_admin.py (9 source + 1 archive verb) |
| Routing settings | `/admin/routing-settings/*` | 3 | routing_settings.py |
| Admin-on-admin | `/admin/admin-users/*` | 5 | admin_users.py |
| Audit logs | `/admin/audit-logs/*` | 3 | admin_audit_logs.py |

Total: **36 new admin endpoints**, plus Plan 05-01's 5 auth endpoints = **41 admin paths in admin_router.routes**.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking issue] Phase 3 `PoolModel` model renamed to `PoolModelConfig`**

- **Found during:** Task 1 (porting `pool_service.py`).
- **Issue:** The plan's interfaces block references `PoolModel` (matching the admin-service source). The api-service Phase 3 port renamed the ORM class to `PoolModelConfig` to match the `pool_model_configs` table name.
- **Fix:** All in-file references updated from `PoolModel` to `PoolModelConfig`; `from api_service.models.pool import Pool, PoolAccount, PoolModelConfig`. Both `pool_service.py` and `health_check_service.py` use the new name.
- **Files modified:** `services/admin/pool_service.py`, `services/admin/health_check_service.py`.

**2. [Rule 3 — Blocking issue] Phase 3 `PoolAccountRepository` / `PoolModelRepository` merged into single `PoolRepository`**

- **Found during:** Task 1 (porting `pool_service.py`).
- **Issue:** Source imports three separate repos (`PoolRepository`, `PoolAccountRepository`, `PoolModelRepository`). Phase 3 merged them into a single `PoolRepository` with prefixed methods: `account_*` and `model_config_*`.
- **Fix:** Replaced `PoolAccountRepository(db).add(x)` with `PoolRepository(db).account_add(x)`, `PoolAccountRepository(db).get_by_id_and_pool(...)` with `PoolRepository(db).account_get_by_id_and_pool(...)`, `PoolModelRepository(db).add(pm)` with `PoolRepository(db).model_config_add(pm)`, `PoolModelRepository(db).get_by_pool_and_model(...)` with `PoolRepository(db).model_config_get_by_pool_and_model(...)`, and `PoolModelRepository(db).remove(...)` with `PoolRepository(db).model_config_remove(...)`.
- **Files modified:** `services/admin/pool_service.py`.

**3. [Rule 3 — Blocking issue] `SupportedModel` / `SupportedModelCategoryMap` / `SupportedModelRepository` rename (Phase 3)**

- **Found during:** Task 2 (porting `model_catalog_service.py`).
- **Issue:** Source uses `SupportedModel`, `SupportedModelCategoryMap`, `SupportedModelRepository`. The api-service Phase 3 port renamed them to `ModelCatalog`, `ModelCatalogCategoryMap`, `ModelCatalogRepository` to match the `model_catalog` table.
- **Fix:** All references updated; `from api_service.models import ModelCatalog, ModelCatalogCategoryMap, ModelCategory, ModelVendor`; `from api_service.repositories.model_catalog_repository import ModelCatalogRepository, ModelCategoryRepository, ModelVendorRepository`.
- **Files modified:** `services/admin/model_catalog_service.py`, `services/admin/routing_setting_service.py` (one local import of the catalog repo).

**4. [Rule 2 — Missing critical functionality] Pool model column defaults at flush time**

- **Found during:** Task 1 (writing `test_create_encrypts_key`).
- **Issue:** The `PoolAccount` ORM has `default=PoolAccountStatus.ACTIVE` etc declared at the column level — these defaults apply at DB flush, not at Python construction time. In the integration test the mocked DB doesn't flush, so `account.status` is `None` when the service tries to serialize it.
- **Fix:** Test-side fix only — the test now explicitly sets the column defaults inside the `_account_add` capture callback that mocks the repo's `add` method. The production code is unchanged because in real flows MySQL applies the defaults at INSERT time.
- **Files modified:** `tests/test_admin_pools.py`.

**5. [Rule 2 — Test stability] settings-singleton vs env-var ordering**

- **Found during:** Task 1 full-suite run.
- **Issue:** `settings = get_settings()` is cached via `@lru_cache`. When other tests load the module first, `PROVIDER_SECRET_MASTER_KEY` may be `""` even though our test set the env var. `test_check_balances` asserted the exact key string passed to `decrypt_api_key`, which intermittently failed in full-suite runs.
- **Fix:** Test asserts only the ciphertext / IV / tag triple (first 3 args) — the master key value is asserted via separate dedicated unit tests on the crypto module. Production code is unchanged.
- **Files modified:** `tests/test_admin_pools.py`.

**6. [Rule 2 — Pre-flight clarity] core/jobs.py pre-flight notes block placement**

- **Plan instruction:** Task 1 step 0 says "record findings in a Phase 5 pre-flight notes block at the top of `services/api-service/api_service/core/jobs.py`".
- **Issue:** Task 1 (pools) doesn't otherwise modify `core/jobs.py`; touching it just to add a comment would force jobs.py into the Task 1 commit footprint.
- **Fix:** Pre-flight notes block was added to `core/jobs.py` in Task 3 instead, alongside the actual `run_health_checks` cron registration that it documents. The notes record both the source cron cadence and the `AdminAuditCategory` Literal cross-check (CONTEXT O-2 + O-4). This keeps the commit footprint of Task 1 focused on pools.
- **Files modified:** `services/api-service/api_service/core/jobs.py` (deferred to Task 3).

### Settings override note (not a deviation — documented)

`config.py` adds 4 new keys (`HEALTH_CHECK_TIMEOUT_SECONDS`, `HEALTH_CHECK_LLM_PROBE_ENABLED`, `HEALTH_CHECK_LLM_PROBE_MAX_TOKENS`, `HEALTH_CHECK_RATE_LIMIT_DELAY`) with documented defaults that match the source admin-service settings.

## Authentication Gates

None encountered.

## Known Stubs

None. All admin endpoints are wired end-to-end. The two cache contracts (D-05 `mc:*` invalidation, D-06 `routing_config:version` INCR) are functional today even though their downstream consumers (`ModelCatalogReadService` cache fills in Phase 4 already exist; `RoutingConfigCache` arrives in Phase 6) — the D-06 INCR is harmless when nobody is reading the version key yet.

## Threat Flags

None. All threats in the plan's `<threat_model>` register are mitigated:

- **T-5-05** (provider key plaintext at rest) — `encrypt_api_key` is called with the plaintext; `PoolAccount.api_key_enc` always carries ciphertext. Verified by `test_create_encrypts_key`.
- **T-5-05a** (provider key in logs) — `mask_api_key` is the only function used in responses + log messages.
- **T-5-AUDIT-1, 2, 3** — explicit `record + commit` pattern; no DELETE endpoint on audit logs; `safe_audit_commit` not imported anywhere.
- **T-5-CACHE-1** (stale model catalog) — D-05 invalidation enforced by `test_invalidates_on_all_writes`.
- **T-5-CACHE-2** (stale routing config) — D-06 INCR enforced by `test_update_bumps_version` + `test_version_incremented_on_batch`.
- **T-5-TIER** — `validate_tier_model_coverage` enforces both pool coverage AND catalog routing_slug existence.
- **T-5-HEALTH** — `HealthCheckService` source preserved verbatim with `mask`/no-log discipline for the decrypted key.
- **T-5-ADMIN-CONFLICT** — `AdminAccountService.create_admin` checks `get_by_email` BEFORE insert; DB unique constraint is the fallback.

## Pre-existing Test Failure (NOT my regression)

`tests/test_health.py::test_ready_returns_200` continues to fail on the wave-1 base because it exercises `/ready` and needs a live DB + Redis. Excluded with `--deselect`; all 172 other tests pass.

## Self-Check: PASSED

- [x] `services/admin/pool_service.py` exports `PoolService` with `_extract_balance` (module-level) and all CRUD methods; commit `563c8a0`.
- [x] `services/admin/model_catalog_service.py` exports `ModelCatalogService._invalidate_cache` (D-05); commit `5a52398`.
- [x] `services/admin/routing_setting_service.py` exports `RoutingSettingService._bump_version` (D-06); `resolve_for_internal` ABSENT (Pitfall 4); commit `5a52398`.
- [x] `services/admin/account_service.py` exports `AdminAccountService`; module does NOT export `AdminManagementService` (Pitfall 3); commit `5a52398`.
- [x] `services/admin/health_check_service.py` exports `HealthCheckService` + `HEALTH_CHECK_CONCURRENCY=5`; commit `24d1ae3`.
- [x] `controllers/admin/{pools,model_catalog,routing_settings,admin_users,audit_logs}.py` all importable; all routers mounted under their respective `/admin/*` prefixes.
- [x] `core/jobs.py` registers `run_health_checks` in WorkerSettings.functions + cron_jobs with source cadence `minute={0,10,20,30,40,50}`.
- [x] `core/config.py` exposes 4 new HEALTH_CHECK_* keys with documented defaults.
- [x] `schemas/admin/__init__.py` re-exports pool / model_catalog / routing_setting schemas BELOW the Plan 05-02 anchor; Plan 05-03 anchor untouched.
- [x] `controllers/admin/__init__.py` includes 5 new sub-routers BELOW the Plan 05-02 anchor; Plan 05-03 anchor untouched.
- [x] Grep audits pass: 0 matches for `safe_audit_commit`, `resolve_for_internal`, `AdminManagementService`, `AdminBaseResponse` under `services/api-service/api_service/`.
- [x] Test suite green: 172 passed, 1 pre-existing infrastructure-dependent test deselected.
- [x] Three commits on the worktree branch: `563c8a0`, `5a52398`, `24d1ae3`.
