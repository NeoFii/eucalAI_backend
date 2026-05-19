---
phase: "08"
plan: "02"
subsystem: inference-service/gateway
tags: [config, gateway-rename, api-service-repoint]
dependency_graph:
  requires: [08-01]
  provides: [inference-service-api-service-gateway]
  affects: []
tech_stack:
  added: []
  patterns: [gateway-rename, config-deprecation]
key_files:
  created:
    - services/inference-service/src/inference_service/gateways/api_service_config.py
  modified:
    - services/inference-service/src/inference_service/core/config.py
    - services/inference-service/src/inference_service/services/config_manager.py
    - services/inference-service/src/inference_service/main.py
decisions:
  - "D-06 applied: API_SERVICE_URL added to InferenceSettings (default http://127.0.0.1:8000)"
  - "D-07 applied: ADMIN_SERVICE_URL preserved with DEPRECATED comment"
  - "D-08 applied: gateway renamed to ApiServiceConfigGateway in api_service_config.py"
metrics:
  duration: "2m 03s"
  completed: "2026-05-19T14:52:56Z"
  tasks: 2
  files_changed: 4
---

# Phase 8 Plan 02: Inference Service Repoint Summary

ApiServiceConfigGateway created pointing at API_SERVICE_URL, ConfigManager and main.py switched to use it — inference-service now fetches routing config from api-service.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add API_SERVICE_URL config and ApiServiceConfigGateway | d78f95c | core/config.py, gateways/api_service_config.py |
| 2 | Switch ConfigManager and main.py to new gateway | 9aa8663 | services/config_manager.py, main.py |

## What Was Built

1. **API_SERVICE_URL config field** added to `InferenceSettings` with default `http://127.0.0.1:8000`. `ADMIN_SERVICE_URL` preserved but marked deprecated (D-07).

2. **ApiServiceConfigGateway** in `gateways/api_service_config.py`:
   - Extends `BaseGateway` with service name `"api-service"`
   - Uses `settings.API_SERVICE_URL` as base URL
   - Same `fetch_active_config()` method calling `/api/v1/internal/routing-config/active/inference`
   - Same error handling (circuit breaker + unavailable → fallback)

3. **ConfigManager** type hint updated from `AdminConfigGateway` to `ApiServiceConfigGateway`

4. **main.py lifespan** imports and instantiates `ApiServiceConfigGateway` instead of `AdminConfigGateway`

## Deviations from Plan

None - plan executed exactly as written.

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|-----------|
| T-08-05 (Spoofing/misconfiguration) | Default localhost:8000; production requires explicit env var; HMAC will fail if pointed at wrong service |
| T-08-06 (DoS config poll) | Existing 60s interval + circuit breaker in BaseGateway unchanged |

## Verification

```
$ PYTHONPATH=src python -c "from inference_service.core.config import InferenceSettings; ..."
All imports OK
API_SERVICE_URL field present

$ grep -c "AdminConfigGateway" src/inference_service/main.py src/inference_service/services/config_manager.py
src/inference_service/main.py:0
src/inference_service/services/config_manager.py:0

$ grep -c "ApiServiceConfigGateway" src/inference_service/main.py src/inference_service/services/config_manager.py
src/inference_service/main.py:2
src/inference_service/services/config_manager.py:2
```

## Self-Check: PASSED

- [x] services/inference-service/src/inference_service/gateways/api_service_config.py exists
- [x] Commit d78f95c exists
- [x] Commit 9aa8663 exists
- [x] No AdminConfigGateway references in main.py or config_manager.py
