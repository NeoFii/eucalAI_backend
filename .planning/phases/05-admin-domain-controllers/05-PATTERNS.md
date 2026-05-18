# Phase 5: Admin Domain Controllers — Pattern Map

**Mapped:** 2026-05-19
**Files classified:** 47 new + 5 modify = 52
**Analogs found:** 52 / 52 (every target has a 1:1 source analog — admin-service for ports, Phase 4 PATTERNS for shared infra files, Phase 3 repositories for data access)

This phase is a **3-axis port**:
1. **Admin-service → api-service ports** (8 services + 7 native controllers + 12 schemas) — line-for-line copies with import rewrites
2. **Proxy-elimination services** (5 NEW services) — replace 5 `gateways/*.py` files with direct calls into Phase 4 user services / Phase 3 repositories
3. **Structural debts** (3 new behaviors) — D-04 schemas hoist, D-05 mc:* cache invalidation, D-06 routing_config:version INCR

Phase 4 PATTERNS.md establishes the shared `core/router.py` + `core/lifespan.py` + `core/jobs.py` + cookie-helper + audit-around-commit conventions; Phase 5 extends those exact patterns. Where a Phase 5 file shares structure with a Phase 4 file (e.g., the cookie helpers, the controller endpoint shape, the `_set_auth_cookies` module-level helper), the analog row points at `04-PATTERNS.md` rather than re-citing.

## Summary

| Plan | New Files | Modified Files | Source Volume (approx lines) | Notes |
|------|-----------|----------------|------------------------------|-------|
| **05-01** Admin auth + bootstrap | 11 | 5 | 214 + 259 + 212 + ~300 schemas + 75 common = ~1,060 | Gating plan — D-04 hoist + Phase 4 import rewrite happens HERE before any new admin code |
| **05-02** Pool/Channel/Model/Routing CRUD | 14 | 1 (`core/jobs.py`) | 599 + 535 + 240 + 186 + 217 + 173 + 231 + 261 + 63 + 126 + 134 + schemas ~600 = ~3,365 | Largest plan; pool_service is largest single file; D-05 + D-06 hooks land here |
| **05-03** Proxy elimination | 22 | 0 (gateways deleted, not modified) | 456 + 198 + 135 + 142 + 63 controllers + 5 NEW services (~990) + 4 schemas (~540) = ~2,524 | 5 NEW services replace 4 gateways + safe_audit_commit wrapper; HMAC sender common/internal.py must land in 05-01 |

**Verified prerequisites (Phase 3):** `AdminUserRepository.{count_active_super_admins,acquire_named_lock,release_named_lock,get_by_email,get_by_uid,get_id_by_uid}` `[VERIFIED via grep]`, `get_current_admin` dependency, `get_ring_buffer` in `common/observability.py:164`, `get_cache_redis` in `common/infra/cache.py:22`, `cache_get_or_fetch` at line 45.

## File Classification

Legend — Plan column references CONTEXT D-07. Match Quality: **exact** = 1:1 source port with only import rewrites; **role-match** = closest existing analog but the new file composes patterns; **role-match (cross-domain)** = Phase 4 user-domain analog (different domain, same shape).

### Plan 05-01 — Admin auth + bootstrap (gating)

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `api_service/common/schemas.py` | schema (envelope hoist) | request-response | `services/api-service/api_service/schemas/common.py` (Phase 4 04-01 produces) + `services/admin-service/src/schemas/common.py` (35 lines) | exact (D-04 merge of two near-identical files) |
| `api_service/common/internal.py` | infrastructure / HTTP sender | request-response | `services/admin-service/src/common/internal.py` (552 lines) | exact (verbatim port + dedupe of signature primitives with existing `common/http/internal_auth.py` — see Pitfall 1) |
| `api_service/controllers/admin/__init__.py` | wiring / sub-router root | n/a | `services/admin-service/src/controllers/__init__.py` (1 line) + the `prefix="/admin"` pattern in Phase 4 04-PATTERNS.md `core/router.py` entry | role-match (new aggregator) |
| `api_service/controllers/admin/auth.py` | controller | request-response | `services/admin-service/src/controllers/auth.py` (214 lines) | exact |
| `api_service/services/admin/__init__.py` | exports | n/a | (new — minimal pass-through) | role-match |
| `api_service/services/admin/auth_service.py` | service | CRUD + auth | `services/admin-service/src/services/auth_service.py` (259 lines) | exact (with import rewrites: `common.token_blacklist` → `common.security.token_blacklist`, `common.utils.jwt` → `common.security.jwt`) |
| `api_service/services/admin/bootstrap_service.py` | service / lifespan | event-driven (startup) | `services/admin-service/src/services/bootstrap_service.py` (212 lines) | exact |
| `api_service/services/admin/audit_service.py` | service | CRUD | `services/admin-service/src/services/audit_service.py` (186 lines) | exact (Plan 05-01 ports the bare `record`/`record_auto` because 05-02 and 05-03 controllers both need it) |
| `api_service/schemas/admin/__init__.py` | exports | n/a | `services/admin-service/src/schemas/__init__.py` | exact |
| `api_service/schemas/admin/auth.py` | schema | request-response | `services/admin-service/src/schemas/auth.py` (~108 lines) | exact |
| `api_service/schemas/admin/admin_user.py` | schema | request-response | `services/admin-service/src/schemas/admin_user.py` (~142 lines) | exact |
| `api_service/schemas/admin/audit_log.py` | schema | request-response | `services/admin-service/src/schemas/audit_log.py` (~80 lines) | exact |
| `api_service/core/policies.py` (MODIFY — add admin guards) | dependency / guard | request-response | `services/admin-service/src/core/policies.py` + Phase 4 04-PATTERNS.md `core/policies.py` entry | exact (extension) |
| `api_service/core/router.py` (MODIFY — include admin sub-router) | wiring | n/a | itself + Phase 4 04-PATTERNS.md `core/router.py` entry | exact |
| `api_service/main.py` (MODIFY — register `super_admin_bootstrap` lifespan hook) | bootstrap | event-driven | Phase 4 04-PATTERNS.md `main.py` entry (cache_redis registration shape) | exact |
| Phase 4 schemas/controllers (MODIFY — rewrite `api_service.schemas.common` → `api_service.common.schemas`) | n/a | n/a | itself | exact (mechanical sed) |
| `tests/test_admin_auth.py` (NEW) | test | integration | `services/api-service/tests/test_auth_dependencies.py` (mocking style) + Phase 4 04-PATTERNS.md test entry | role-match |
| `tests/test_admin_bootstrap.py` (NEW) | test | integration | Phase 4 04-PATTERNS.md test entry | role-match |
| `tests/test_schemas_hoist.py` (NEW) | test | shape | `services/api-service/tests/test_repositories_import.py` (import-shape style) | role-match |
| `tests/conftest.py` (MODIFY — append admin fixtures) | test fixture | n/a | Phase 4 04-PATTERNS.md test entry | exact (extension) |

### Plan 05-02 — Pool/Channel/Model/Routing CRUD

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `api_service/controllers/admin/pools.py` | controller | CRUD | `services/admin-service/src/controllers/pools.py` (231 lines) | exact |
| `api_service/controllers/admin/model_catalog.py` (admin write) | controller | CRUD | `services/admin-service/src/controllers/model_catalog_admin.py` (261 lines) | exact (cohabits with Phase 4 04-03 read controller — see Pitfall 5) |
| `api_service/controllers/admin/routing_settings.py` | controller | CRUD | `services/admin-service/src/controllers/routing_settings.py` (63 lines) | exact |
| `api_service/controllers/admin/admin_users.py` | controller | CRUD | `services/admin-service/src/controllers/admin_users.py` (126 lines) | exact |
| `api_service/controllers/admin/audit_logs.py` | controller | request-response (read + label patch) | `services/admin-service/src/controllers/admin_audit_logs.py` (134 lines) | exact |
| `api_service/services/admin/pool_service.py` | service | CRUD + AES encrypt + upstream HTTP | `services/admin-service/src/services/pool_service.py` (599 lines) | exact (largest port; Pitfall 9 — port `_extract_balance` verbatim with 4 provider shapes) |
| `api_service/services/admin/model_catalog_service.py` | service | CRUD + cache | `services/admin-service/src/services/model_catalog_service.py` (535 lines) + RESEARCH Pattern 3 D-05 hook | exact (port) + role-match (add `_invalidate_cache()` after every write) |
| `api_service/services/admin/routing_setting_service.py` | service | CRUD + cache version signal | `services/admin-service/src/services/routing_setting_service.py:1-185` (240 lines TOTAL, but `resolve_for_internal` lines 186-240 are SKIPPED per Pitfall 4) + RESEARCH Pattern 4 D-06 hook | exact (port lines 1-185 only) + role-match (add `_bump_version()` to `update_setting` + `batch_update`) |
| `api_service/services/admin/account_service.py` (renamed from `management_service.py` per Pitfall 3) | service | CRUD (admin-on-admin) | `services/admin-service/src/services/management_service.py` (217 lines, class `AdminManagementService` → renamed to `AdminAccountService`) | exact (with rename) |
| `api_service/services/admin/health_check_service.py` | service / background | event-driven | `services/admin-service/src/services/health_check_service.py` (173 lines) | exact |
| `api_service/schemas/admin/pool.py` | schema | request-response | `services/admin-service/src/schemas/pool.py` (~229 lines) | exact |
| `api_service/schemas/admin/model_catalog.py` (admin write schemas — extend Phase 4 reads) | schema | request-response | `services/admin-service/src/schemas/model_catalog.py` (~217 lines write-side subset; Phase 4 04-03 already ported the read subset) | exact (additive — port write classes only) |
| `api_service/schemas/admin/routing_setting.py` | schema | request-response | `services/admin-service/src/schemas/routing_setting.py` (~41 lines) | exact |
| `api_service/core/jobs.py` (MODIFY — append `run_health_checks` ARQ cron per O-2/O-5) | worker / cron | event-driven | Phase 4 04-PATTERNS.md `core/jobs.py` entry (4 existing cron jobs) + `services/admin-service/src/core/jobs.py` (source cadence) | role-match (extend with one cron entry) |
| `tests/test_admin_pools.py`, `test_admin_model_catalog.py`, `test_admin_routing_settings.py`, `test_admin_audit.py`, `test_admin_management.py`, `test_pool_service.py`, `test_routing_setting_service.py` (NEW) | test | unit + integration | Phase 4 04-PATTERNS.md test entry | role-match |

