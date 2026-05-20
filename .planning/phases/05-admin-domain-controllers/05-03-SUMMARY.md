---
phase: 05-admin-domain-controllers
plan: 05-03
subsystem: admin-proxy-elimination
tags: [admin, proxy-elimination, user-management, dashboard, vouchers, route-monitor, service-logs, hmac, d-03]
dependency_graph:
  requires: [05-01]
  provides: [ADMIN-03, ADMIN-07, ADMIN-09, ADMIN-10, ADMIN-11]
  affects: [api-service/controllers/admin, api-service/services/admin]
tech_stack:
  added: []
  patterns: [proxy-elimination, inline-audit, HMAC-signed-internal-HTTP, ring-buffer-aggregation]
key_files:
  created:
    - services/api-service/api_service/services/admin/admin_user_service.py
    - services/api-service/api_service/services/admin/dashboard_service.py
    - services/api-service/api_service/services/admin/voucher_service.py
    - services/api-service/api_service/services/admin/route_monitor_service.py
    - services/api-service/api_service/services/admin/service_logs_service.py
    - services/api-service/api_service/controllers/admin/users.py
    - services/api-service/api_service/controllers/admin/dashboard.py
    - services/api-service/api_service/controllers/admin/vouchers.py
    - services/api-service/api_service/controllers/admin/route_monitor.py
    - services/api-service/api_service/controllers/admin/service_logs.py
    - services/api-service/api_service/schemas/admin/user_management.py
    - services/api-service/api_service/schemas/admin/voucher.py
    - services/api-service/api_service/schemas/admin/route_monitor.py
    - services/api-service/api_service/schemas/admin/service_logs.py
    - services/api-service/tests/test_admin_users.py
    - services/api-service/tests/test_admin_dashboard.py
    - services/api-service/tests/test_admin_vouchers.py
    - services/api-service/tests/test_admin_route_monitor.py
    - services/api-service/tests/test_admin_service_logs.py
  modified:
    - services/api-service/api_service/controllers/admin/__init__.py
    - services/api-service/api_service/schemas/admin/__init__.py
    - services/api-service/api_service/repositories/user_repository.py
decisions:
  - "D-02: admin domain services wrap Phase 4 user services + Phase 3 repositories directly"
  - "D-02a: Phase 4 service signatures untouched (no acting_admin_id)"
  - "D-02b: inline audit via AdminAuditService.record + await db.commit()"
  - "D-03: only inference-service remains as remote HMAC target"
  - "O-3: inference log endpoint verified as /internal/logs"
metrics:
  completed: 2026-05-19
  tasks: 4
  files_created: 19
  files_modified: 3
  endpoints_added: 28
---

# Phase 05 Plan 03: Admin Proxy Elimination Summary

Five admin gateway modules replaced with same-process service calls. 28 endpoints under `/api/v1/admin/{users,dashboard,vouchers,route-monitor,service-logs}/*` now flow through direct Phase 4 service / Phase 3 repository calls with zero HTTP gateway hops (except inference-service logs via HMAC).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 23ff3c2 | AdminEndUserService + admin/users controller (14 endpoints) |
| 2 | ba6402c | dashboard + vouchers + route-monitor proxy elimination |
| 3 | bb78efd | AdminServiceLogsService + service_logs controller (D-03 HMAC) |

## Task Details

### Task 1: AdminEndUserService + admin/users controller

- `AdminEndUserService` (NOT `AdminUserService` per Pitfall 3) with 14 staticmethods
- Each method accepts `target_uid: str` at boundary, resolves to `user_id: int` internally
- `reset_user_password` revokes all active sessions (T-5-07)
- `UserRepository.revoke_all_sessions` added to Phase 3 repository
- 14 endpoints under `/api/v1/admin/users/*`
- 3 tests: test_list_no_http (T-5-06), test_topup_atomic_with_audit, test_reset_password_revokes_sessions (T-5-07)

### Task 2: Dashboard + Vouchers + Route Monitor

- `AdminDashboardService` (5 methods): single-query aggregates, no N+1
- `AdminVoucherService` (4 methods): wraps Phase 4 VoucherService (Warning 5 method names verified)
- `AdminRouteMonitorService` (4 methods): direct CallLogRepository calls
- 13 endpoints under `/api/v1/admin/{dashboard,vouchers,route-monitor}/*`
- 6 tests covering no-HTTP, bucketing, generate, disable, list, compare

### Task 3: Service Logs (D-03)

- `AdminServiceLogsService`: local RingBuffer + inference HMAC HTTP
- `_REMOTE_SERVICES` has exactly 1 entry: `("inference-service", "INFERENCE_SERVICE_URL")`
- Partial-on-failure UX: inference unreachable returns `reachable=false` + error
- O-3 verified: inference log endpoint is `/internal/logs`
- 1 endpoint: GET `/api/v1/admin/service-logs` (super_admin only)
- 3 tests: test_local_only, test_partial_on_failure (T-5-08), test_remote_services_only_inference

## Requirements Addressed

| Requirement | Status | Coverage |
|-------------|--------|----------|
| ADMIN-03 | Complete | 14 user-management endpoints, proxy-free |
| ADMIN-07 | Complete | 5 dashboard aggregate endpoints |
| ADMIN-09 | Complete | 4 voucher endpoints |
| ADMIN-10 | Complete | 4 route-monitor endpoints |
| ADMIN-11 | Complete | 1 service-logs endpoint (local + inference HMAC) |

## Validation Slots

| Test | Threat/Validation | Status |
|------|-------------------|--------|
| test_list_no_http | T-5-06 (no HTTP in admin endpoints) | PASS |
| test_topup_atomic_with_audit | T-5-AUDIT-3 (atomic audit) | PASS |
| test_reset_password_revokes_sessions | T-5-07 (session revocation) | PASS |
| test_summary_no_http | T-5-DASH (direct repo calls) | PASS |
| test_rpm_trend_bucketing | Dashboard bucketing | PASS |
| test_generate_batch | T-5-VOUCHER (audit on generate) | PASS |
| test_disable | Voucher disable + audit | PASS |
| test_list | T-5-RM (uid resolution) | PASS |
| test_compare | Route monitor compare | PASS |
| test_local_only | Service logs local fetch | PASS |
| test_partial_on_failure | T-5-08 (graceful degradation) | PASS |
| test_remote_services_only_inference | D-03 enforcement | PASS |

## Deviations from Plan

None - plan executed exactly as written.

## Pitfalls Addressed

| Pitfall | Resolution |
|---------|-----------|
| 2 | Inline `AdminAuditService.record + await db.commit()` replaces `safe_audit_commit` |
| 3 | `AdminEndUserService` naming (not `AdminUserService`) avoids collision with Plan 05-02's `AdminAccountService` |
| 12 | `get_db` used (not `get_db_session`) |
| 13 | `safe_audit_commit` not imported anywhere in api-service |
| 14 | Admin guards (`require_active_admin` / `require_super_admin`) on all endpoints |
| O-3 | Inference log endpoint path verified as `/internal/logs` |

## Endpoint Summary

- 14 users + 5 dashboard + 4 vouchers + 4 route-monitor + 1 service-logs = **28 endpoints**
- Combined Phase 5 total: 5 (05-01 auth) + 36 (05-02 native CRUD) + 28 (05-03 proxy elimination) = **69 admin endpoints**

## Self-Check: PASSED

- All 19 created files verified present
- All 3 task commits verified in git log (23ff3c2, ba6402c, bb78efd)
- 182 tests pass (1 pre-existing health check failure excluded — unrelated to this plan)
