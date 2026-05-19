---
phase: "06"
plan: "02"
subsystem: relay
tags: [routing-config, version-poll, upstream-resolution, runtime-config]
dependency_graph:
  requires: [phase-05-routing-settings, phase-03-models]
  provides: [RoutingConfigCache, normalize_runtime_config, resolve_model_channel_target]
  affects: [relay/routing.py, relay/channel_selector.py, core/lifespan.py]
tech_stack:
  added: []
  patterns: [version-poll-cache, SSRF-blocklist, DB-to-config-normalization]
key_files:
  created:
    - services/api-service/api_service/relay/__init__.py
    - services/api-service/api_service/relay/runtime_config.py
    - services/api-service/api_service/relay/upstream.py
    - services/api-service/api_service/relay/config_cache.py
    - services/api-service/tests/test_config_cache.py
  modified: []
decisions:
  - "D-11: Constants defined locally in runtime_config.py (no cross-service import)"
  - "D-09: Version poll via Redis GET routing_config:version per request"
  - "D-12: Startup raises RuntimeError if no model_channels and no model_providers"
  - "channel_slug format: pool_slug:pool_account_id for unique identification"
metrics:
  duration: "12m"
  completed: "2026-05-19T06:22:23Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 5
  files_modified: 0
---

# Phase 06 Plan 02: RoutingConfigCache + Runtime Config Summary

RoutingConfigCache per-worker singleton with Redis version poll, normalize_runtime_config port from router-service, and upstream resolution utilities with SSRF protection.

## Task Results

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | runtime_config.py + upstream.py port | 84c939e | relay/runtime_config.py, relay/upstream.py |
| 2 | RoutingConfigCache + tests | 0461803 | relay/config_cache.py, tests/test_config_cache.py |

## Implementation Details

### Task 1: Runtime Config + Upstream Port

Ported verbatim from `router-service/src/utils/runtime_config.py` and `router-service/src/services/upstream.py`:

- `normalize_runtime_config()` — validates and normalizes raw routing config dicts (weights, score bands, tier model map, model channels, model prices, aliases)
- `parse_score_bands()` — parses "0-3:5,3-5:4" format into typed tuples
- `build_default_runtime_config()` — provides sensible defaults
- `_coerce_default_user_rpm()` — safe int coercion for RPM values
- `resolve_model_channel_target()` — resolves logical model to pool channel via ChannelSelector
- `resolve_model_provider_target()` — resolves logical model to single provider
- `normalize_api_base()` — strips trailing /chat/completions or /models
- `strip_think_tags()` — removes `<think>...</think>` from LLM output
- `_validate_upstream_url()` — SSRF blocklist (localhost, 127.0.0.1, 169.254.169.254, metadata.google.internal, private networks 10.x, 192.168.x, 172.16-31.x)

Constants defined locally per D-11: `DEFAULT_ROUTER_ALIAS`, `FIVEWAY_ROUTE_ORDER`, `FIVEWAY_DEFAULT_WEIGHTS`.

### Task 2: RoutingConfigCache

Implements the per-worker singleton cache with Redis version poll:

- `start(db_session_factory)` — loads config from DB, reads initial version from Redis, raises RuntimeError if empty (D-12)
- `load()` — synchronous read of cached config (called every request)
- `check_and_reload(db_session_factory)` — GET routing_config:version, reload if changed (D-09)
- `_load_from_db()` — reads routing_settings + builds model_channels from pool joins + builds model_prices from model_catalog, then normalizes via normalize_runtime_config()
- `_build_model_channels()` — joins PoolModelConfig + PoolAccount + Pool, decrypts API keys via AES-256-GCM
- `_build_model_prices()` — reads sale prices from ModelCatalog.routing_slug

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- 8/8 tests pass in `tests/test_config_cache.py`
- All module imports verified successfully
- SSRF blocklist contains all required hosts
- normalize_runtime_config produces correct output structure

## Self-Check: PASSED

- [x] services/api-service/api_service/relay/__init__.py exists
- [x] services/api-service/api_service/relay/runtime_config.py exists
- [x] services/api-service/api_service/relay/upstream.py exists
- [x] services/api-service/api_service/relay/config_cache.py exists
- [x] services/api-service/tests/test_config_cache.py exists
- [x] Commit 84c939e exists
- [x] Commit 0461803 exists