### Plan 05-03 — Proxy elimination (gateways deleted)

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `api_service/controllers/admin/users.py` (proxy → native) | controller | CRUD + audit | `services/admin-service/src/controllers/user_management.py` (456 lines) | exact (controller shape) + role-match (replace 14 `_gateway.X(...)` calls with `AdminEndUserService.X(...)`) |
| `api_service/controllers/admin/dashboard.py` (proxy → native) | controller | aggregate / read-heavy | `services/admin-service/src/controllers/dashboard.py` (198 lines) | exact (shape) + role-match (replace 5 `_stats_gateway.X(...)` calls with `AdminDashboardService.X(...)`) |
| `api_service/controllers/admin/vouchers.py` (proxy → native) | controller | CRUD + audit | `services/admin-service/src/controllers/vouchers.py` (135 lines) | exact (shape) + role-match (replace `_gateway.X(...)` with `AdminVoucherService.X(...)`) |
| `api_service/controllers/admin/route_monitor.py` (proxy → native) | controller | read-heavy | `services/admin-service/src/controllers/route_monitor.py` (142 lines) | exact (shape) + role-match (replace `_gateway.X(...)` with `AdminRouteMonitorService.X(...)`) |
| `api_service/controllers/admin/service_logs.py` (partial native + HMAC) | controller | aggregate / HTTP+local | `services/admin-service/src/controllers/service_logs.py` (63 lines) | exact (shape) + role-match (call site changes to `AdminServiceLogsService`) |
| `api_service/services/admin/admin_user_service.py` (NEW, ~400 lines) | service | wraps Phase 4 services | `services/admin-service/src/gateways/user_management.py` (289 lines — 16-method gateway mapped 1:1) + Phase 4 `BalanceService`/`ApiKeyService`/`UsageStatService` | role-match (NEW — composed from gateway method shapes + Phase 4 direct calls) |
| `api_service/services/admin/dashboard_service.py` (NEW, ~200 lines) | service | aggregate | `services/admin-service/src/gateways/user_management.py:30-89` (`UserStatsGateway` 5 methods) + Phase 4 `BillingRepository.stat_*` | role-match (NEW — replace HTTP fetch with direct repo aggregate) |
| `api_service/services/admin/voucher_service.py` (NEW, ~120 lines) | service | CRUD wrapper | Phase 4 `services/voucher_service.py` (admin-perspective wrapper) + admin-service `gateways/user_management.py` voucher methods | role-match (NEW — composed) |
| `api_service/services/admin/route_monitor_service.py` (NEW, ~150 lines) | service | read-heavy | `services/admin-service/src/gateways/route_monitor.py` (113 lines, 4-method gateway) + `CallLogRepository` direct calls | role-match (NEW — gateway HTTP → repo direct) |
| `api_service/services/admin/service_logs_service.py` (NEW, ~120 lines) | service | aggregate (local + HTTP) | `services/admin-service/src/gateways/service_logs.py` (137 lines) | exact (port + delete user/router from `_REMOTE_SERVICES`) |
| `api_service/schemas/admin/user_management.py` | schema | request-response | `services/admin-service/src/schemas/user_management.py` (~275 lines) | exact |
| `api_service/schemas/admin/route_monitor.py` | schema | request-response | `services/admin-service/src/schemas/route_monitor.py` (~137 lines) | exact |
| `api_service/schemas/admin/service_logs.py` | schema | request-response | `services/admin-service/src/schemas/service_logs.py` (~48 lines) | exact |
| `api_service/schemas/admin/voucher.py` | schema | request-response | `services/admin-service/src/schemas/voucher.py` (~80 lines) | exact |
| `tests/test_admin_users.py`, `test_admin_dashboard.py`, `test_admin_vouchers.py`, `test_admin_route_monitor.py`, `test_admin_service_logs.py` (NEW) | test | integration | Phase 4 04-PATTERNS.md test entry | role-match |
| DELETE `services/admin-service/src/gateways/` (5 files) | cleanup | n/a | n/a | n/a |
| DELETE `services/admin-service/src/utils/audit.py` (`safe_audit_commit`) | cleanup | n/a | n/a | n/a (Pitfall 13) |

---

## Pattern Assignments

### Plan 05-01

#### `api_service/common/schemas.py` (envelope hoist — D-04)

**Analogs:**
- Phase 4 04-PATTERNS.md `api_service/schemas/common.py` entry (40 lines source)
- `services/admin-service/src/schemas/common.py` lines 1-36

**Source (admin-service) — full file:**
```python
# services/admin-service/src/schemas/common.py:1-36 [VERIFIED]
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field, model_serializer
from common.utils.timezone import format_iso


class AdminBaseResponse(BaseModel):
    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="消息")


class DateTimeModel(BaseModel):
    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):    # Pitfall 7 — keep list() wrap
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class AdminErrorResponse(AdminBaseResponse):
    code: int = Field(default=400, description="错误码")
    message: str = Field(default="error", description="错误消息")
```

**Target merge (D-04 + Pitfall 8):**
```python
# api_service/common/schemas.py — NEW
from __future__ import annotations
from datetime import datetime
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field, model_serializer
from api_service.common.utils.timezone import format_iso

T = TypeVar("T")


class DateTimeModel(BaseModel):
    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class BaseResponse(BaseModel):                   # unified — was AuthBaseResponse + AdminBaseResponse
    code: int = Field(default=200, description="Status code")
    message: str = Field(default="success", description="Message")


class ErrorResponse(BaseResponse):               # unified error
    code: int = Field(default=400, description="Error code")
    message: str = Field(default="error", description="Error message")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[T] = None
```

**Delta vs analogs:**
- Merge `AdminBaseResponse` + `AuthBaseResponse` → single `BaseResponse` (D-04, Pitfall 8).
- Merge `AdminErrorResponse` + `AuthErrorResponse` → single `ErrorResponse`.
- Add `ApiResponse[T]` generic from Phase 4 source.
- Path: `api_service/common/schemas.py` (NOT `api_service/schemas/common.py`).
- After write: `sed -i 's/api_service\.schemas\.common/api_service.common.schemas/g'` on Phase 4 files; then `sed 's/AuthBaseResponse/BaseResponse/g'` + `sed 's/AdminBaseResponse/BaseResponse/g'` (Pitfall 7+8).

**Plan:** 05-01 (FIRST task — gating for everything else).

---

#### `api_service/common/internal.py` (HMAC sender — Pitfall 1)

**Analog:** `services/admin-service/src/common/internal.py` (552 lines).

**Imports block + error types (source lines 1-69 — port verbatim, no rewrites needed except the observability/Header receiver-side bits already exist in api-service `common/http/internal_auth.py`):**
```python
# services/admin-service/src/common/internal.py:1-69 [VERIFIED]
import asyncio
from dataclasses import dataclass
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

from common.observability import REQUEST_ID_HEADER, get_request_id, TRACE_ID_HEADER, get_trace_id

INTERNAL_CALLER_HEADER = "X-Internal-Service"
INTERNAL_TIMESTAMP_HEADER = "X-Internal-Timestamp"
INTERNAL_SIGNATURE_HEADER = "X-Internal-Signature"


class InternalServiceError(httpx.HTTPError):
    def __init__(self, message: str, *, target_service: str, path: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.target_service = target_service
        self.path = path
        self.status_code = status_code


class InternalServiceUnavailableError(InternalServiceError): ...
class InternalCircuitOpenError(InternalServiceError): ...
class InternalServiceResponseError(InternalServiceError): ...


@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    opened_until: float | None = None


_CIRCUIT_BREAKERS: dict[str, _CircuitState] = {}
```

**Delta vs analog:**
- Verbatim port of 552 lines to `api_service/common/internal.py`.
- Import rewrites: `from common.observability` → `from api_service.common.observability` (all REQUEST_ID/TRACE_ID symbols already present in api-service `common/observability.py:164` — verified).
- **Dedupe step:** `_canonicalize_request_body`, `_canonicalize_request_query`, `_canonicalize_request_target`, `_build_internal_signature` already exist on the receiver side at `api_service/common/http/internal_auth.py`. **Move the four primitives into a new `api_service/common/http/internal_signing.py`** and have both `common/internal.py` (sender) + `common/http/internal_auth.py` (receiver) import from it. Net result: zero duplication.
- Exports `get_internal_client`, `get_internal_json`, `request_internal_json`, `close_internal_clients`, `InternalServiceError`, `InternalServiceUnavailableError`, `InternalCircuitOpenError`, `InternalServiceResponseError`, `reset_internal_circuit_breakers`.

**Why blocking gate:** `AdminServiceLogsService` (05-03) imports `get_internal_json` + `InternalServiceError` from this module. Without 05-01 landing this module, 05-03 cannot compile.

**Plan:** 05-01.

---

#### `api_service/controllers/admin/__init__.py` (admin sub-router root)

**Analog:** new module — Phase 4 04-PATTERNS.md `core/router.py` `include_router` shape.

**Pattern:**
```python
# api_service/controllers/admin/__init__.py
"""Admin sub-router aggregator — mounted at /api/v1/admin by core/router.py."""

from fastapi import APIRouter

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# Plan 05-01:
from api_service.controllers.admin import auth as _admin_auth
admin_router.include_router(_admin_auth.router)

# Plan 05-02: append
# from api_service.controllers.admin import pools, model_catalog, routing_settings, admin_users, audit_logs
# admin_router.include_router(pools.router)            # → /admin/pools/*
# admin_router.include_router(model_catalog.router)    # → /admin/model-catalog/*
# admin_router.include_router(routing_settings.router) # → /admin/routing-settings/*
# admin_router.include_router(admin_users.router)      # → /admin/admin-users/*
# admin_router.include_router(audit_logs.router)       # → /admin/audit-logs/*

# Plan 05-03: append
# from api_service.controllers.admin import users, dashboard, vouchers, route_monitor, service_logs
# admin_router.include_router(users.router)            # → /admin/users/*
# admin_router.include_router(dashboard.router)        # → /admin/dashboard/*
# admin_router.include_router(vouchers.router)         # → /admin/vouchers/*
# admin_router.include_router(route_monitor.router)    # → /admin/route-monitor/*
# admin_router.include_router(service_logs.router)     # → /admin/service-logs/*
```

**Delta vs Phase 4 router pattern:** `prefix="/admin"` is on the sub-router itself, so `api_service/core/router.py` does `api_router.include_router(admin_router)` (NOT `api_router.include_router(admin_router, prefix="/admin")` — that would double-prefix). Each child router's existing `prefix` (e.g., `/auth`, `/pools`) appends naturally — see source `controllers/auth.py:35` uses `tags=["admin-auth"]` (no prefix; the `/auth/login` path is set on the route decorator) versus `controllers/pools.py:33` uses `prefix="/pools"`. **Per D-01:** admin auth controller should use `prefix="/auth"` to produce `/api/v1/admin/auth/login` cleanly.

**Plan:** 05-01.

---

#### `api_service/controllers/admin/auth.py` (admin auth — 5 endpoints)

**Analog:** `services/admin-service/src/controllers/auth.py` (214 lines — full file read above).

