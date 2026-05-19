---
phase: "08"
plan: "01"
subsystem: api-service/internal
tags: [hmac, internal-endpoint, routing-config, inference-service]
dependency_graph:
  requires: [05-02, 05-01]
  provides: [internal-routing-config-endpoint]
  affects: [08-02]
tech_stack:
  added: []
  patterns: [hmac-auth-dependency, internal-controller]
key_files:
  created:
    - services/api-service/api_service/controllers/internal.py
    - services/api-service/tests/test_internal_endpoint.py
  modified:
    - services/api-service/api_service/services/admin/routing_setting_service.py
    - services/api-service/api_service/core/router.py
    - services/api-service/tests/test_routing_setting_service.py
decisions:
  - "D-03 enforced: allowed_callers={inference-service} only"
  - "version field hardcoded to 0 (matches admin-service behavior)"
  - "InternalRoutingConfigInference schema defined inline in controller (lightweight, single-use)"
metrics:
  duration: "4m 23s"
  completed: "2026-05-19T14:48:39Z"
  tasks: 2
  files_changed: 5
---

# Phase 8 Plan 01: Internal HMAC Endpoint Summary

HMAC-protected GET /api/v1/internal/routing-config/active/inference endpoint ported from admin-service, with resolve_for_internal method and integration tests.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Port resolve_for_internal and update test | fab6728 | routing_setting_service.py, test_routing_setting_service.py |
| 2 | Create internal controller and mount on router | a0c8c50 | controllers/internal.py, core/router.py, test_internal_endpoint.py |

## What Was Built

1. **resolve_for_internal** static method ported into `RoutingSettingService` — assembles routing settings (weights, tier_model_map, score_bands, aliases, RPM limits) into the dict shape expected by inference-service.

2. **Internal controller** at `api_service/controllers/internal.py`:
   - `GET /api/v1/internal/routing-config/active/inference`
   - HMAC signature verification via `build_internal_auth_dependency`
   - `allowed_callers={"inference-service"}` (D-03)
   - Returns `InternalRoutingConfigInference` (version, status, route_order, weights, score_bands, tier_model_map)

3. **Router mount** — `internal.router` included in `api_router` (core/router.py)

4. **Tests** — 11 total passing:
   - 8 routing_setting_service tests (2 new positive tests replacing 1 old negative)
   - 3 internal endpoint integration tests (403 no headers, 403 wrong caller, 200 valid HMAC)

## Deviations from Plan

None - plan executed exactly as written.

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|-----------|
| T-08-01 (Spoofing) | HMAC signature verification with 30s TTL |
| T-08-02 (Tampering) | hmac.compare_digest prevents timing attacks |
| T-08-04 (Privilege escalation) | allowed_callers={"inference-service"} restricts access |

## Verification

```
$ python -m pytest tests/test_routing_setting_service.py tests/test_internal_endpoint.py -x -q
11 passed in 2.13s

$ python -c "from api_service.controllers.internal import router; print('OK')"
OK
```

## Self-Check: PASSED

- [x] services/api-service/api_service/controllers/internal.py exists
- [x] services/api-service/tests/test_internal_endpoint.py exists
- [x] Commit fab6728 exists
- [x] Commit a0c8c50 exists