**Cookie helpers (source lines 38-70) — port verbatim:**
```python
# services/admin-service/src/controllers/auth.py:38-70 [VERIFIED]
# Cookie names are namespaced to "admin_*" so that the admin and user front-ends
# can coexist on the same domain without overwriting each other's tokens. The
# path stays at "/" because Next.js page-level middleware (which gates /login,
# /dashboard, etc.) needs to read the cookie before any /api request fires.
ADMIN_ACCESS_COOKIE = "admin_access_token"
ADMIN_REFRESH_COOKIE = "admin_refresh_token"
ADMIN_COOKIE_PATH = "/"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=ADMIN_ACCESS_COOKIE, value=access_token, httponly=True,
        secure=settings.COOKIE_SECURE, samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=ADMIN_COOKIE_PATH,
    )
    response.set_cookie(
        key=ADMIN_REFRESH_COOKIE, value=refresh_token, httponly=True,
        secure=settings.COOKIE_SECURE, samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=ADMIN_COOKIE_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=ADMIN_ACCESS_COOKIE, path=ADMIN_COOKIE_PATH)
    response.delete_cookie(key=ADMIN_REFRESH_COOKIE, path=ADMIN_COOKIE_PATH)
```

**Login endpoint (source lines 73-113 — port with import rewrites + D-01 prefix):**
```python
# Target — translations applied
router = APIRouter(prefix="/auth", tags=["admin-auth"])   # was tags=["admin-auth"] only

@router.post("/login", response_model=AdminLoginResponse, summary="Admin login")
async def login(
    payload: AdminLoginRequest, request: Request, response: Response,
    db: AsyncSession = Depends(get_db),                   # Pitfall 12: was get_db_session
) -> AdminLoginResponse:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    admin, access_token = await AdminAuthService.login(db, payload.email, payload.password, user_agent, ip_address)
    refresh_token = create_refresh_token(
        data={"uid": admin.uid, "sub": str(admin.uid)},
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )
    _set_auth_cookies(response, access_token, refresh_token)
    return AdminLoginResponse(code=200, message="登录成功", data=AdminLoginResponseData(...))
```

**Refresh endpoint (source lines 135-160) — keep verbatim;** note the `try/except` block clears cookies on `InvalidTokenException` (port verbatim — important for "refresh from stale cookie" UX).

**Delta vs analog:**
- Imports rewritten per Pitfalls 11+12:
  - `from core.dependencies import get_db_session` → `from api_service.core.db import get_db`
  - `from services.auth_service` → `from api_service.services.admin.auth_service`
  - `from common.utils.jwt` → `from api_service.common.security.jwt`
  - `from core.policies` → `from api_service.core.policies` (extended with `require_active_admin`)
  - `from schemas import (...)` → `from api_service.schemas.admin.auth import (...)`
- **Pitfall O-1 / A1:** preserve `ADMIN_COOKIE_PATH = "/"` (NOT `/api/v1/admin` from CONTEXT `<specifics>`) — load-bearing source comment.
- Router: `APIRouter(prefix="/auth", tags=["admin-auth"])` — D-01 path normalization: paths become `@router.post("/login"...)` instead of `@router.post("/auth/login"...)` to avoid double `/auth/auth/`.

**Plan:** 05-01.

---

#### `api_service/services/admin/auth_service.py`

**Analog:** `services/admin-service/src/services/auth_service.py` (259 lines — full file read above).

**Login flow with audit (source lines 49-149) — port verbatim with import rewrites:**
```python
# services/admin-service/src/services/auth_service.py:49-107 [VERIFIED]
@staticmethod
async def login(db, email, password, user_agent=None, ip_address=None) -> tuple[AdminUser, str]:
    log_event(logger, logging.INFO, "adminLoginAttempt", email=email)
    user_repo = AdminUserRepository(db)
    admin = await user_repo.get_by_email(email)

    if not admin:
        await verify_password_async("dummy", _DUMMY_HASH)    # timing equalizer
        raise InvalidCredentialsException()

    was_locked = bool(admin.login_locked_until and admin.login_locked_until > now())
    if was_locked:
        remaining_minutes = int((admin.login_locked_until - now()).total_seconds() / 60)
        raise InvalidCredentialsException(detail=f"Too many failed login attempts...")

    if not await verify_password_async(password, admin.password_hash):
        admin.login_fail_count = (admin.login_fail_count or 0) + 1
        await AdminAuditService.record(
            db, actor_admin_id=admin.id, target_admin_id=admin.id,
            action="admin_login_failed", resource_type="admin_user",
            resource_id=str(admin.uid), status="failed",
            ip_address=ip_address, user_agent=user_agent,
        )
        if admin.login_fail_count >= LOGIN_MAX_FAILURES:
            admin.login_locked_until = now() + timedelta(hours=LOGIN_LOCK_DURATION_HOURS)
            # ... record admin_login_locked audit + commit
            await db.commit()
            raise InvalidCredentialsException(detail=...)
        await db.commit()
        raise InvalidCredentialsException()
    # ... happy path: set last_login_at, audit success, commit
```

**Refresh + blacklist pattern (source lines 166-206) — port verbatim:**
```python
@staticmethod
async def refresh_access_token(db, refresh_token) -> tuple[str, str]:
    old_jti = get_token_jti(refresh_token)
    if await is_token_blacklisted(old_jti):
        raise InvalidTokenException(detail="Refresh token has been revoked")
    payload = decode_token(refresh_token, settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM)
    if not payload: raise InvalidTokenException()
    if payload.get("type") != "refresh":
        raise TokenExpiredException(detail="Invalid token type")
    uid = payload.get("uid")
    admin = await AdminUserRepository(db).get_by_uid(uid)
    if not admin or admin.status == 0:
        raise AuthenticationException(detail="Account is disabled or does not exist")
    new_access_token = create_access_token(...)
    new_refresh_token = create_refresh_token(...)
    remaining = _remaining_ttl(refresh_token)
    if not await blacklist_token(old_jti, remaining):
        raise InvalidTokenException(detail="Token revocation failed, please retry")
    return new_access_token, new_refresh_token
```

**Delta vs analog:**
- Imports rewrites (Pitfall 11): `from common.token_blacklist` → `from api_service.common.security.token_blacklist`; `from common.utils.jwt` → `from api_service.common.security.jwt`; `from common.utils.password` → `from api_service.common.security.password`; `from repositories` → `from api_service.repositories.admin_user_repository`; `from services.audit_service` → `from api_service.services.admin.audit_service`.
- `from utils.password import check_password_strength` (in `change_password`) → `from api_service.common.utils.password_policy import check_password_strength` (Phase 4 already renamed `utils/password.py` to `password_policy.py` per 04-PATTERNS.md).
- **Audit failure semantics (Pitfall 2 + CONTEXT discretion):** Source already inlines `await AdminAuditService.record(...) + await db.commit()` (no `safe_audit_commit` wrapper here — the wrapper is only on the proxy-elimination controllers). Port verbatim.

**Plan:** 05-01.

---

#### `api_service/services/admin/bootstrap_service.py`

**Analog:** `services/admin-service/src/services/bootstrap_service.py` (212 lines — full file read above).

**Entry point + MySQL lock (source lines 27-59) — port verbatim:**
```python
# services/admin-service/src/services/bootstrap_service.py:27-59 [VERIFIED]
class AdminBootstrapService:
    LOCK_NAME = "bootstrap_super_admin"
    LOCK_TIMEOUT_SECONDS = 10

    @classmethod
    async def ensure_super_admin(cls) -> bool:
        async with get_db_context() as db:
            active_count = await cls._count_active_super_admins(db)
            if active_count > 0:
                await cls._maybe_update_existing_super_admin(db)
                return False
            if not settings.BOOTSTRAP_SUPERADMIN_ENABLED:
                if settings.BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP:
                    raise RuntimeError("No active super_admin and bootstrap is disabled")
                logger.warning("No active super_admin found; bootstrap disabled")
                return False
            cls._validate_bootstrap_settings()
            lock_acquired = await cls._acquire_lock(db)
            if not lock_acquired:
                raise RuntimeError("Failed to acquire bootstrap lock for super admin initialization")
            try:
                active_count = await cls._count_active_super_admins(db)  # double-check after lock
                if active_count > 0:
                    await cls._maybe_update_existing_super_admin(db)
                    return False
                admin, created = await cls._upsert_bootstrap_super_admin(db)
                await cls._record_bootstrap_audit(db, admin, created)
                return created
            finally:
                await cls._release_lock(db)
```

**Lock helpers (source lines 185-198):**
```python
@classmethod
async def _acquire_lock(cls, db) -> bool:
    return await AdminUserRepository(db).acquire_named_lock(cls.LOCK_NAME, cls.LOCK_TIMEOUT_SECONDS)

@classmethod
async def _release_lock(cls, db) -> None:
    try:
        await AdminUserRepository(db).release_named_lock(cls.LOCK_NAME)
    except Exception:
        logger.exception("Failed to release bootstrap lock")
```

**Delta vs analog:**
- Imports rewrites: `from core.db import get_db_context` → `from api_service.core.db import get_db_context` (verified exists in Phase 2); `from core.enums` → `from api_service.core.enums` (Phase 1 baseline); `from repositories.admin_user_repository` → `from api_service.repositories.admin_user_repository` (Phase 3 has `count_active_super_admins`, `acquire_named_lock`, `release_named_lock` verified at lines 36/51/58); `from utils.password` → `from api_service.common.utils.password_policy`; `from common.utils.nanoid_uid` → `from api_service.common.utils.nanoid_uid`; `from common.utils.password` → `from api_service.common.security.password`.
- New settings needed (RESEARCH Settings Gap): `BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP=True`, `BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS=False`, `BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS=False` — add to `core/config.py`.
- Lifespan registration: in `api_service/main.py`, register with priority **25** (after DB at 20, before Redis at 30 — RESEARCH Pattern 5 + Pitfall 6).

**Plan:** 05-01.

---

#### `api_service/services/admin/audit_service.py`

**Analog:** `services/admin-service/src/services/audit_service.py` (186 lines — full file read above).

**Module-level cache + record (source lines 15-117):**
```python
# services/admin-service/src/services/audit_service.py:15-39, 84-116 [VERIFIED]
_action_defs_cache: dict[str, AuditActionDefinition] | None = None
_category_actions_cache: dict[str, tuple[str, ...]] | None = None
_action_labels_cache: dict[str, str] | None = None


class AdminAuditService:
    @staticmethod
    async def _ensure_cache(db: AsyncSession) -> None:
        global _action_defs_cache, _category_actions_cache, _action_labels_cache
        if _action_defs_cache is not None:
            return
        result = await db.execute(
            select(AuditActionDefinition).where(AuditActionDefinition.is_active == True)
        )
        defs = result.scalars().all()
        _action_defs_cache = {d.code: d for d in defs}
        _action_labels_cache = {d.code: d.label for d in defs}
        cat_map: dict[str, list[str]] = {}
        for d in defs:
            cat_map.setdefault(d.category, []).append(d.code)
        _category_actions_cache = {k: tuple(v) for k, v in cat_map.items()}

    @staticmethod
    async def record(
        db, *, actor_admin_id, target_admin_id, action, resource_type, resource_id,
        status, before_data=None, after_data=None, reason=None,
        ip_address=None, user_agent=None,
    ) -> AdminAuditLog:
        audit_log = AdminAuditLog(
            actor_admin_id=actor_admin_id, target_admin_id=target_admin_id,
            action=action, resource_type=resource_type, resource_id=resource_id,
            status=status, before_data=before_data, after_data=after_data,
            reason=reason, ip_address=ip_address, user_agent=user_agent,
        )
        repo = AdminAuditLogRepository(db)
        repo.add(audit_log)
        await db.flush()
        return audit_log
```

**Delta vs analog:**
- Imports rewrites: `from models` → `from api_service.models`; `from repositories` → `from api_service.repositories.{audit_log_repository,admin_user_repository}` (Phase 3 verified); `from schemas.audit_log import AdminAuditCategory` → `from api_service.schemas.admin.audit_log import AdminAuditCategory`.
- Class name preserved: `AdminAuditService` (no collision).
- `record_auto` source (lines 118-149) references `from common.request_context import get_request_ip, get_request_user_agent` — Phase 1 has `api_service/common/http/request_context.py` (verified). Rewrite import accordingly.
- **Failure handling (CONTEXT discretion):** `record` keeps `await db.flush()` (NOT `await db.commit()`) — the caller commits the whole transaction. So an audit-row failure naturally aborts the business mutation via the shared session rollback. **This matches RESEARCH Pattern 2 recommendation** and the Pitfall 2 resolution.

**Plan:** 05-01 (early — 05-02 and 05-03 both depend on `AdminAuditService.record`).

---

#### `api_service/schemas/admin/auth.py` + `admin_user.py` + `audit_log.py`

**Analogs:**
- `services/admin-service/src/schemas/auth.py` (~108 lines)
- `services/admin-service/src/schemas/admin_user.py` (~142 lines)
- `services/admin-service/src/schemas/audit_log.py` (~80 lines)

**Pattern (representative — `audit_log.py`):**
```python
# Port verbatim, only the base-class name changes per Pitfall 8
# from schemas.common import AdminBaseResponse  ←  was
from api_service.common.schemas import BaseResponse  # D-04

class AdminAuditCategory(str): ...  # actual is Literal[...] — read source for full enum (O-4)

class AdminAuditActor(BaseModel):
    uid: str
    email: str
    name: str
    role: str

class AdminAuditLogItem(DateTimeModel):
    id: int
    actor_admin: AdminAuditActor
    target_admin: AdminAuditActor | None = None
    action: str
    action_label: str
    resource_type: str
    resource_id: str | None
    # ... etc

class AdminAuditLogListResponse(BaseResponse):  # was AdminBaseResponse
    data: PaginatedResponse[AdminAuditLogItem] | None = None
```

**Delta vs analog:**
- `AdminBaseResponse` → `BaseResponse` (D-04 + Pitfall 8).
- `from schemas.common` → `from api_service.common.schemas`.
- `from common.api import PaginatedResponse` → `from api_service.common.api.pagination import PaginatedResponse`.
- `DateTimeModel` import same source `api_service.common.schemas`.
- **O-4:** read source `audit_log.py:13` for the full `AdminAuditCategory` Literal members before porting (RESEARCH flagged as unverified).

**Plan:** 05-01.

---

#### `api_service/core/policies.py` (MODIFY — add admin guards, Pitfall 14)

**Analog:** Phase 4 04-PATTERNS.md `core/policies.py` entry (which itself ports user-service `core/policies.py:12-19`) + admin-service `core/policies.py`.

**Existing (Phase 4):**
```python
async def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.status == 0:
        raise UserDisabledException()
    if current_user.status == 2:
        raise EmailNotVerifiedException()
    return current_user
```

**Append (Pitfall 14 — port from admin-service):**
```python
from api_service.core.dependencies.admin import get_current_admin  # Phase 3 D-06
from api_service.core.enums import AdminRole, AdminStatus
from api_service.common.core.exceptions import AdminPermissionDeniedException  # Pitfall 15 adds class

async def require_active_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.status != AdminStatus.ACTIVE:
        raise AdminPermissionDeniedException("Admin account inactive")
    return admin

async def require_super_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.role != AdminRole.SUPER_ADMIN:
        raise AdminPermissionDeniedException("Super admin permission required")
    return admin
```

**Delta vs Phase 4:** purely additive. Imports `AdminPermissionDeniedException` + `AdminConflictException` from `api_service.common.core.exceptions` — these two classes are NEW per Pitfall 15. Plan 05-01 must add them to `common/core/exceptions.py` (mapped to HTTP 403 + 409 respectively).

**Plan:** 05-01.

---

#### `api_service/core/router.py` (MODIFY — include admin sub-router)

**Analog:** itself + Phase 4 04-PATTERNS.md `core/router.py` entry.

**Current state (verified):**
```python
# api_service/core/router.py:1-12 [VERIFIED]
from fastapi import APIRouter
api_router = APIRouter(prefix="/api/v1")

# Phase 4: User domain routes
# Phase 5: Admin domain routes
```

**Append in 05-01:**
```python
# Phase 5: Admin domain routes
from api_service.controllers.admin import admin_router
api_router.include_router(admin_router)   # admin_router already has prefix="/admin"
```

**Delta vs Phase 4 controllers wiring:** Phase 4 includes flat per-controller routers (`auth.router`, `keys.router`, ...) directly under `/api/v1`. Phase 5 includes a single `admin_router` aggregator that owns `/admin`. The sub-router pattern keeps `api_router.include_router(admin_router)` to one line and lets `controllers/admin/__init__.py` own all admin sub-routes (D-01).

**Plan:** 05-01.

---

#### `api_service/main.py` (MODIFY — bootstrap lifespan hook)

**Analog:** Phase 4 04-PATTERNS.md `main.py` entry (`cache_redis` registration shape, priority=30).

**Append after database registration (RESEARCH Pattern 5):**
```python
# api_service/main.py — append after database registration (priority=20)
async def _bootstrap_super_admin() -> None:
    from api_service.services.admin.bootstrap_service import AdminBootstrapService
    await AdminBootstrapService.ensure_super_admin()

registry.register(
    "super_admin_bootstrap",
    init_fn=_bootstrap_super_admin,
    priority=25,        # AFTER db(20), BEFORE redis(30) — Pitfall 6
)
```

**Delta vs Phase 4 main.py:** Phase 4 registers `arq_pool` at priority=40. Phase 5 inserts `super_admin_bootstrap` at priority=25. The lifespan registry sorts ascending so order is: logging(0) → snowflake(10) → database(20) → **super_admin_bootstrap(25)** → redis(30) → cache_redis(30) → arq_pool(40). No shutdown function needed — bootstrap is one-shot.

**Plan:** 05-01.

---

#### `tests/test_admin_auth.py`, `test_admin_bootstrap.py`, `test_schemas_hoist.py` (NEW)

**Analog:** Phase 4 04-PATTERNS.md test entry — same mocking style (`patch("api_service.services.admin.auth_service.AdminAuthService")` + `AsyncMock`).

**Pattern (`test_schemas_hoist.py` — verifies D-04 import rewrite):**
```python
# CITED: api-service tests/test_repositories_import.py style
def test_phase4_imports_resolve_from_new_location():
    """After D-04, Phase 4 schemas must import from common.schemas, not schemas.common."""
    from api_service.common.schemas import ApiResponse, DateTimeModel, BaseResponse
    assert ApiResponse is not None
    assert BaseResponse is not None
    # negative test — old path should no longer have these
    try:
        from api_service.schemas.common import AuthBaseResponse  # noqa
        assert False, "old path should not export AuthBaseResponse after D-04"
    except ImportError:
        pass  # expected
```

**Plan:** 05-01.

---

### Plan 05-02

#### `api_service/controllers/admin/pools.py`

**Analog:** `services/admin-service/src/controllers/pools.py` (231 lines — first 80 lines read above).

**Imports + section pattern (source lines 1-50 — port with rewrites):**
```python
# services/admin-service/src/controllers/pools.py:1-50 [VERIFIED]
router = APIRouter(prefix="/pools", tags=["admin-pools"])

_SLUG_PATH = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=64)
_MODEL_SLUG_PATH = Path(..., max_length=120)


@router.post("", response_model=PoolResponse, summary="Create pool")
async def create_pool(
    payload: PoolCreate,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> PoolResponse:
    item = await PoolService.create_pool(db, payload, actor_admin_id=current_admin.id)
    return PoolResponse(data=item)
```

**Delta vs analog:**
- `from schemas.common import AdminBaseResponse` → `from api_service.common.schemas import BaseResponse` (Pitfall 8) — though pools.py only uses concrete response classes via schemas.pool.
- `get_db_session` → `get_db` (Pitfall 12).
- `from core.policies` → `from api_service.core.policies` (Pitfall 14 — has `require_super_admin` after 05-01 lands).
- Path: file moves to `controllers/admin/pools.py`; URL: `/api/v1/admin/pools/*` (admin_router prefix + this router's `/pools`).

**Plan:** 05-02.

---

#### `api_service/services/admin/pool_service.py` (largest file — 599 lines)

**Analog:** `services/admin-service/src/services/pool_service.py` (599 lines — first 120 lines read above).

**Imports block (source lines 1-37) — port with rewrites:**
```python
# services/admin-service/src/services/pool_service.py:1-37 [VERIFIED]
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import settings
from core.enums import PoolAccountStatus
from common.internal import get_internal_client                 # USES 05-01 Pitfall 1 module
from models.pool import Pool, PoolAccount, PoolModel
from repositories.pool_repository import (
    PoolAccountRepository, PoolModelRepository, PoolRepository,
)
from schemas.pool import (PoolAccountCreate, PoolItem, PoolDetail, ...)
from services.audit_service import AdminAuditService
from common.core.exceptions import NotFoundException, ValidationException
from common.utils.crypto import decrypt_api_key, encrypt_api_key, mask_api_key
```

**Provider balance parser (source lines 90-101 — port verbatim, Pitfall 9):**
```python
def _extract_balance(body: dict) -> int:
    """Parse upstream balance response into micro-yuan (1 yuan = 1,000,000)."""
    data = body.get("data", body)
    if isinstance(data, dict):
        for key in ("total_remain", "points", "balance", "remain"):
            if key in data:
                return int(float(data[key]) * 1_000_000)
    if isinstance(data, (int, float)):
        return int(float(data) * 1_000_000)
    if isinstance(body, dict) and "balance" in body:
        return int(float(body["balance"]) * 1_000_000)
    return 0
```

**Delta vs analog:**
- Imports rewrites: `from core.config` → `from api_service.core.config`; `from core.enums` → `from api_service.core.enums`; `from common.internal import get_internal_client` → `from api_service.common.internal import get_internal_client` (05-01 Pitfall 1 module); `from models.pool` → `from api_service.models.pool`; `from repositories.pool_repository` → `from api_service.repositories.pool_repository` (Phase 3 merged — verify class names match `PoolRepository` / `PoolAccountRepository` / `PoolModelRepository`); `from common.utils.crypto` → `from api_service.common.security.crypto`.
- Class section organization (Claude's Discretion in CONTEXT): keep three logical sections (`# ---- Pool ----`, `# ---- PoolModel ----`, `# ---- PoolAccount ----`) as in source — 599 lines justifies the explicit anchors.
- **Pitfall 9 — write 4 unit tests for `_extract_balance`** (one per provider shape: `total_remain`, `points`, `balance`, `remain`).

**Plan:** 05-02.

---

#### `api_service/services/admin/model_catalog_service.py` (535 lines + D-05 hook)

**Analog:** `services/admin-service/src/services/model_catalog_service.py` (535 lines — first 60 lines read above) + RESEARCH Pattern 3 D-05 hook.

**Serializer pattern (source lines 44-60) — port verbatim:**
```python
# services/admin-service/src/services/model_catalog_service.py:44-60 [VERIFIED]
class ModelCatalogService:
    @staticmethod
    def _vendor_item(vendor: ModelVendor) -> ModelVendorItem:
        return ModelVendorItem(
            id=vendor.id, slug=vendor.slug, name=vendor.name,
            logo_url=vendor.logo_url, is_active=vendor.is_active,
            sort_order=vendor.sort_order,
            created_at=vendor.created_at, updated_at=vendor.updated_at,
        )
```

**D-05 invalidation hook (RESEARCH Pattern 3 — NEW, wire after every commit):**
```python
# api_service/services/admin/model_catalog_service.py — NEW helper
from api_service.common.infra.cache import get_cache_redis

class ModelCatalogService:
    @staticmethod
    async def _invalidate_cache() -> None:
        """Invalidate all mc:* cache keys (D-05). Called after every successful write."""
        try:
            r = get_cache_redis()
            async for key in r.scan_iter(match="mc:*"):
                await r.delete(key)
        except Exception:
            logger.warning("model_catalog cache invalidation failed", exc_info=True)

    @staticmethod
    async def create_vendor(db, payload, *, actor_admin_id, ip_address, user_agent):
        # ... source body ...
        await db.commit()
        await ModelCatalogService._invalidate_cache()   # NEW per D-05
        return ModelCatalogService._vendor_item(vendor)
```

**Delta vs analog:**
- Imports rewrites: `from models` → `from api_service.models`; `from repositories` → `from api_service.repositories.model_catalog_repository`; `from services.audit_service` → `from api_service.services.admin.audit_service`; `from schemas.model_catalog` → `from api_service.schemas.admin.model_catalog`.
- **D-05 NEW:** add `_invalidate_cache()` + wire after every `await db.commit()` in: `create_vendor`, `update_vendor`, `delete_vendor` (if soft-delete), `create_category`, `update_category`, `delete_category`, `create_model`, `update_model`, `disable_model`/`archive_model`, and any `update_category_map`. **Pre-commit semantics:** invalidate AFTER commit (so rollback doesn't clear cache unnecessarily).
- Coexists with Phase 4 `ModelCatalogReadService` — they touch the same `mc:*` cache keys (Phase 4 fills, Phase 5 invalidates). No code overlap (different file, different filter defaults).

**Plan:** 05-02.

---

#### `api_service/services/admin/routing_setting_service.py` (port lines 1-185 + D-06 hook)

**Analog:** `services/admin-service/src/services/routing_setting_service.py:1-185` (240 lines TOTAL — full file read above; Pitfall 4 explicitly EXCLUDES `resolve_for_internal` at lines 186-240).

**Update + audit pattern (source lines 60-101 — port verbatim with D-06 INCR appended):**
```python
# services/admin-service/src/services/routing_setting_service.py:60-101 [VERIFIED]
@staticmethod
async def update_setting(
    db, key, value, *, actor_admin_id, ip_address=None, user_agent=None,
) -> RoutingSettingItem:
    repo = RoutingSettingRepository(db)
    setting = await repo.get_by_key(key)
    if setting is None:
        raise NotFoundException(f"setting '{key}' not found")
    validator = _TYPE_VALIDATORS.get(setting.value_type)
    if validator:
        try: validator(value)
        except (ValueError, TypeError) as exc:
            raise ValidationException(f"value '{value}' is not valid for type '{setting.value_type}': {exc}") from exc

    before_value = setting.value
    await repo.update_value(key, value, updated_by=actor_admin_id)
    await AdminAuditService.record(
        db, actor_admin_id=actor_admin_id, target_admin_id=None,
        action="update_routing_setting", resource_type="routing_setting", resource_id=key,
        status="success",
        before_data={"key": key, "value": before_value},
        after_data={"key": key, "value": value},
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()
    await RoutingSettingService._bump_version()   # NEW per D-06
    updated = await repo.get_by_key(key)
    return _setting_item(updated)
```

**D-06 version-bump hook (RESEARCH Pattern 4 — NEW):**
```python
ROUTING_CONFIG_VERSION_KEY = "routing_config:version"

class RoutingSettingService:
    @staticmethod
    async def _bump_version() -> None:
        try:
            r = get_cache_redis()
            await r.incr(ROUTING_CONFIG_VERSION_KEY)
        except Exception:
            logger.warning("routing_config_version_bump_failed", exc_info=True)
```

**Delta vs analog:**
- Imports rewrites (same pattern as audit_service).
- **Pitfall 4 — DO NOT PORT `resolve_for_internal` (lines 186-240):** it's only used by `controllers/internal.py` which D-01b explicitly excludes. Port lines 1-185 only.
- **D-06 NEW:** add `_bump_version()`; wire into both `update_setting` and `batch_update` after their `await db.commit()`.
- `validate_tier_model_coverage` (lines 145-183) — port verbatim; it uses `PoolRepository.get_available_model_slugs` (verify on Phase 3 repo) + `SupportedModelRepository.get_routing_slugs_existing`.

**Plan:** 05-02.

---

#### `api_service/services/admin/account_service.py` (renamed from management_service, Pitfall 3)

**Analog:** `services/admin-service/src/services/management_service.py` (217 lines — class `AdminManagementService`).

**Create-admin pattern (source lines 37-80 — port with class rename):**
```python
# services/admin-service/src/services/management_service.py:37-80 [VERIFIED]
class AdminAccountService:        # renamed from AdminManagementService per Pitfall 3
    @staticmethod
    async def create_admin(
        db, *, actor_admin, email, name, password, role=AdminRole.ADMIN,
    ) -> AdminUser:
        user_repo = AdminUserRepository(db)
        if await user_repo.get_by_email(email):
            raise AdminConflictException("Admin email already exists")
        ok, message = check_password_strength(password)
        if not ok:
            raise ValidationException(message)
        admin = AdminUser(
            uid=generate_nanoid_uid(),
            email=email,
            password_hash=await hash_password_async(password),
            name=name, role=role, status=AdminStatus.ACTIVE,
            created_by_admin_id=actor_admin.id,
            updated_by_admin_id=actor_admin.id,
        )
        user_repo.add(admin)
        await db.flush()
        await db.refresh(admin)
        await AdminAuditService.record_auto(
            db, actor_admin_id=actor_admin.id, target_admin_id=admin.id,
            action="create_admin", resource_type="admin_user",
            resource_id=str(admin.uid), status="success",
            before_data=None,
            after_data=AdminAccountService.build_admin_snapshot(admin),
        )
        await db.commit()
```

**Delta vs analog:**
- **Class rename:** `AdminManagementService` → `AdminAccountService` (Pitfall 3 — prevents collision with `AdminUserService` in 05-03 which manages END users).
- File rename: `management_service.py` → `account_service.py`.
- Controller `admin_users.py` import: `from services.management_service import AdminManagementService` → `from api_service.services.admin.account_service import AdminAccountService` (and rename references inside the controller body).
- Imports rewrites: `from core.exceptions import AdminConflictException, AdminPermissionDeniedException` → `from api_service.common.core.exceptions import ...` (Pitfall 15 — both classes are added there in 05-01).

**Plan:** 05-02.

---

#### `api_service/services/admin/health_check_service.py` + `core/jobs.py` cron entry (O-2/O-5)

**Analog:** `services/admin-service/src/services/health_check_service.py` (173 lines — first 60 lines read above).

**Concurrency pattern (source lines 26-52) — port verbatim:**
```python
# services/admin-service/src/services/health_check_service.py:26-52 [VERIFIED]
HEALTH_CHECK_CONCURRENCY = 5

class HealthCheckService:
    @staticmethod
    async def run_health_checks(db: AsyncSession) -> None:
        repo = PoolRepository(db)
        pools, _ = await repo.list_pools(page=1, page_size=500)
        semaphore = asyncio.Semaphore(HEALTH_CHECK_CONCURRENCY)
        tasks = []
        for pool in pools:
            if not pool.is_enabled: continue
            accounts = [a for a in (pool.accounts or [])
                        if a.status in (PoolAccountStatus.ACTIVE, PoolAccountStatus.ERROR)]
            for account in accounts:
                tasks.append(asyncio.create_task(
                    HealthCheckService._check_with_limit(semaphore, db, pool, account)
                ))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await db.commit()
```

**ARQ cron registration (RESEARCH O-2/O-5 — append to Phase 4's `api_service/core/jobs.py`):**
```python
# Phase 4 04-PATTERNS.md `core/jobs.py` had 4 cron jobs; Phase 5 appends:
from arq.cron import cron
from api_service.services.admin.health_check_service import HealthCheckService

async def run_health_checks(ctx: dict) -> None:
    async with get_db_context() as db:
        await HealthCheckService.run_health_checks(db)

# Append to WorkerSettings.functions + cron_jobs:
"functions": [
    aggregate_usage_stats, cleanup_expired_verification_codes,
    cleanup_expired_sessions, reconcile_balance_ledger,
    send_verification_email,  # Phase 4 D-02
    run_health_checks,        # Phase 5 NEW (O-2/O-5)
],
"cron_jobs": [
    cron(run_health_checks, hour=None, minute={0, 30}),   # source cadence verify O-2
    # ... Phase 4 cron entries unchanged
],
```

**Delta vs analog:**
- Imports rewrites: `from common.internal import get_internal_client` → `from api_service.common.internal` (05-01 module).
- **O-2 — read** `services/admin-service/src/core/jobs.py` during plan 05-02 task to extract exact cron cadence (every 30 min vs every 6 h vs ...). Port verbatim.
- **O-5:** add to api-service's existing user-domain ARQ worker (not a separate worker). Phase 4 `core/jobs.py` worker is the single worker process.

**Plan:** 05-02 (last task — register cron).

---

#### Schemas: `pool.py`, `model_catalog.py` (write extension), `routing_setting.py`

**Analogs:** corresponding `services/admin-service/src/schemas/*.py`.

**Pattern (representative):**
- `from schemas.common import AdminBaseResponse, DateTimeModel` → `from api_service.common.schemas import BaseResponse, DateTimeModel` (Pitfall 8 + D-04).
- `from common.api import PaginatedResponse` → `from api_service.common.api.pagination import PaginatedResponse`.
- `AdminBaseResponse` references in `class XxxResponse(AdminBaseResponse)` → `class XxxResponse(BaseResponse)`.
- For `model_catalog.py`: Phase 4 04-03 already shipped read schemas. Phase 5 **appends** `ModelVendorCreate`, `ModelVendorUpdate`, `ModelCategoryCreate`, `ModelCategoryUpdate`, `SupportedModelCreate`, `SupportedModelUpdate`, `ModelCatalogOperationResponse` to the **same file** (single source of truth).

**Plan:** 05-02.

---

### Plan 05-03

#### `api_service/controllers/admin/users.py` (proxy → native, 456 lines source)

**Analog:** `services/admin-service/src/controllers/user_management.py` (456 lines — first 100 lines read above).

**Source proxy pattern (lines 56-74 — port shape, replace gateway calls):**
```python
# services/admin-service/src/controllers/user_management.py:56-74 [VERIFIED]
router = APIRouter(prefix="/users", tags=["user-management"])
_gateway = UserManagementGateway()        # ← DELETE

@router.get("", response_model=UserListResponse, summary="List users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: int | None = Query(None),
    _current_admin: AdminUser = Depends(require_active_admin),
) -> UserListResponse:
    data = await _gateway.list_users(                     # ← REPLACE
        page=page, page_size=page_size, search=search, status=status,
    )
    return UserListResponse(data=PaginatedResponse[UserListItem](
        items=[UserListItem(**item) for item in data["items"]],
        total=data["total"], page=data["page"], page_size=data["page_size"],
    ))
```

**Target rewrite (Wave 1 of 05-03):**
```python
from api_service.services.admin.admin_user_service import AdminEndUserService

@router.get("", response_model=UserListResponse, summary="List users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: int | None = Query(None),
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),       # NEW — service needs DB
) -> UserListResponse:
    items, total = await AdminEndUserService.list_users(
        db, page=page, page_size=page_size, search=search, status=status,
    )
    return UserListResponse(data=PaginatedResponse[UserListItem](
        items=[UserListItem(**item) for item in items],
        total=total, page=page, page_size=page_size,
    ))
```

**Audit-around-commit (replace `safe_audit_commit`, Pitfall 2 / Pitfall 13):**
```python
# Source pattern (DELETE):
# await safe_audit_commit(db, actor_admin_id=..., action=..., ...)

# Target pattern (inline):
ip_address, user_agent = get_request_meta(request)
await AdminAuditService.record(
    db, actor_admin_id=current_admin.id, target_admin_id=None,
    action="topup_user", resource_type="user", resource_id=str(uid),
    status="success",
    after_data={"amount": payload.amount, "order_no": result.order_no},
    ip_address=ip_address, user_agent=user_agent,
)
await db.commit()
```

**Delta vs analog:**
- Delete `_gateway = UserManagementGateway()` line and all `_gateway.X(...)` calls.
- Replace with `AdminEndUserService.X(...)` direct calls (14 endpoint paths).
- Add `db: AsyncSession = Depends(get_db)` to every handler (service needs DB).
- Delete `from utils.audit import safe_audit_commit`; replace 14 `safe_audit_commit(...)` calls with `await AdminAuditService.record(...) + await db.commit()` (Pitfall 13).
- Imports rewrites (standard pattern from 05-01).

**Plan:** 05-03.

---

#### `api_service/services/admin/admin_user_service.py` (NEW — class `AdminEndUserService`)

**Analogs (composed):**
- `services/admin-service/src/gateways/user_management.py` (289 lines — defines 16-method gateway whose method signatures are the target service's contract)
- Phase 4 services: `BalanceService.topup` / `adjust_balance`, `ApiKeyService.disable` / `enable` / `list_for_user`, `UsageStatService.list_usage_logs`, `UserRepository` direct (for list/detail/disable/reset_password)

**Gateway method shape (source lines 40-89 of `gateways/user_management.py`, `UserStatsGateway` — same pattern applies for `UserManagementGateway`):**
```python
# services/admin-service/src/gateways/user_management.py:40-50 [VERIFIED]
async def fetch_total_users(self) -> int:
    payload = await self._get("/api/v1/internal/stats/users")
    try:
        return int(payload["total_users"])
    except (KeyError, TypeError, ValueError) as exc:
        from common.core.exceptions import ServiceUnavailableException
        raise ServiceUnavailableException(...) from exc
```

**Target pattern (NEW — direct call, no HTTP):**
```python
# api_service/services/admin/admin_user_service.py — NEW
from sqlalchemy.ext.asyncio import AsyncSession
from api_service.repositories.user_repository import UserRepository
from api_service.services.balance_service import BalanceService
from api_service.services.api_key_service import ApiKeyService
from api_service.services.usage_stat_service import UsageStatService

class AdminEndUserService:    # NOT AdminUserService — Pitfall 3 collision avoidance

    @staticmethod
    async def list_users(db: AsyncSession, *, page, page_size, search=None, status=None):
        return await UserRepository(db).list_users(
            page=page, page_size=page_size, search=search, status=status,
        )

    @staticmethod
    async def topup_user(db: AsyncSession, *, target_uid: str, amount: int,
                         operator_admin, remark: str | None = None):
        user = await UserRepository(db).get_by_uid(target_uid)
        if not user:
            raise UserNotFoundException()
        # Phase 4 D-02a: do NOT pass operator_admin into BalanceService
        return await BalanceService.topup(
            db, user_id=int(user.id), amount=amount, ref_type="admin_topup",
            ref_id=f"admin:{operator_admin.uid}", remark=remark,
        )

    @staticmethod
    async def disable_api_key(db, *, target_uid: str, key_id: int):
        user = await UserRepository(db).get_by_uid(target_uid)
        if not user:
            raise UserNotFoundException()
        return await ApiKeyService.update_status(
            db, key_id=key_id, user_id=int(user.id),
            status=UserApiKey.STATUS_DISABLED,
        )
    # ... 13 more methods (1:1 mapping to gateway's 16) ...
```

**Delta vs analogs:**
- 16 gateway methods → 16 service methods (1:1 mapping per CONTEXT D-02).
- HTTP fetch → direct Phase 4 service / Phase 3 repo call.
- **Class name `AdminEndUserService`** (NOT `AdminUserService`) per Pitfall 3 — avoid collision with `AdminAccountService` (admin-on-admin) and clearly name end-user operations.
- **D-02a discipline:** Phase 4 services keep their existing signatures. No `acting_admin_id` parameter. Admin-only audit happens at controller layer via `AdminAuditService.record(...)`.

**Plan:** 05-03.

---

#### `api_service/controllers/admin/dashboard.py` + `services/admin/dashboard_service.py` (NEW)

**Analogs:**
- Controller: `services/admin-service/src/controllers/dashboard.py` (198 lines — first 80 lines read above).
- Service: composed from `services/admin-service/src/gateways/user_management.py:50-89` (`UserStatsGateway` 5 methods) + Phase 4 `BillingRepository.stat_*` direct calls.

**Source `UserStatsGateway.fetch_dashboard_summary` shape (lines 50-60 of `gateways/user_management.py`):**
```python
async def fetch_dashboard_summary(self, start=None, end=None) -> dict:
    params: dict = {}
    if start is not None: params["start"] = start
    if end is not None: params["end"] = end
    return await self._get("/api/v1/internal/dashboard/summary", query_params=params or None)
```

**Target pattern:**
```python
# api_service/services/admin/dashboard_service.py — NEW
from sqlalchemy.ext.asyncio import AsyncSession
from api_service.repositories.user_repository import UserRepository
from api_service.repositories.billing_repository import BillingRepository
from api_service.repositories.call_log_repository import CallLogRepository

class AdminDashboardService:

    @staticmethod
    async def fetch_summary(db: AsyncSession, *, start=None, end=None) -> dict:
        # Single-query aggregate per CONTEXT <specifics>: dashboard summary聚合应单次查询+JOIN
        total_users = await UserRepository(db).count_all()
        total_metrics = await CallLogRepository(db).aggregate_summary_metrics(start=start, end=end)
        new_users_today, requests_today, revenue_today, cost_today = \
            await CallLogRepository(db).aggregate_today_metrics()
        return {
            "total_users": total_users,
            "total_requests": total_metrics["total_requests"],
            # ... fold in the same fields the gateway used to return
        }

    @staticmethod
    async def fetch_user_growth(db, *, start: str, end: str) -> list[dict]:
        return await UserRepository(db).get_user_growth_buckets(start, end)

    # ... 3 more methods: usage_trends, rpm_trend, tpm_trend
```

**Delta vs analogs:**
- 5 gateway methods → 5 service methods.
- HTTP fetch → direct repo aggregate.
- **CONTEXT specifics:** prefer single-query + JOIN for `fetch_summary` (avoid N+1). If `CallLogRepository.aggregate_summary_metrics` doesn't exist on Phase 3 repos, planner adds it as part of 05-03 (extension to repo).
- Controller (`controllers/admin/dashboard.py`): replace `_stats_gateway.X(...)` with `AdminDashboardService.X(db, ...)`; add `db: AsyncSession = Depends(get_db)` to handlers.

**Plan:** 05-03.

---

#### `api_service/controllers/admin/vouchers.py` + `services/admin/voucher_service.py` (NEW)

**Analogs:**
- Controller: `services/admin-service/src/controllers/vouchers.py` (135 lines — full file read above).
- Service: Phase 4 `services/voucher_service.py` (VoucherService — already exists per 04-PATTERNS.md) + admin-perspective wrapper.

**Source controller pattern (lines 39-77 — replace gateway+safe_audit_commit with service+inline audit):**
```python
# services/admin-service/src/controllers/vouchers.py:39-77 [VERIFIED]
@router.post("", response_model=VoucherCodeCreateResponse, summary="Generate voucher codes")
async def generate_voucher_codes(
    payload: GenerateVoucherCodesRequest, request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> VoucherCodeCreateResponse:
    data = await _gateway.generate_voucher_codes(...)   # DELETE
    ip_address, user_agent = get_request_meta(request)
    await safe_audit_commit(db, ...)                    # DELETE
```

**Target pattern (Pitfall 13 — inline audit):**
```python
from api_service.services.admin.voucher_service import AdminVoucherService

@router.post("", response_model=VoucherCodeCreateResponse, summary="Generate voucher codes")
async def generate_voucher_codes(
    payload: GenerateVoucherCodesRequest, request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> VoucherCodeCreateResponse:
    items = await AdminVoucherService.generate_batch(
        db, amount=payload.amount, count=payload.count,
        starts_at=payload.starts_at, expires_at=payload.expires_at,
        operator_admin=current_admin, remark=payload.remark,
    )
    ip_address, user_agent = get_request_meta(request)
    await AdminAuditService.record(
        db, actor_admin_id=current_admin.id, target_admin_id=None,
        action="generate_voucher_codes", resource_type="voucher_redemption_code",
        resource_id="batch", status="success",
        after_data={"amount": payload.amount, "count": payload.count, ...},
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()
    return VoucherCodeCreateResponse(data=VoucherCodeCreateData(items=items))
```

**Service shape (NEW):**
```python
# api_service/services/admin/voucher_service.py — NEW
from api_service.services.voucher_service import VoucherService  # Phase 4

class AdminVoucherService:
    @staticmethod
    async def generate_batch(db, *, amount, count, starts_at, expires_at, operator_admin, remark=None):
        return await VoucherService.generate_batch(
            db, amount=amount, count=count, starts_at=starts_at,
            expires_at=expires_at, remark=remark,
        )
    # 3 more methods: list, get, disable
```

**Delta vs analogs:**
- 4 gateway methods → 4 service methods.
- Phase 4 `VoucherService` provides the core CRUD; this admin wrapper is a thin pass-through (D-02a — admin-only checks live in controller `Depends(require_super_admin)` + audit happens in controller).
- Audit moved from `safe_audit_commit` inline to explicit `record + commit` (Pitfall 2 + 13).

**Plan:** 05-03.

---

#### `api_service/controllers/admin/route_monitor.py` + `services/admin/route_monitor_service.py` (NEW)

**Analogs:**
- Controller: `services/admin-service/src/controllers/route_monitor.py` (142 lines — first 60 lines read above).
- Service: `services/admin-service/src/gateways/route_monitor.py` (113 lines — read above; 4-method gateway).

**Source gateway shape (lines 27-75 of `gateways/route_monitor.py`):**
```python
async def list_requests(self, *, page=1, page_size=20, user_id=None, user_uid=None,
                        model_name=None, selected_model=None, ..., start=None, end=None) -> dict:
    qp: dict = {"page": page, "page_size": page_size}
    if user_id is not None: qp["user_id"] = user_id
    if user_uid: qp["user_uid"] = user_uid
    # ... 11 more conditional kwargs
    return await self._get("/api/v1/internal/route-monitor/requests", query_params=qp)
```

**Target pattern (NEW — direct `CallLogRepository` call):**
```python
# api_service/services/admin/route_monitor_service.py — NEW
from api_service.repositories.call_log_repository import CallLogRepository

class AdminRouteMonitorService:

    @staticmethod
    async def list_requests(
        db, *, page=1, page_size=20, user_id=None, user_uid=None,
        model_name=None, selected_model=None, provider_slug=None,
        routing_tier=None, status=None, score_min=None, score_max=None,
        request_id=None, input_hash=None, start=None, end=None,
    ):
        # Resolve user_uid → user_id if needed (admin can pass either)
        if user_uid and not user_id:
            user = await UserRepository(db).get_by_uid(user_uid)
            if not user: return [], 0
            user_id = int(user.id)
        return await CallLogRepository(db).list_requests(
            page=page, page_size=page_size, user_id=user_id,
            model_name=model_name, selected_model=selected_model,
            provider_slug=provider_slug, routing_tier=routing_tier,
            status=status, score_min=score_min, score_max=score_max,
            request_id=request_id, input_hash=input_hash, start=start, end=end,
        )
    # 3 more methods: get_request_detail, get_aggregates, get_compare
```

**Delta vs analogs:**
- 4 gateway methods → 4 service methods.
- HTTP fetch → direct `CallLogRepository` call (Phase 3 already merged `call_log_repository` per CONTEXT canonical refs).
- `user_uid` → `user_id` resolution happens at service boundary (CLAUDE.md user identity rule).
- Controller (`controllers/admin/route_monitor.py`): replace `_gateway.X(...)` with `AdminRouteMonitorService.X(db, ...)`; add `db: AsyncSession = Depends(get_db)` to handlers.

**Plan:** 05-03.

---

#### `api_service/controllers/admin/service_logs.py` + `services/admin/service_logs_service.py` (NEW)

**Analogs:**
- Controller: `services/admin-service/src/controllers/service_logs.py` (63 lines — full file read above).
- Service: `services/admin-service/src/gateways/service_logs.py` (137 lines — first 110 lines read above).

**Source gateway pattern (lines 17-110) — port verbatim except `_REMOTE_SERVICES`:**
```python
# services/admin-service/src/gateways/service_logs.py:17-21 [VERIFIED]
# SOURCE — 3 entries:
_REMOTE_SERVICES: list[tuple[str, str]] = [
    ("user-service", "USER_SERVICE_URL"),
    ("router-service", "ROUTER_SERVICE_URL"),
    ("inference-service", "INFERENCE_SERVICE_URL"),
]

# TARGET (D-03) — only inference remains:
_REMOTE_SERVICES: list[tuple[str, str]] = [
    ("inference-service", "INFERENCE_SERVICE_URL"),
]
```

**Local fetch (source lines 62-75) — port verbatim with name swap:**
```python
async def _fetch_local(service: str, params: dict) -> dict:
    buf = get_ring_buffer()
    if buf is None:
        return _result(service, reachable=True, entries=[], total=0, latest_seq=0)
    entries, total, latest_seq = buf.snapshot(
        after_seq=params.get("after_seq", 0),
        level=params.get("level"), since=params.get("since"),
        until=params.get("until"), search=params.get("search"),
        page=params.get("page", 1), page_size=params.get("page_size", 50),
    )
    return _result(service, reachable=True, entries=entries, total=total, latest_seq=latest_seq)


def _resolve_targets(services):
    all_targets = [("api-service", "")]    # was "admin-service" — pre-merge
    for svc_name, url_attr in _REMOTE_SERVICES:
        all_targets.append((svc_name, getattr(settings, url_attr)))
    if not services: return all_targets
    requested = set(services)
    return [(n, u) for n, u in all_targets if n in requested]
```

**Remote HMAC fetch (source lines 78-105) — port verbatim:**
```python
async def _fetch_remote(service: str, base_url: str, params: dict) -> dict:
    try:
        payload = await get_internal_json(           # ← from api_service.common.internal (05-01)
            base_url=base_url, target_service=service,
            path="/internal/logs",                    # O-3: verify path; may be /api/v1/internal/logs
            secret=settings.INTERNAL_SECRET,
            caller_service=settings.SERVICE_NAME,
            timeout=_LOG_FETCH_TIMEOUT,
            query_params=params, max_retries=0,
            retry_backoff_seconds=0,
            circuit_breaker_threshold=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD,
            circuit_breaker_cooldown_seconds=settings.INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )
        return _result(service, reachable=True, entries=payload.get("entries", []),
                       total=payload.get("total", 0),
                       latest_seq=payload.get("latest_seq", 0))
    except InternalServiceError as exc:
        logger.warning("Failed to fetch logs from %s: %s", service, exc)
        return _result(service, reachable=False, error=str(exc))
```

**Delta vs analogs:**
- **D-03:** delete `("user-service", "USER_SERVICE_URL")` and `("router-service", "ROUTER_SERVICE_URL")` from `_REMOTE_SERVICES`. Only inference-service remains.
- Rename local service label `"admin-service"` → `"api-service"` (merged process owns admin + user + router merged logs).
- Class wrap: source's `ServiceLogsGateway` (staticmethod-only class) → target `AdminServiceLogsService` with same `fetch_all` staticmethod (RESEARCH Pattern 6 skeleton).
- Imports rewrites: `from common.internal` → `from api_service.common.internal` (05-01 module); `from common.observability` → `from api_service.common.observability`.
- **O-3:** verify inference-service path is `/internal/logs` (source) vs `/api/v1/internal/logs` (likely current) during 05-03.
- New settings: `INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD=5`, `INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS=30` (RESEARCH Settings Gap).
- Controller (`controllers/admin/service_logs.py`): replace `ServiceLogsGateway.fetch_all(...)` with `AdminServiceLogsService.fetch_all(...)`. Port the merge+sort logic at controller layer verbatim (lines 45-62 of source).

**Plan:** 05-03.

---

#### Schemas: `user_management.py`, `route_monitor.py`, `service_logs.py`, `voucher.py`

**Analogs:** `services/admin-service/src/schemas/{user_management,route_monitor,service_logs,voucher}.py`.

**Delta vs analogs (same pattern as 05-02 schemas):**
- `AdminBaseResponse` → `BaseResponse` (Pitfall 8).
- `from schemas.common` → `from api_service.common.schemas`.
- `from common.api import PaginatedResponse` → `from api_service.common.api.pagination`.
- **CLAUDE.md user identity rule:** `user_management.py` response schemas use `user_uid: str` (NEVER `user_id: int`). Verify the source already follows this; if any `user_id: int` slips through, rename in this port.

**Plan:** 05-03.

---

## Shared Patterns

### Authentication (admin guards)

**Source:** `api_service/core/policies.py` (extended in 05-01 — see Pitfall 14 entry).

**Apply to:** every controller in `controllers/admin/`:

| Guard | Endpoints |
|-------|-----------|
| `require_active_admin` | All admin auth endpoints except `/login` and `/refresh`; all read endpoints in pools/model_catalog/users/dashboard/route_monitor/audit_logs |
| `require_super_admin` | All write endpoints in pools/model_catalog/routing_settings/admin_users/users (mutating)/vouchers/service_logs |

**One-line pattern:**
```python
current_admin: AdminUser = Depends(require_super_admin)
# or for read-only:
_current_admin: AdminUser = Depends(require_active_admin)
```

---

### Cookie Set/Clear (admin auth only)

**Source:** `services/admin-service/src/controllers/auth.py:38-70` (full block above).

**Apply to:** `controllers/admin/auth.py` only.

**Locked constants:**
```python
ADMIN_ACCESS_COOKIE = "admin_access_token"
ADMIN_REFRESH_COOKIE = "admin_refresh_token"
ADMIN_COOKIE_PATH = "/"                       # Pitfall O-1 / A1 — DO NOT use /api/v1/admin
```

**Phase 4 parity:** Phase 4 user-domain `controllers/auth.py` has `USER_ACCESS_COOKIE = "user_access_token"` at `path = "/"`. The cookie *name* is the namespacing axis; the path stays root.

---

### Audit Log Write (D-02b — explicit per mutation)

**Source:** `services/admin-service/src/services/routing_setting_service.py:84-99` + RESEARCH Pattern 2.

**Apply to:** every mutation endpoint in `controllers/admin/*` AND every mutation method in `services/admin/*`.

**Pattern (controller layer — preferred for proxy-elimination endpoints):**
```python
ip_address, user_agent = get_request_meta(request)
result = await SomeService.do_mutation(db, ...)
await AdminAuditService.record(
    db, actor_admin_id=current_admin.id, target_admin_id=None,
    action="<action_code>", resource_type="<resource>", resource_id=str(<id>),
    status="success",
    before_data=..., after_data=...,
    ip_address=ip_address, user_agent=user_agent,
)
await db.commit()
```

**Pattern (service layer — preferred for native admin services where the service owns the full mutation transaction, like `routing_setting_service.update_setting`):**
```python
# Inside the service method, after the mutation but before commit:
await AdminAuditService.record(db, ...)
await db.commit()
```

**Pitfall 2 resolution:** No `safe_audit_commit` wrapper. If `AdminAuditService.record` raises, the shared session rolls back the entire transaction (audit + business mutation). This is correct (transactional integrity in the merged service).

**Pitfall 13:** delete `services/admin-service/src/utils/audit.py` entirely; do NOT port it.

---

### Error Handling

**Source:** `api_service/common/core/exceptions.py` (Phase 1 baseline) + Pitfall 15 adds `AdminConflictException` (HTTP 409) + `AdminPermissionDeniedException` (HTTP 403).

**Apply to:** every admin service and controller — raise domain exceptions, let global handler map them.

**Common admin exception classes (port from admin-service `core/exceptions.py` → `common.core.exceptions`):**
- `AdminConflictException` (409 — e.g., email duplicate on create_admin)
- `AdminPermissionDeniedException` (403 — e.g., `require_super_admin` fails)

Plus shared classes already in `common.core.exceptions`: `AuthenticationException`, `InvalidCredentialsException`, `InvalidTokenException`, `TokenExpiredException`, `WeakPasswordException`, `NotFoundException`, `ValidationException`, `UserNotFoundException`, `ServiceUnavailableException`.

---

### Logging

**Source:** `api_service/common/observability.py:300+` — `log_event(logger, level, "eventName", **fields)` (Phase 4 04-PATTERNS.md identical).

**Apply to:** every admin service and controller.

**Pattern (port verbatim from admin-service auth_service.py:58, 148):**
```python
log_event(logger, logging.INFO, "adminLoginAttempt", email=email)
log_event(logger, logging.INFO, "adminLoginSuccess", email=email)
log_event(logger, logging.INFO, "adminPasswordChanged", uid=admin.uid)
```

---

### Transaction Boundary

**Source:** `services/admin-service/CLAUDE.md` (re-affirmed in system reminder above) + Phase 4 04-PATTERNS.md Transaction Boundary entry.

**Apply to:** every admin service method that writes to DB.

**Pattern (per CLAUDE.md "Service 层"):**
```python
@staticmethod
async def some_mutation(db: AsyncSession, ...) -> ...:
    repo = SomeRepository(db)
    # mutate
    repo.add(...)
    # audit
    await AdminAuditService.record(db, ...)
    # commit
    await db.commit()
```

**CPU-bound (bcrypt) discipline:** wrap in `asyncio.to_thread` via `hash_password_async` / `verify_password_async` from `api_service.common.security.password` (already async helpers).

---

### Cache Invalidation (D-05 — model_catalog)

**Source:** RESEARCH Pattern 3 + `api_service/common/infra/cache.py:22` `get_cache_redis`.

**Apply to:** every write method in `services/admin/model_catalog_service.py`.

**Pattern:**
```python
@staticmethod
async def _invalidate_cache() -> None:
    try:
        r = get_cache_redis()
        async for key in r.scan_iter(match="mc:*"):
            await r.delete(key)
    except Exception:
        logger.warning("model_catalog cache invalidation failed", exc_info=True)
```

**Hook sites** (call AFTER `await db.commit()`, fail-open): `create_vendor`, `update_vendor`, `delete_vendor`, `create_category`, `update_category`, `delete_category`, `create_model`, `update_model`, `disable_model`, `update_category_map`.

---

### Routing Config Version Signal (D-06)

**Source:** RESEARCH Pattern 4 + `api_service/common/infra/cache.py:22`.

**Apply to:** every write method in `services/admin/routing_setting_service.py`.

**Pattern:**
```python
ROUTING_CONFIG_VERSION_KEY = "routing_config:version"

@staticmethod
async def _bump_version() -> None:
    try:
        await get_cache_redis().incr(ROUTING_CONFIG_VERSION_KEY)
    except Exception:
        logger.warning("routing_config_version_bump_failed", exc_info=True)
```

**Hook sites** (call AFTER `await db.commit()`, fail-open): `update_setting`, `batch_update`.

---

### Service @staticmethod Convention

**Source:** root `CLAUDE.md` + admin-service `CLAUDE.md` (system reminder) + Phase 4 04-PATTERNS.md.

**Apply to:** every admin service file.

**Pattern:**
```python
class SomeAdminService:
    @staticmethod
    async def some_op(db: AsyncSession, *, kw1, kw2, ...) -> ResultModel:
        repo = SomeRepository(db)
        # ...
```

**No instance state.** No `__init__`. Helper functions (e.g., `_pool_item`, `_setting_item`) live at module level outside the class.

---

### Settings (config injection)

**Source:** `api_service/core/config.py` + RESEARCH Settings Gap table.

**Apply to:** every admin service. Never read env vars directly.

**Settings that must be added in 05-01:**
```python
BOOTSTRAP_SUPERADMIN_REQUIRE_ON_STARTUP: bool = True
BOOTSTRAP_SUPERADMIN_RESET_PASSWORD_IF_EXISTS: bool = False
BOOTSTRAP_SUPERADMIN_UPDATE_NAME_IF_EXISTS: bool = False
HEALTH_CHECK_TIMEOUT_SECONDS: float = 15.0
HEALTH_CHECK_LLM_PROBE_ENABLED: bool = True
HEALTH_CHECK_LLM_PROBE_MAX_TOKENS: int = 5
HEALTH_CHECK_RATE_LIMIT_DELAY: float = 0.5
INTERNAL_HTTP_CIRCUIT_BREAKER_THRESHOLD: int = 5
INTERNAL_HTTP_CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 30
```

**Already present (verified per RESEARCH):** `BOOTSTRAP_SUPERADMIN_ENABLED`, `BOOTSTRAP_SUPERADMIN_EMAIL`, `BOOTSTRAP_SUPERADMIN_PASSWORD`, `BOOTSTRAP_SUPERADMIN_NAME`, `PROVIDER_SECRET_MASTER_KEY`, `INFERENCE_SERVICE_URL`, `INFERENCE_SERVICE_SECRET`, `INTERNAL_SECRET`, `SERVICE_NAME`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `JWT_*`.

**Deleted:** `USER_SERVICE_URL`, `ROUTER_SERVICE_URL` (gateways removed).

---

### Snowflake worker_id

**Source:** root `CLAUDE.md` + Phase 2 baseline.

**Apply to:** admin domain — `worker_id=2` (already configured in Phase 2). No code change in Phase 5.

---

### CLAUDE.md User Identity Rule

**Source:** root `CLAUDE.md` "用户标识规范".

**Apply to:** every admin response schema referencing an end user.

**Rule:** Frontend admin responses use `user_uid: str` (NEVER `user_id: int`). Internal admin service code may receive `user_uid` from controller, resolve to `user_id: int` via `UserRepository.get_by_uid(uid)`, then call Phase 4 services with `user_id` (internal boundary).

---

## No Analog Found

None. Every Phase 5 file has a source analog — either a 1:1 admin-service port, a Phase 4 PATTERNS.md analog (cookie helpers, ARQ cron, lifespan registration shape, controller skeleton), or a composed pattern from two analogs (e.g., proxy-elimination services compose `gateways/*.py` method signatures with Phase 3 repo / Phase 4 service direct calls).

---

## Metadata

**Analog search scope:**
- `services/admin-service/src/{controllers,services,schemas,gateways,common,utils,core}/` — primary source for 8 service ports + 7 native controllers + 5 gateway-mapping references + 12 schemas + HMAC client
- `services/api-service/api_service/{repositories,common,core}/` — Phase 1–3 baseline (verified `admin_user_repository`, `audit_log_repository`, `pool_repository`, `model_catalog_repository`, `routing_setting_repository`, `call_log_repository`, `get_cache_redis`, `get_ring_buffer`, `cache_get_or_fetch`, `get_db_context`, lifespan `registry.register` shape)
- `.planning/phases/04-user-domain-controllers/04-PATTERNS.md` — sibling phase: cookie helpers, ARQ cron append shape, controller endpoint skeleton, lifespan priority discipline, test mocking style, `ApiResponse[T]` envelope, settings injection
- `services/api-service/tests/` — test mocking idiom

**Files scanned (Read tool, non-overlapping ranges):** 13 source files (admin-service controllers/services/gateways/schemas) + 5 api-service Phase 1–3 files (router, lifespan, observability, infra/cache) + 1 Phase 4 PATTERNS doc = 19 files.

**Pattern extraction date:** 2026-05-19

**Confidence by file class:**
- **HIGH** — `controllers/admin/auth.py`, `services/admin/auth_service.py`, `services/admin/bootstrap_service.py`, `services/admin/audit_service.py`, all 12 schemas, all native controllers in 05-02 (pools, model_catalog_admin, routing_settings, admin_users, audit_logs): line-for-line ports with explicit import-rewrite rules.
- **HIGH** — `common/schemas.py` (D-04 hoist): merge of two near-identical 35-40 line files into one with explicit unified-class naming (Pitfall 8).
- **MEDIUM-HIGH** — `services/admin/model_catalog_service.py` (D-05 NEW hook) and `services/admin/routing_setting_service.py` (D-06 NEW hook + Pitfall 4 exclusion): straightforward port + small hook addition, but each touch site must be wired (10 for D-05, 2 for D-06).
- **MEDIUM-HIGH** — `common/internal.py` HMAC sender port: 552-line verbatim port, but the dedupe step (move signing primitives to `common/http/internal_signing.py`) introduces non-trivial merge work with existing receiver-side `common/http/internal_auth.py`.
- **MEDIUM** — 5 NEW proxy-elimination services in 05-03 (`admin_user_service`, `dashboard_service`, `voucher_service`, `route_monitor_service`, `service_logs_service`): NEW composed code — analogs are the gateway method signatures + Phase 4 service / Phase 3 repo direct calls. Some new repo methods may be needed (e.g., `CallLogRepository.aggregate_summary_metrics` for dashboard summary).
- **MEDIUM** — test files: pattern is api-service's own mocking style (`unittest.mock.patch + AsyncMock`); no admin-service test scaffolding to mirror.

## PATTERN MAPPING COMPLETE
