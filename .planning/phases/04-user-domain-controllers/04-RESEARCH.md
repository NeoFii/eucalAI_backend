# Phase 4: User Domain Controllers - Research

**Researched:** 2026-05-19
**Domain:** Migration / refactor — port 4 FastAPI user-facing controllers + services + schemas + ARQ worker from `user-service` to merged `api-service`, with one behavior change (D-02: email send becomes ARQ-async).
**Confidence:** HIGH

## Summary

This research is a **migration guide**, not a greenfield FastAPI investigation. The source code (`services/user-service`) is the source of truth — Phase 4 must reproduce its behavior 1:1 except for D-02 (async email). The bulk of risk lies in five integration mismatches between source and target that the planner must address explicitly:

1. **Repository API mismatch** — `user-service` calls `SessionRepository`, `BalanceTxRepository`, `EmailCodeRepository`, etc. These classes **do not exist** in `api-service`. Phase 3 merged them into prefixed methods on `UserRepository` / `BillingRepository` / `VoucherRepository`. Every line of migrated service code that constructs a sub-repo must be rewritten to use the merged repo.
2. **JWT/password util path moved** — sources import from `common.utils.jwt` / `common.utils.password`; target placed them under `common/security/`. Every service-layer import line will need rewriting.
3. **Helper utilities not yet migrated** — `utils/email.py`, `utils/password.py` (password strength), `utils/api_key_policy.py` (allowed_models / allow_ips normalization) live in `user-service/src/utils/` and have no api-service home. Schema validators depend on them, so they must be migrated before schemas can be imported.
4. **Two cross-service gateways must be eliminated** — `model_catalog_gateway` (HTTP→admin-service) becomes a direct service call; `system_settings_gateway` (used by `/auth/me`) must be replaced with either a direct query of `RoutingSetting`/`system_settings` table OR a configuration constant fallback (CONTEXT.md is silent on this — flagged as Open Question O-1).
5. **ARQ Redis pool wiring** — `api-service` has no ARQ pool initialized in lifespan today; Phase 4 must add it. Settings already declare `WORKER_QUEUE_REDIS_URL` (db/1) and `arq>=0.26.0` is in pyproject. No external work needed besides wiring.

**Primary recommendation:** Plan 04-01 must include a "Wave 0" of foundational migrations (helper `utils/`, missing settings keys, ARQ pool lifespan + dependency) before the auth controller is touched. Plans 04-02 and 04-03 are then mechanical 1:1 ports against the now-available scaffolding.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Auth cookie set/clear (HTTP layer) | API / Backend (FastAPI controller) | — | Cookie manipulation is a transport-layer concern; service layer stays cookie-agnostic |
| JWT issue/decode/JTI | API / Backend (service via `common/security/jwt`) | — | Pure stateless utility, no DB |
| Session row + refresh_token_hash | Database / Storage (`user_sessions` table) | API / Backend (`AuthService`) | Refresh-token revocation requires server-side row; DB owns truth |
| Password strength check | API / Backend (`utils/password.check_password_strength`) | — | Pure validation, runs in Pydantic validator before reaching service |
| Email verification code lifecycle | Database / Storage (`email_verification_codes`) | API / Backend (`EmailService`) | DB row is canonical; service mediates create + verify + retry-locking |
| Email SMTP send | Background worker (ARQ) | — | **Behavior change (D-02)** — moved off the request thread |
| API Key hash + validation | API / Backend (`ApiKeyService`) | Database / Storage (`user_api_keys`) | sha256-only storage, no plaintext in DB |
| Balance ledger (consume/freeze/settle/topup/voucher) | Database / Storage (`SELECT…FOR UPDATE`) | API / Backend (`BalanceService`) | All wallet mutations gated by row lock — DB is the integrity boundary |
| Usage stats aggregation (chart endpoints) | API / Backend (`UsageStatService`) | Database / Storage (`api_call_logs` + `usage_stats`) | Read-heavy + bucket logic in service; DB provides raw rows |
| Model catalog read (list + detail) | API / Backend (`ModelCatalogService` user variant) | Cache / Storage (Redis db/2 + MySQL) | Two-tier cache; DB is fallback |
| `/auth/me` current_tpm | API / Backend (`UsageStatService.get_user_tpm_last_minute`) | Database / Storage (`api_call_logs`) | Sliding-window aggregate over last 60s |
| `system_settings.default_user_rpm` lookup | API / Backend (new helper) | Database / Storage (`routing_settings` table or constant) | See Open Question O-1 — gateway must be replaced |

## Standard Stack

All dependencies already declared in `services/api-service/pyproject.toml` (verified via `Read` of the file). No new installs required.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.115.0 | HTTP framework — controllers, dependency injection, cookies | Phase 1 baseline `[VERIFIED: pyproject.toml]` |
| pydantic | >=2.5.0 | Schema validation, ApiResponse envelope, EmailStr | Phase 1 baseline `[VERIFIED: pyproject.toml]` |
| sqlalchemy[asyncio] | >=2.0.25 | Async ORM, `SELECT … FOR UPDATE` row locks for balance | Phase 2 baseline `[VERIFIED: pyproject.toml]` |
| aiomysql | >=0.2.0 | MySQL async driver | Phase 2 baseline `[VERIFIED: pyproject.toml]` |
| arq | >=0.26.0 | ARQ async task queue (Redis db/1) | Already declared `[VERIFIED: pyproject.toml line 25]` |
| redis | >=5.0 | Async Redis client (cache + ARQ pool) | Already used by Phase 2 cache layer `[VERIFIED: pyproject.toml]` |
| python-jose[cryptography] | >=3.3.1 | JWT encode/decode (HS256) | Used by `common/security/jwt.py` `[VERIFIED: pyproject.toml]` |
| passlib[bcrypt] | >=1.7.4 | bcrypt password hashing | Used by `common/security/password.py` `[VERIFIED: pyproject.toml]` |
| email-validator | >=2.1.0 | `EmailStr` runtime validator for Pydantic schemas | Already declared `[VERIFIED: pyproject.toml line 12]` |

### Supporting (already imported by source — no new install)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `secrets` (stdlib) | — | API Key generation (`sk-` + 46 chars), verification code 6-digit, order_no random suffix | Throughout `api_key_service` / `email_service` / `topup_order_service` |
| `hashlib` (stdlib) | — | sha256 for API key hash + voucher hash + JWT jti | `ApiKeyService.create`, `VoucherService.hash_code`, `get_token_jti` |
| `smtplib` (stdlib) | — | SMTP send (wrapped in `asyncio.to_thread` until D-02 moves to ARQ) | `EmailService._send_email` only |
| `ipaddress` (stdlib) | — | API Key `allow_ips` CIDR validation | `utils/api_key_policy.py` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual cookie set via `Response.set_cookie` | `fastapi-jwt-auth` library | Source already uses raw `Response.set_cookie`; migrating to a library introduces churn and tighter coupling to a 3rd-party schema. **Reject.** |
| ARQ for email | `BackgroundTasks` (Starlette) | `BackgroundTasks` dies if the worker process dies after the response is sent; ARQ persists in Redis. D-02 already locks in ARQ. **Reject alternative.** |
| ApiResponse generic envelope | Plain dict returns | Source has 100+ uses of `ApiResponse[T]`; frontend depends on the `{code, message, data}` shape. **Keep envelope.** |
| Replace `python-jose` with `PyJWT` | — | python-jose already wired in `common/security/jwt.py`; switch has zero benefit during a 1:1 migration. **Reject.** |

**Installation:**
```bash
# No new installs needed — all dependencies present in api-service/pyproject.toml
# Verified versions (from pyproject.toml read 2026-05-19):
#   arq>=0.26.0, redis>=5.0, python-jose[cryptography]>=3.3.1,
#   passlib[bcrypt]>=1.7.4, bcrypt>=3.2.0,<4.0.0, email-validator>=2.1.0
```

**Version verification:** Skipped per Phase scope — this is a pure migration, not a dependency upgrade. Every package is reused from Phase 1/2.

## Package Legitimacy Audit

> No new packages are installed in Phase 4. All dependencies originate from Phase 1 (`pyproject.toml` baseline) and were audited there. The legitimacy gate is **N/A** for this phase.

| Package | Registry | Disposition |
|---------|----------|-------------|
| arq | PyPI | Already approved in Phase 1; published since 2017, 600k+ monthly downloads, samuelcolvin maintainer |
| (all others) | PyPI | Already approved in Phase 1 |

## Architecture Patterns

### System Architecture Diagram

```
Browser (Next.js console)
   │
   │  Cookie: user_access_token (HttpOnly, SameSite=strict|lax)
   │  Cookie: user_refresh_token (HttpOnly, /api/v1/auth/refresh-only ideal)
   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ FastAPI controller layer (api_service/controllers/{auth,keys,billing,model_catalog}) │
│   • Extract cookie / Bearer → Depends(get_current_user) → User              │
│   • Map User → user_id (int) for internal repositories                       │
│   • Build ApiResponse[T] envelope                                           │
└──────┬────────────────────────────────┬──────────────────────────┬────────┘
       │                                │                          │
       ▼                                ▼                          ▼
┌──────────────────┐         ┌────────────────────┐        ┌───────────────────┐
│  AuthService     │         │ BalanceService     │        │ EmailService      │
│  (staticmethod)  │         │ (SELECT FOR UPDATE)│        │ (D-02: enqueues   │
│                  │         │                    │        │  ARQ job, returns)│
└────┬──────┬──────┘         └─────────┬──────────┘        └─────────┬─────────┘
     │      │                          │                              │
     │      │  AsyncSession            │                              │ enqueue_job
     │      │                          │                              ▼
     ▼      ▼                          ▼                    ┌──────────────────┐
┌──────────────────────────────────────────────────────┐    │ ARQ Redis (db/1) │
│ Repositories (merged in Phase 3):                    │    │   • job queue    │
│   UserRepository (user+session+email_code)           │    │   • cron schedule│
│   ApiKeyRepository, BillingRepository (merged),      │    └──────────┬───────┘
│   VoucherRepository, ModelCatalogRepository          │               │
└──────────┬─────────────────────────────────┬─────────┘               │
           │                                 │                          │
           ▼                                 ▼                          ▼
┌──────────────────────┐         ┌───────────────────┐      ┌────────────────────┐
│  MySQL eucal_ai DB   │         │ Redis cache (db/2)│      │ ARQ worker process │
│  (single engine,     │         │   mc:* prefix     │      │   send_verification│
│  pool_size=5×4=20)   │         │   60s/300s TTL    │      │   _email + 4 crons │
└──────────────────────┘         └───────────────────┘      └─────────┬──────────┘
                                                                       │
                                                                       ▼ smtplib (sync, in thread)
                                                                ┌────────────────┐
                                                                │   SMTP server  │
                                                                └────────────────┘
```

**Reading the diagram:** A registration request enters via FastAPI, goes through `AuthService.register` → `UserRepository` → DB commit, and then the controller calls `EmailService.send_verification_code` which writes the verification_code row + **enqueues** an ARQ job. The HTTP response returns immediately. The ARQ worker process (separate from uvicorn) picks up the job and sends SMTP. The cron jobs (cleanup/aggregation/reconciliation) live entirely inside the worker process.

### Component Responsibilities

| File (target path) | Responsibility | Approximate Source Line Count |
|--------------------|----------------|-------------------------------|
| `api_service/controllers/auth.py` | 10 `/auth/*` endpoints + cookie set/clear helpers | ~390 lines |
| `api_service/controllers/keys.py` | 5 `/keys` endpoints (list/create/update/disable/delete) | ~110 lines |
| `api_service/controllers/billing.py` | 8 `/billing/*` endpoints | ~310 lines |
| `api_service/controllers/model_catalog.py` | 4 public read endpoints | ~55 lines |
| `api_service/services/auth_service.py` | Register/login/logout/refresh/verify/change/reset + session helpers | ~395 lines |
| `api_service/services/api_key_service.py` | API key CRUD + `validate_by_hash` (used by Phase 6 relay) | ~200 lines |
| `api_service/services/balance_service.py` | All wallet mutations (consume/freeze/settle/refund/topup/admin_adjust) | ~410 lines |
| `api_service/services/email_service.py` | Code generate + DB row + ARQ enqueue + verify-or-raise | ~150 lines (slightly shorter post-D-02) |
| `api_service/services/topup_order_service.py` | Manual top-up order create | ~85 lines |
| `api_service/services/usage_stat_service.py` | Stats aggregate + analytics + log list | ~340 lines |
| `api_service/services/voucher_service.py` | Generate/list/redeem voucher codes | ~190 lines |
| `api_service/services/model_catalog_service.py` (user variant) | List vendors/categories/models + get-by-slug + Redis cache | ~120 lines (new) |
| `api_service/schemas/auth.py` | 16 request/response models | ~225 lines |
| `api_service/schemas/keys.py` | ApiKeyItem/Create/Update | ~85 lines |
| `api_service/schemas/billing.py` | Balance/Topup/Voucher/Usage/CallLog/Analytics | ~190 lines |
| `api_service/schemas/model_catalog.py` | Read-only subset of admin schemas (no Create/Update — D-06) | ~70 lines |
| `api_service/schemas/common.py` | `ApiResponse[T]`, `DateTimeModel`, `AuthBaseResponse`, `AuthErrorResponse` | ~40 lines |
| `api_service/common/utils/email.py` | `normalize_email` | ~7 lines |
| `api_service/common/utils/password_policy.py` | `check_password_strength` (renamed to avoid clash with `security/password.py`) | ~70 lines |
| `api_service/common/utils/api_key_policy.py` | `normalize_allowed_models`, `normalize_allow_ips`, `is_model_allowed`, `is_ip_allowed` | ~75 lines |
| `api_service/core/policies.py` | `require_active_user` dependency wrapping `get_current_user` | ~20 lines |
| `api_service/core/worker.py` | `WorkerSettings` class | ~20 lines |
| `api_service/core/jobs.py` | 4 cron jobs + new `send_verification_email` + `build_redis_settings` + `on_worker_startup`/`shutdown` | ~170 lines |
| `api_service/core/arq_pool.py` (new) | Lifespan-managed `create_pool` + `get_arq_pool` accessor | ~30 lines |

### Recommended Project Structure (after Phase 4 completes)

```
api_service/
├── controllers/
│   ├── auth.py            # NEW — 10 /auth/* endpoints
│   ├── keys.py            # NEW — 5 /keys endpoints
│   ├── billing.py         # NEW — 8 /billing/* endpoints
│   └── model_catalog.py   # NEW — 4 public read endpoints
├── services/
│   ├── auth_service.py    # NEW
│   ├── api_key_service.py # NEW
│   ├── balance_service.py # NEW
│   ├── email_service.py   # NEW (enqueues ARQ)
│   ├── topup_order_service.py # NEW
│   ├── usage_stat_service.py  # NEW
│   ├── voucher_service.py # NEW
│   └── model_catalog_service.py # NEW (user-facing read variant)
├── schemas/
│   ├── common.py          # NEW (ApiResponse[T], DateTimeModel, AuthBaseResponse)
│   ├── auth.py            # NEW
│   ├── keys.py            # NEW
│   ├── billing.py         # NEW
│   └── model_catalog.py   # NEW (read-only subset; admin write schemas land in Phase 5)
├── core/
│   ├── arq_pool.py        # NEW — Redis pool lifespan + dependency
│   ├── policies.py        # NEW — require_active_user
│   ├── worker.py          # NEW — ARQ WorkerSettings
│   ├── jobs.py            # NEW — 4 cron jobs + send_verification_email
│   └── router.py          # MODIFY — include_router for new routers
└── common/
    └── utils/
        ├── email.py            # NEW (normalize_email)
        ├── password_policy.py  # NEW (check_password_strength; renamed to avoid security/password.py clash)
        └── api_key_policy.py   # NEW (normalize_*, is_*_allowed)
```

### Pattern 1: Cookie-Based JWT (Reproduce Source Verbatim)

**What:** Two-cookie setup — `user_access_token` (15min) + `user_refresh_token` (7d). HttpOnly + Secure + SameSite controlled by settings.

**When to use:** Every login path (register, login, login-with-code, refresh).

**Example (port from source — no modification recommended):**
```python
# Source: services/user-service/src/controllers/auth.py:55-89 [VERIFIED]
USER_ACCESS_COOKIE = "user_access_token"
USER_REFRESH_COOKIE = "user_refresh_token"
USER_COOKIE_PATH = "/"

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=USER_ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=USER_COOKIE_PATH,
    )
    response.set_cookie(
        key=USER_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=USER_COOKIE_PATH,
    )

def _clear_auth_cookies(response: Response) -> None:
    for key in (USER_ACCESS_COOKIE, USER_REFRESH_COOKIE):
        response.delete_cookie(
            key=key, path=USER_COOKIE_PATH,
            httponly=True, secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
        )
```

**Critical observations from source review:**
- `BaseServiceSettings` (api-service) already declares `COOKIE_SECURE: bool = True` and `COOKIE_SAMESITE: str = "strict"` with the same names as source. `[VERIFIED: api_service/common/config.py:57-58]`
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` defaults to 15, `JWT_REFRESH_TOKEN_EXPIRE_DAYS` defaults to 7. `[VERIFIED: api_service/common/config.py:53-54]`
- **Logout invalidation** — source revokes the session row by `token_jti` AND clears cookies. The blacklist module (`common/security/token_blacklist.py`) is **admin-only** per D-08 Phase 3 — user logout uses DB-row revocation only (no JWT blacklist). This is preserved in Phase 4.
- **Refresh rotation** — source rotates BOTH access and refresh tokens on every `/auth/refresh` call. `session.token_jti` and `session.refresh_token_hash` are updated in-place. `[VERIFIED: services/user-service/src/services/auth_service.py:236-240]` Preserve verbatim.

### Pattern 2: ARQ Pool in FastAPI Lifespan (NEW for api-service)

**What:** Initialize an `ArqRedis` pool from `WORKER_QUEUE_REDIS_URL` during lifespan startup; expose via a FastAPI dependency for controllers; close in shutdown.

**When to use:** Any controller that enqueues a background job. Currently only `email_service.send_verification_code` and `auth_service` paths (register/send-email-code/reset-password) need it.

**Example:**
```python
# api_service/core/arq_pool.py (NEW)
# Source pattern: standard FastAPI lifespan + ARQ create_pool [CITED: arq-docs.helpmanual.io]
from __future__ import annotations
from arq import create_pool
from arq.connections import ArqRedis
from urllib.parse import urlparse

from api_service.core.config import settings

_arq_pool: ArqRedis | None = None


def _build_redis_settings():
    from arq.connections import RedisSettings
    parsed = urlparse(settings.WORKER_QUEUE_REDIS_URL)
    database = int((parsed.path or "/0").lstrip("/") or 0)
    return RedisSettings(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        database=database,
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


async def init_arq_pool() -> None:
    global _arq_pool
    _arq_pool = await create_pool(_build_redis_settings())


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.close()
        _arq_pool = None


def get_arq_pool() -> ArqRedis:
    if _arq_pool is None:
        raise RuntimeError("ARQ pool not initialised — call init_arq_pool() first")
    return _arq_pool
```

```python
# api_service/main.py — register in LifespanRegistry (NEW)
async def _init_arq() -> None:
    from api_service.core.arq_pool import init_arq_pool
    await init_arq_pool()

async def _shutdown_arq() -> None:
    from api_service.core.arq_pool import close_arq_pool
    await close_arq_pool()

registry.register("arq_pool", init_fn=_init_arq, shutdown_fn=_shutdown_arq, priority=40)
```

```python
# Usage inside email_service (controller-or-service-side enqueue)
from api_service.core.arq_pool import get_arq_pool

async def send_verification_code(db, email, purpose):
    # ... validate + insert code row + commit ...
    pool = get_arq_pool()
    await pool.enqueue_job(
        "send_verification_email",
        email, code, purpose,
        _job_try=1,
    )
```

**Why module-global accessor not `Depends`:** Source pattern (`get_redis()`, `get_cache_redis()`) uses module-global accessor in `api_service/common/infra/redis.py` and `cache.py`. Stays consistent with Phase 2's choice. `[VERIFIED: api_service/common/infra/redis.py:16-19]`

### Pattern 3: Service Layer @staticmethod (Source Convention)

**What:** All service classes use `@staticmethod` methods, `db: AsyncSession` as the first parameter. Module-level singletons (email_service) are converted to staticmethod where stateless; SMTP config is moved into the ARQ job (no instance state needed).

**Why:** Mandated by `services/user-service/CLAUDE.md` Service 层 section. Already enforced in Phase 3 dependencies. `[VERIFIED: user-service CLAUDE.md]`

**Migration rule for `email_service`:**
- Source has `email_service = EmailService()` module-level instance.
- D-02 makes it stateless (config read from `settings` inside ARQ job).
- Convert to `class EmailService:` with `@staticmethod` methods + no `__init__`. Drop the module-level instance.

### Pattern 4: SELECT … FOR UPDATE for All Wallet Mutations

**What:** Every method in `BalanceService` that touches `user.balance` / `user.frozen_amount` uses `for_update=True` when loading the User row.

**When:** consume, freeze, settle, refund, topup, admin_adjust, voucher redeem.

**Example (from source):**
```python
# Source: services/user-service/src/services/balance_service.py:60 [VERIFIED]
user = await BalanceService._get_user(db, user_id, for_update=True)
# ...
user.balance -= cost
# ... commit
```

`UserRepository.get_by_id(user_id, for_update=True)` already supports this `[VERIFIED: api_service/repositories/user_repository.py:37-41]`.

### Pattern 5: ref_id Idempotency Key

**What:** Every balance transaction insert is preceded by `BalanceTxRepository.exists_by_ref(tx_type, ref_type, ref_id)` to short-circuit duplicate writes. Voucher uses `str(code.id)`; api_call uses `request_id`; topup uses `order_no`.

**Migration note:** In api-service, `BalanceTxRepository(db)` no longer exists. Source code reads `tx_repo = BalanceTxRepository(db)` → must rewrite to `billing_repo = BillingRepository(db)` and method name changes from `exists_by_ref(...)` to `exists_by_ref(...)` (same name, on merged repo). Adding TX rows: `tx_repo.add(BalanceTransaction(...))` → `billing_repo.add_tx(BalanceTransaction(...))`. `[VERIFIED: api_service/repositories/billing_repository.py:37-50]`

### Pattern 6: Redis Cache with Fail-Open Fetch

**What:** Use the existing `cache_get_or_fetch(key, fetch, ttl_seconds)` helper from Phase 2.

**When:** Model catalog reads (mc:vendors, mc:categories, mc:models:{hash}, mc:model:{slug}).

**Example (port from `gateways/model_catalog.py`, just swap the HTTP `_fetch` for a direct service call):**
```python
# api_service/services/model_catalog_service.py — NEW
from api_service.common.infra.cache import cache_get_or_fetch
from api_service.repositories.model_catalog_repository import (
    ModelCatalogRepository, ModelCategoryRepository, ModelVendorRepository,
)

_CACHE_PREFIX = "mc:"
_VENDORS_TTL = 300
_CATEGORIES_TTL = 300
_MODELS_LIST_TTL = 120
_MODEL_DETAIL_TTL = 300


class ModelCatalogReadService:
    @staticmethod
    async def list_vendors(db, *, page=1, page_size=100):
        cache_key = f"{_CACHE_PREFIX}vendors:{page}:{page_size}"

        async def _fetch():
            vendors, total = await ModelVendorRepository(db).list_vendors(
                page=page, page_size=page_size, active_only=True,
            )
            return {
                "items": [VendorBrief.model_validate(v).model_dump() for v in vendors],
                "total": total, "page": page, "page_size": page_size,
            }
        return await cache_get_or_fetch(cache_key, _fetch, _VENDORS_TTL)
```

`cache_get_or_fetch` already serializes via `json.dumps` and is fail-open on Redis errors `[VERIFIED: api_service/common/infra/cache.py:45-66]`. **Do not use msgpack** — JSON keeps human readability, the helper is already wired, and payloads are small (<5KB per cached entry).

### Anti-Patterns to Avoid

- **Creating ARQ pool per request.** Source pattern uses module-global accessor; do the same. Anti-pattern documented in `[CITED: davidmuraya.com/blog/fastapi-arq-retries]`.
- **Skipping the SELECT FOR UPDATE row lock.** Wallet operations without the lock will produce drift detectable by the `reconcile_balance_ledger` cron — and you'll find out only days later in logs.
- **Returning plaintext API key on list/get.** Source returns plaintext only once on creation (D-02 of source spec). The model stores only `key_hash`. **Verify the migrated `ApiKeyItem` does NOT include `key`** — it should expose only `key_prefix`. `[VERIFIED: schemas/keys.py:15-31]`
- **Inlining `int(current_user.id)` calls.** Source does this everywhere because controllers receive `User` but service layer takes `user_id: int`. Reproduce verbatim — refactoring is out of scope.
- **Returning database-internal `user_id: int` to the frontend.** Root `CLAUDE.md` 用户标识规范 forbids this. Source already complies (responses only use `uid: str`). Verify nothing slips through during the port.
- **Using `Response.set_cookie` with `samesite="none"` without `Secure`.** Browsers reject this combo. Settings default to `"strict"` which is safe.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Generic API envelope | Custom `dict` returns from every endpoint | `ApiResponse[T]` from `schemas/common.py` (port from source) | Frontend expects `{code, message, data}`; consistent OpenAPI schema |
| Pagination payload | Custom dict per endpoint | `PaginatedResponse[T]` from `api_service/common/api/pagination.py` (already present, Phase 2) | Already wired, `from_result` helper exists |
| Async password hashing | `await asyncio.to_thread(pwd_context.hash, ...)` inline | `hash_password_async` / `verify_password_async` from `common/security/password.py` | Wrapper already exists `[VERIFIED]` |
| JWT JTI computation | Manual sha256 | `get_token_jti(token)` from `common/security/jwt.py` | Already wired `[VERIFIED]` |
| Datetime ISO formatting in JSON | Override JSON encoder per schema | `DateTimeModel` base via `@model_serializer(mode="wrap")` from `schemas/common.py` | Source pattern, frontend already consumes it `[VERIFIED: user-service/src/schemas/common.py]` |
| Cache get-then-set with stampede protection | Manual cache miss handling | `cache_get_or_fetch(key, fetch_fn, ttl)` from `common/infra/cache.py` | Helper exists with fail-open; no need for distributed lock at this load level `[VERIFIED]` |
| Redis pool (db/1 for ARQ) | Build a 4th Redis pool | Use ARQ's own `create_pool` from `WORKER_QUEUE_REDIS_URL` — ARQ has its own pool semantics | Mixing ARQ's pool with the generic Redis pool wastes resources |
| ARQ retry with backoff | Custom retry decorator | `raise Retry(defer=ctx['job_try'] * N)` inside the job function | Native ARQ pattern `[CITED: arq-docs.helpmanual.io]` |
| SMTP retry on transient failure | Custom retry loop in service | Let ARQ retry the whole job (max_tries=3 recommended for SMTP) | Cleaner separation; ARQ already serializes job retry state |
| Verification code lock-out after N errors | New rate limiter | Source already implements via `error_count` + `locked_until` columns on `email_verification_codes` table | Reuse — schema already migrated in Phase 3 |
| Voucher idempotency | UUID dedup table | `ref_type='voucher_code' + ref_id=str(code.id)` on `balance_transactions` | Already implemented in source |

**Key insight:** Phase 4 is a port, not a redesign. Every "should we build X?" question has the same answer: *look at the source first*. If source has it, port it; if source doesn't have it, do not invent it.

## Runtime State Inventory

This phase is a 1:1 controller/service migration. Code lives in a new directory tree but reads/writes the same database tables. Most state categories are inapplicable, but the migration introduces new runtime state that must be tracked.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None new. Phase reuses `users`, `user_sessions`, `email_verification_codes`, `user_api_keys`, `balance_transactions`, `topup_orders`, `usage_stats`, `api_call_logs`, `voucher_redemption_codes`, `model_catalog`, `model_vendor`, `model_category`, `model_catalog_category_map` — all present in Phase 3 baseline migration. | None — schema unchanged. |
| Live service config | None — D-02 keeps SMTP config in env vars (read inside ARQ job). | None. |
| OS-registered state | The ARQ worker is a new long-running process. Deployment must register it (systemd unit, pm2 entry, supervisord, or Docker compose service) using command `arq api_service.core.worker.WorkerSettings`. This is **a deployment concern flagged for Phase 10** — Phase 4 only ensures the worker module exists and is runnable. | Document the worker command in Phase 4 plan output (README or deployment notes); the actual service-registration belongs to Phase 10. |
| Secrets/env vars | `WORKER_QUEUE_REDIS_URL` (already in settings ✓), `SMTP_HOST/PORT/USER/PASSWORD/TLS/FROM` (already in settings ✓), `JWT_SECRET_KEY` (already in settings ✓), **NEW required**: `CODE_DAILY_SEND_LIMIT`, `MAX_CODE_ERRORS`, `CODE_ERROR_LOCK_HOURS`, `LOGIN_LOCK_DURATION_HOURS`, `VERIFICATION_CODE_RETENTION_DAYS`, `DEFAULT_USER_RPM`, `MIN_TOPUP_AMOUNT`, `MAX_TOPUP_AMOUNT`, `USER_WORKER_CONCURRENCY`, `USER_JOB_TIMEOUT_SECONDS`. See **Settings Gap** table below. | Add to `api_service/core/config.py` with same defaults as source. |
| Build artifacts | None. `pip install -e .` already covered by Phase 1. The new `arq` console-script entrypoint is provided by the ARQ package itself; no extra build step. | None. |

**Settings Gap (must add to `ApiServiceSettings` before plans 04-01 can run):**

| Setting | Default | Source line |
|---------|---------|-------------|
| `LOGIN_LOCK_DURATION_HOURS` | 1 | `user-service/src/core/config.py:32` |
| `MAX_CODE_ERRORS` | 5 | `user-service/src/core/config.py:33` |
| `CODE_ERROR_LOCK_HOURS` | 24 | `user-service/src/core/config.py:34` |
| `CODE_DAILY_SEND_LIMIT` | 3 | `user-service/src/core/config.py:35` |
| `VERIFICATION_CODE_RETENTION_DAYS` | 7 | `user-service/src/core/config.py:39` |
| `MIN_TOPUP_AMOUNT` | 1_000_000 | `user-service/src/core/config.py:28` |
| `MAX_TOPUP_AMOUNT` | 10_000_000_000 | `user-service/src/core/config.py:29` |
| `USER_WORKER_CONCURRENCY` | 5 | `user-service/src/core/config.py:37` |
| `USER_JOB_TIMEOUT_SECONDS` | 300 | `user-service/src/core/config.py:38` |
| `DEFAULT_USER_RPM` | 20 | `user-service/src/core/config.py:51` (overlap with existing `RATE_LIMIT_DEFAULT_USER_RPM` — see Open Question O-1) |

## Common Pitfalls

### Pitfall 1: Repository Sub-Class Imports Will Fail
**What goes wrong:** Source code imports like `from repositories import SessionRepository, EmailCodeRepository, BalanceTxRepository, TopupOrderRepository, UsageStatRepository` — none of these classes exist in api-service. Phase 3 merged them into the parent repos with prefixed methods.
**Why it happens:** Phase 3 D-04 merged sub-repos into `UserRepository` / `BillingRepository`. The merge changed method names: `session_repo.get_by_token_jti(jti)` → `user_repo.get_session_by_token_jti(jti)`; `tx_repo.add(...)` → `billing_repo.add_tx(...)`; etc.
**How to avoid:** Plan 04-01 must include a **method-name rewrite checklist** for every service line that touches a sub-repo. See the **Repository Method Translation Table** below.
**Warning signs:** Import errors at startup; AttributeError on a repo when running a unit test.

**Repository Method Translation Table (CRITICAL — planner MUST embed):**

| Source call (user-service) | Target call (api-service) | Source repo class | Notes |
|----------------------------|---------------------------|-------------------|-------|
| `SessionRepository(db).get_by_token_jti(jti)` | `UserRepository(db).get_session_by_token_jti(jti)` | merged | |
| `SessionRepository(db).list_active_for_user(uid)` | `UserRepository(db).list_active_sessions_for_user(uid)` | merged | |
| `SessionRepository(db).revoke(session)` | `UserRepository(db).revoke_session(session)` | merged | |
| `session_repo.add(session)` | `user_repo.add_session(session)` | merged | |
| `EmailCodeRepository(db).count_created_since(...)` | `UserRepository(db).email_code_count_created_since(...)` | merged | |
| `EmailCodeRepository(db).latest_for_email(...)` | `UserRepository(db).email_code_latest_for_email(...)` | merged | |
| `EmailCodeRepository(db).latest_unused_for_email(..., for_update=True)` | `UserRepository(db).email_code_latest_unused_for_email(..., for_update=True)` | merged | |
| `EmailCodeRepository(db).list_unused_for_email(...)` | `UserRepository(db).email_code_list_unused_for_email(...)` | merged | |
| `EmailCodeRepository(db).delete(record)` | `await UserRepository(db).email_code_delete(record)` | merged | Note: now async |
| `repo.add(verification)` (email code) | `UserRepository(db).email_code_add(verification)` | merged | |
| `BalanceTxRepository(db).exists_by_ref(...)` | `BillingRepository(db).exists_by_ref(...)` | merged | Same method name |
| `BalanceTxRepository(db).add(tx)` | `BillingRepository(db).add_tx(tx)` | merged | |
| `BalanceTxRepository(db).list_for_user(...)` | `BillingRepository(db).list_tx_for_user(...)` | merged | |
| `BalanceTxRepository(db).list_all(...)` | `BillingRepository(db).list_tx_all(...)` | merged | |
| `TopupOrderRepository(db).get_for_user_by_order_no(...)` | `BillingRepository(db).topup_get_for_user_by_order_no(...)` | merged | |
| `TopupOrderRepository(db).list_for_user(...)` | `BillingRepository(db).topup_list_for_user(...)` | merged | |
| `TopupOrderRepository(db).list_all(...)` | `BillingRepository(db).topup_list_all(...)` | merged | |
| `topup_repo.add(order)` | `billing_repo.topup_add(order)` | merged | |
| `UsageStatRepository(db).get_user_tpm_last_minute(uid)` | `BillingRepository(db).stat_get_user_tpm_last_minute(uid)` | merged | |
| `UsageStatRepository(db).get_user_stats(...)` | `BillingRepository(db).stat_get_user_stats(...)` | merged | |
| `UsageStatRepository(db).get_all_stats(...)` | `BillingRepository(db).stat_get_all_stats(...)` | merged | |
| `UsageStatRepository(db).list_usage_logs(...)` | `BillingRepository(db).stat_list_usage_logs(...)` | merged | |
| `UsageStatRepository(db).list_analytics_logs(...)` | `BillingRepository(db).stat_list_analytics_logs(...)` | merged | |
| `UsageStatRepository(db).list_logs_for_hour(...)` | `BillingRepository(db).stat_list_logs_for_hour(...)` | merged | |
| `UsageStatRepository(db).get_bucket(...)` | `BillingRepository(db).stat_get_bucket(...)` | merged | |
| `repo.add(bucket)` (UsageStat) | (no per-row helper found — use `billing_repo.session.add(bucket)`) | merged | Verify in `usage_stat_service` port |
| `VoucherRedemptionCodeRepository(db).get_by_id(...)` | `VoucherRepository(db).get_by_id(...)` | renamed only | Class renamed; method same |
| `VoucherRedemptionCodeRepository(db).get_by_hash(...)` | `VoucherRepository(db).get_by_hash(...)` | renamed only | |
| `VoucherRedemptionCodeRepository(db).list_for_admin(...)` | `VoucherRepository(db).list_for_admin(...)` | renamed only | |
| `VoucherRedemptionCodeRepository(db).list_for_user_redemptions(...)` | `VoucherRepository(db).list_for_user_redemptions(...)` | renamed only | |
| `UserRepository` (most methods) | unchanged | merged | `get_by_email`, `get_by_uid`, `get_by_id(..., for_update=...)`, `add`, etc. all preserved |
| `ApiKeyRepository` (all methods) | unchanged | unchanged | `list_for_user`, `count_for_user`, `get_owned_key`, `get_by_hash`, `disable_all_for_user` all preserved |

### Pitfall 2: Import Path Drift (jwt, password, common.utils → common.security)
**What goes wrong:** Source imports `from common.utils.jwt import create_access_token`. In api-service, this lives at `from api_service.common.security.jwt import create_access_token`. Wholesale `sed` over the source files will produce broken imports.
**Why it happens:** Phase 1 reorganized the common layer (D-02). `common/utils/` now holds only timezone + snowflake + nanoid; security utilities moved to `common/security/`.
**How to avoid:** Build the import-rewrite map below into plan 04-01. Run `grep -rn "from common\." migrated_file.py` as a final pre-commit check.
**Warning signs:** `ModuleNotFoundError: No module named 'common.utils.jwt'`.

**Import Translation Table:**

| Source import | Target import |
|---------------|---------------|
| `from common.utils.jwt import ...` | `from api_service.common.security.jwt import ...` |
| `from common.utils.password import hash_password_async, verify_password_async, hash_password` | `from api_service.common.security.password import hash_password_async, verify_password_async, hash_password` |
| `from common.utils.nanoid_uid import generate_nanoid_uid` | `from api_service.common.utils.nanoid_uid import generate_nanoid_uid` |
| `from common.utils.snowflake import generate_snowflake_id` | `from api_service.common.utils.snowflake import generate_snowflake_id` |
| `from common.utils.timezone import now, to_shanghai_naive, format_iso` | `from api_service.common.utils.timezone import now, to_shanghai_naive, format_iso` |
| `from common.observability import log_event, set_uid` | `from api_service.common.observability import log_event, set_uid` |
| `from common.core.exceptions import ...` | `from api_service.common.core.exceptions import ...` |
| `from common.db import ListParams, PaginatedResult` | `from api_service.common.infra.db.query import ListParams, PaginatedResult` |
| `from common.api import PaginatedResponse` | `from api_service.common.api.pagination import PaginatedResponse` |
| `from common.cache import cache_get_or_fetch` | `from api_service.common.infra.cache import cache_get_or_fetch` |
| `from core.config import settings` | `from api_service.core.config import settings` |
| `from core.dependencies import get_db_session` | `from api_service.core.db import get_db` (Phase 2 standard name) |
| `from core.policies import require_active_user` | `from api_service.core.policies import require_active_user` (NEW — must create) |
| `from models import ...` | `from api_service.models import ...` |
| `from repositories import ...` | `from api_service.repositories.* import ...` (or `from api_service.repositories import ...` via `__init__.py`) |
| `from schemas import ...` | `from api_service.schemas.{auth,billing,keys,model_catalog,common} import ...` |
| `from services.X import Y` | `from api_service.services.X import Y` |
| `from utils.email import normalize_email` | `from api_service.common.utils.email import normalize_email` (NEW — must create) |
| `from utils.password import check_password_strength` | `from api_service.common.utils.password_policy import check_password_strength` (NEW — renamed) |
| `from utils.api_key_policy import ...` | `from api_service.common.utils.api_key_policy import ...` (NEW — must create) |
| `from gateways.system_settings import system_settings_gateway` | **DELETE** — replace with config constant or direct DB read; see O-1 |
| `from gateways.model_catalog import model_catalog_gateway` | **DELETE** — replace with `ModelCatalogReadService` direct call |

### Pitfall 3: `get_db_session` vs `get_db` Name Drift
**What goes wrong:** Source uses `Depends(get_db_session)`; api-service Phase 2 calls it `get_db`.
**Why it happens:** Phase 2 renamed it during scaffolding consolidation.
**How to avoid:** Global search-replace `get_db_session` → `get_db` after copying source controllers.
**Warning signs:** `ImportError: cannot import name 'get_db_session'`.

### Pitfall 4: `email_service` is a Module Singleton, Plan Must Convert
**What goes wrong:** Source `email_service = EmailService()` is consumed as `email_service.get_valid_code_or_raise(...)`. Auth service has multiple call sites.
**Why it happens:** Source uses an instance; D-02 + Phase 4 service-layer convention says staticmethod.
**How to avoid:** Convert to `class EmailService:` with `@staticmethod` methods + drop the `__init__` (SMTP config gets read from settings inside the ARQ job, not stored on the instance). Update all callers from `email_service.X(...)` to `EmailService.X(...)`.
**Warning signs:** Test fails because mock was patched on the instance attribute, not the class.

### Pitfall 5: ARQ Worker DB Engine Initialization
**What goes wrong:** The ARQ worker is a separate process from uvicorn. It has its own event loop and **does NOT inherit the engine** that uvicorn's lifespan created. The worker must call `create_engine(...)` + `init_session_factory()` in its `on_startup` hook (source does this in `services/user-service/src/core/jobs.py:39-49`).
**Why it happens:** ARQ workers run via `arq api_service.core.worker.WorkerSettings`, completely separate from `uvicorn`.
**How to avoid:** Port the entire `on_worker_startup` / `on_worker_shutdown` block verbatim. Verify the worker can boot in isolation with `arq api_service.core.worker.WorkerSettings --check` (dry-run).
**Warning signs:** Worker logs say "engine not initialised"; first job fails with `RuntimeError`.

### Pitfall 6: Cookie Path Restriction on Refresh Token
**What goes wrong:** Source sets refresh-token cookie path to `"/"` (broad). A stricter pattern is `path="/api/v1/auth/refresh"` — but **don't change it** during migration; doing so will break the existing browser cookies on first deploy.
**Why it happens:** Tempting micro-optimization during port.
**How to avoid:** Keep `USER_COOKIE_PATH = "/"`. Note as deferred improvement.
**Warning signs:** Phantom "logged out" reports after deploy.

### Pitfall 7: Pydantic V2 `@model_serializer(mode="wrap")` Mutates Dict — Must Not Modify Original
**What goes wrong:** Source's `DateTimeModel` iterates `list(data.items())` then mutates `data[key]`. This is safe because of the `list(...)` copy. If you "tidy up" the loop to iterate `data.items()` directly, you'll get `RuntimeError: dictionary changed size during iteration` on schemas with many datetime fields.
**Why it happens:** Refactoring fingers.
**How to avoid:** Port `schemas/common.py` verbatim, do not lint-clean the loop.
**Warning signs:** Tests pass locally but production hits RuntimeError on a list with many items.

### Pitfall 8: `api_call_log_repository._exclude_invalid_model` is Duplicated
**What goes wrong:** Phase 3 noted that `_exclude_invalid_model()` was duplicated in `call_log_repository.py` to avoid circular imports `[VERIFIED: STATE.md decisions]`. Source `usage_stat_service.py` references `error_code='invalid_model'` filtering. The migrated service must use `BillingRepository.stat_list_analytics_logs` / `stat_list_logs_for_hour` which already embed this filter `[VERIFIED: api_service/repositories/billing_repository.py:259-277]`.
**Why it happens:** Source repo had the filter inline at the repo layer; api-service kept that boundary correctly.
**How to avoid:** When porting `usage_stat_service.py`, do NOT re-add the `error_code` filter in the service — the repo already does it.
**Warning signs:** Aggregates double-filter and return empty when they shouldn't.

### Pitfall 9: ARQ Job Function Name Must Match Worker Registration
**What goes wrong:** Enqueue via `pool.enqueue_job("send_verification_email", ...)` requires that the WorkerSettings.functions list registers a function literally named `send_verification_email`. ARQ uses the function's `__name__` attribute as the lookup key. If you rename the function, queued jobs become unresolvable and stay forever in Redis.
**Why it happens:** Rename refactor without updating both sides.
**How to avoid:** Lock the job name as a module-level constant `_JOB_SEND_VERIFICATION_EMAIL = "send_verification_email"` and reference it on both sides.
**Warning signs:** ARQ worker log: `Function 'send_verification_email' not found`.

### Pitfall 10: Voucher Hash Normalization is Case-Insensitive
**What goes wrong:** Source `VoucherService.normalize_code` lowercases + strips before hashing. If a controller-level Pydantic validator also lowercases, you get a no-op; but if the controller passes the raw user input untouched, the service still normalizes. Either way, ensure no second normalization round-trip drops characters.
**How to avoid:** Keep `VoucherRedeemRequest.code: str = Field(..., min_length=4, max_length=64)` without a `to_lower` validator. Let `VoucherService.normalize_code` be the single source of truth.

## Code Examples

### Register flow — verified end-to-end (port verbatim)
```python
# Source: services/user-service/src/services/auth_service.py:59-111 [VERIFIED]
@staticmethod
async def register(db: AsyncSession, data: RegisterRequest) -> User:
    email = normalize_email(data.email)
    user_repo = UserRepository(db)
    if await user_repo.get_by_email(email):
        raise EmailAlreadyExistsException()
    ok, msg = check_password_strength(data.password, lang=data.lang)
    if not ok:
        raise WeakPasswordException(detail=msg)
    code_record = await EmailService.get_valid_code_or_raise(
        db, email, data.verification_code, "register",
    )
    uid = generate_nanoid_uid()
    password_hash = await hash_password_async(data.password)
    snapshot_rpm = settings.DEFAULT_USER_RPM  # see O-1 (gateway removed)
    user = User(uid=uid, email=email, password_hash=password_hash,
                status=1, email_verified_at=now(), rpm_limit=snapshot_rpm)
    user_repo.add(user)
    EmailService.mark_code_used(code_record)
    await db.commit()
    await db.refresh(user)
    return user
```

### Email service after D-02 (NEW — async enqueue)
```python
# api_service/services/email_service.py — NEW
import secrets
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.core.exceptions import (
    CodeExpiredException, CodeNotFoundException, InvalidCodeException,
)
from api_service.common.security.password import hash_password_async, verify_password_async
from api_service.common.utils.email import normalize_email
from api_service.common.utils.timezone import now
from api_service.core.arq_pool import get_arq_pool
from api_service.core.config import settings
from api_service.models import EmailVerificationCode
from api_service.repositories.user_repository import UserRepository


_JOB_SEND_VERIFICATION_EMAIL = "send_verification_email"


class EmailService:
    @staticmethod
    def generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    async def send_verification_code(db: AsyncSession, email: str, purpose: str = "register") -> tuple[bool, str]:
        email = normalize_email(email)
        repo = UserRepository(db)
        today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        count = await repo.email_code_count_created_since(email, purpose, today_start)
        if count >= settings.CODE_DAILY_SEND_LIMIT:
            return False, "Daily verification code limit reached"

        latest = await repo.email_code_latest_for_email(email, purpose)
        if latest and latest.locked_until and now() < latest.locked_until:
            return False, "Verification code input is temporarily locked"

        code = EmailService.generate_code()
        expires_at = now() + timedelta(minutes=settings.EMAIL_CODE_EXPIRE_MINUTES)

        old_codes = await repo.email_code_list_unused_for_email(email, purpose)
        for old_code in old_codes:
            await repo.email_code_delete(old_code)

        verification = EmailVerificationCode(
            email=email, code_hash=await hash_password_async(code),
            purpose=purpose, expires_at=expires_at,
        )
        repo.email_code_add(verification)
        await db.commit()

        # D-02: enqueue background send
        pool = get_arq_pool()
        await pool.enqueue_job(_JOB_SEND_VERIFICATION_EMAIL, email, code, purpose)
        return True, "queued"

    @staticmethod
    async def get_valid_code_or_raise(db: AsyncSession, email: str, code: str, purpose: str = "register"):
        # ... port verbatim from source, replacing EmailCodeRepository with UserRepository.email_code_* methods ...
```

### ARQ job — send_verification_email (NEW)
```python
# api_service/core/jobs.py — NEW addition
import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from arq import Retry

from api_service.core.config import settings

logger = logging.getLogger(__name__)


def _build_message(email: str, code: str, purpose: str) -> tuple[str, str]:
    code_expire = settings.EMAIL_CODE_EXPIRE_MINUTES
    if purpose == "register":
        return ("[Eucal AI] Registration verification code",
                f"Your verification code is {code}. It expires in {code_expire} minutes.")
    if purpose == "login":
        return ("[Eucal AI] Login verification code",
                f"Your login code is {code}. It expires in {code_expire} minutes.")
    if purpose == "verify":
        return ("[Eucal AI] Email verification code",
                f"Your email verification code is {code}. It expires in {code_expire} minutes.")
    return ("[Eucal AI] Password reset verification code",
            f"Your password reset code is {code}. It expires in {code_expire} minutes.")


def _send_smtp_sync(email: str, code: str, purpose: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.debug("Mock email send: email=%s purpose=%s", email, purpose)
        return
    context = ssl.create_default_context()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_TLS:
            server.starttls(context=context)
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        subject, body = _build_message(email, code, purpose)
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{settings.SMTP_FROM} <{settings.SMTP_USER}>"
        msg["To"] = email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        server.sendmail(settings.SMTP_USER, email, msg.as_string())


async def send_verification_email(ctx: dict, email: str, code: str, purpose: str) -> None:
    """ARQ job — send a verification email synchronously inside a worker thread.

    Retries up to 3 times with linear backoff (5s, 10s, 15s) on SMTP errors.
    [CITED: arq-docs.helpmanual.io retry pattern]
    """
    try:
        await asyncio.to_thread(_send_smtp_sync, email, code, purpose)
    except Exception as exc:
        job_try = ctx.get("job_try", 1)
        if job_try < 3:
            logger.warning("emailSendRetry attempt=%d email=%s error=%s", job_try, email, exc)
            raise Retry(defer=job_try * 5) from exc
        logger.error("emailSendFailedPermanently email=%s purpose=%s error=%s", email, purpose, exc)
        # Do not re-raise: ARQ marks failed; we don't want infinite retries
```

### Controller mounting (Phase 4 final step in plan 04-03)
```python
# api_service/core/router.py — MODIFY
from fastapi import APIRouter

from api_service.controllers import auth, keys, billing, model_catalog

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)             # 10 endpoints
api_router.include_router(keys.router)             # 5 endpoints, prefix=/keys
api_router.include_router(billing.router)          # 8 endpoints, prefix=/billing
api_router.include_router(model_catalog.router)    # 4 endpoints
```

## State of the Art

| Old Approach (admin/user/router services) | Current Approach (api-service Phase 4) | When Changed | Impact |
|------------------------------------------|----------------------------------------|--------------|--------|
| Sub-repo classes (`SessionRepository`, `EmailCodeRepository`, `BalanceTxRepository`) | Merged into parent repos with method prefixes | Phase 3 D-04 (2026-05-19) | Every service-layer file needs method-name rewrite during port |
| `common/utils/jwt.py`, `common/utils/password.py` | `common/security/{jwt,password,crypto,token_blacklist}.py` | Phase 1 D-02 (2026-05-18) | Import path rewrite required |
| `common/cache.py` | `common/infra/cache.py` | Phase 1 D-02 | Import path rewrite required |
| `common/db.py` module → `common.db` package | `common/infra/db/{runtime,base,query,repository,schema_version}.py` | Phase 1 D-02 | Imports of `ListParams` / `PaginatedResult` change to `common.infra.db.query` |
| `gateways/model_catalog.py` HTTP→admin-service | Direct `ModelCatalogReadService` call (no HTTP) | Phase 4 (D-04..07) | Removes one network hop on every model list/detail page load |
| `gateways/system_settings.py` HTTP→admin-service | Config constant + (deferred to Phase 5) direct DB read | Phase 4 (O-1) | `/auth/me` no longer makes admin-service HTTP call |
| Sync SMTP send in request thread | ARQ async job with retry | Phase 4 D-02 | Frontend gets immediate 200; SMTP failure invisible (acceptable tradeoff) |

**Deprecated/outdated for Phase 4:**
- `services/user-service/src/utils/` directory — every helper migrates to `api_service/common/utils/` (3 files: `email.py`, `password_policy.py`, `api_key_policy.py`)
- `services/user-service/src/gateways/` directory — entirely deleted post-merge
- `services/user-service/src/controllers/internal_*.py` — explicitly excluded by D-01

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `system_settings.default_user_rpm` can be replaced by `settings.DEFAULT_USER_RPM` constant for Phase 4 | Architecture / Code Examples / O-1 | If admin runtime-tunable RPM is required during Phase 4 window, /auth/me will show stale data until Phase 5 | `[ASSUMED]` |
| A2 | ARQ Redis pool can use the same `WORKER_QUEUE_REDIS_URL` (db/1) as the worker — pool and worker share the queue, which is the standard pattern | Pattern 2 | Wrong → enqueue works but worker never picks it up `[CITED: arq-docs.helpmanual.io]` |
| A3 | `SameSite=strict` (current default) works for the production deployment (frontend and api-service on same site/domain via reverse proxy) | Pattern 1 / Security Domain | Wrong → refresh cookie not sent on cross-site requests; user gets logged out on page reload `[ASSUMED]` |
| A4 | Cache TTLs (mc:vendors 300s, mc:categories 300s, mc:models 120s, mc:model 300s) match source-gateway TTLs and are acceptable | Pattern 6 | If admin updates a model, users see stale data for up to 300s; D-05 explicitly accepts this `[VERIFIED via D-05]` |
| A5 | `EmailVerificationCode.email_code_delete` being newly async in the merged repo (source was sync) is intentional, not a bug | Repository Method Translation Table | Wrong → code compiles but `await` raises on a non-awaitable; verified by Read of `api_service/repositories/user_repository.py:196` `[VERIFIED]` |
| A6 | `Settings` defaults inherited from source `user-service/src/core/config.py` are still appropriate post-merge | Settings Gap table | Wrong → e.g., 4 workers × `USER_WORKER_CONCURRENCY=5` = 20 concurrent jobs may oversaturate 2h4g — likely fine but monitor `[ASSUMED]` |
| A7 | The schemas `schemas/common.py` duplicate between Phase 4 (user copy) and the future Phase 5 (admin copy) won't cause Pydantic conflicts | D-03 | Same class names in different modules: Python imports them as distinct classes, but `Generic[T]` cache keys may collide. Recommend importing both with module alias to avoid confusion. `[ASSUMED]` |
| A8 | The 4 existing cron jobs from user-service do not double-fire when migrated (api-service worker is the only worker post-merge) | Migration / D-02 | Wrong → duplicate aggregation rows / duplicate cleanup attempts. **Phase 10 must verify the legacy user-service worker is stopped before deploy.** Phase 4 doesn't need to handle it. `[ASSUMED]` |

**Items requiring user confirmation in discuss-phase before plan generation:**
- A1 (DEFAULT_USER_RPM constant vs. DB read) — directly affects /auth/me behavior
- A3 (SameSite=strict) — directly affects production cookie behavior

## Open Questions

1. **O-1: `system_settings_gateway.get_default_user_rpm()` replacement strategy**
   - What we know: Source `/auth/me` and `auth_service.register` both call this gateway to get the *current* global default RPM. The gateway calls `GET /api/v1/internal/system-settings/rate-limits` on admin-service. Per D-01, no internal_* endpoints are migrated.
   - What's unclear: Does Phase 4 need runtime-tunable RPM, or can we hard-code `settings.DEFAULT_USER_RPM`? Phase 5 admin will let admins update this — but the storage table for system settings is unclear from current code. (May live in `routing_settings` table as a key-value pair, or may be a Phase 5 new table.)
   - Recommendation: For Phase 4, use `settings.DEFAULT_USER_RPM` constant (matches source's fallback path when admin-service is unreachable). Add a clearly-named TODO comment pointing at Phase 5. Confirm with user before plan generation.

2. **O-2: `schemas/common.py` import path during Phase 4/5 dual-existence window**
   - What we know: D-03 says Phase 4 copies `schemas/common.py` verbatim from user-service. Phase 5 will also need a similar file from admin-service (`AdminBaseResponse`).
   - What's unclear: After Phase 4 lands, when Phase 5 adds an `AdminBaseResponse`, do we (a) extend the existing `schemas/common.py` adding admin classes, or (b) keep two parallel files `schemas/common.py` (user) and `schemas/admin_common.py` (admin)?
   - Recommendation: Phase 4 plan goes with (a) implicitly — Phase 5 will append `AdminBaseResponse` to the same file. Avoids file duplication, keeps the deferred-decision (merge `BaseResponse` hierarchy) clean for a later refactor.

3. **O-3: Should `EmailService.get_valid_code_or_raise` still call `await db.commit()` on the error-count update?**
   - What we know: Source commits the error count update inside `get_valid_code_or_raise`, then raises. This means caller's pending changes are also committed.
   - What's unclear: In api-service, `get_db` is rollback-on-exception only (no auto-commit). Source had the same behavior — so the explicit `await db.commit()` inside the method must be preserved verbatim.
   - Recommendation: Port verbatim. Add a comment explaining why the inner commit exists. Already documented in source.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| MySQL 8.0 | All data writes | ✓ (Phase 2) | 8.0.x | — |
| Redis (db/0, db/1, db/2) | Cache + ARQ pool | ✓ (Phase 2) | 5.x | — |
| Python 3.10+ | Runtime | ✓ | 3.12.3 | — |
| `arq` package | Background jobs | ✓ (pyproject) | 0.26.0 | — |
| `python-jose[cryptography]` | JWT | ✓ (pyproject) | 3.3.1 | — |
| `passlib[bcrypt]` + `bcrypt<4.0.0` | Password hash | ✓ (pyproject) | 1.7.4 / 3.x | — |
| `email-validator` | `EmailStr` schema field | ✓ (pyproject) | 2.1.0 | — |
| `smtplib` (stdlib) | SMTP send | ✓ | stdlib | — |
| SMTP server | Actual email delivery | Optional (settings allow blank host → mock mode) | — | Mock mode logs to debug; tests use mock mode |
| External `arq` CLI process | Worker process at deploy time | Provided by `arq` package console-script | 0.26.0 | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** SMTP server can be unconfigured (`SMTP_HOST=""`) → email service goes into mock mode (logs only). Same source behavior, useful for local dev/tests.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23+ `[VERIFIED: api-service/pyproject.toml:37-38]` |
| Config file | (no `pytest.ini` yet — pytest-asyncio strict mode noted in STATE.md decisions) |
| Quick run command | `cd services/api-service && pytest tests/ -x -q` |
| Full suite command | `cd services/api-service && pytest tests/ --cov=api_service --cov-report=term-missing` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| USER-01 | Register sets cookies + creates user + 201 | integration | `pytest tests/test_auth_register.py::test_register_success -x` | ❌ Wave 0 |
| USER-01 | Login returns access_token + sets cookies | integration | `pytest tests/test_auth_login.py::test_login_success -x` | ❌ Wave 0 |
| USER-01 | Login fails on invalid creds (rate-limited after N) | integration | `pytest tests/test_auth_login.py::test_login_lockout -x` | ❌ Wave 0 |
| USER-01 | Logout revokes session by jti, clears cookies | integration | `pytest tests/test_auth_logout.py::test_logout_revokes_session -x` | ❌ Wave 0 |
| USER-01 | Refresh rotates both tokens, updates session row | integration | `pytest tests/test_auth_refresh.py::test_refresh_rotates -x` | ❌ Wave 0 |
| USER-01 | /auth/me returns current_user without `id`, only `uid` | integration | `pytest tests/test_auth_me.py::test_me_excludes_id -x` | ❌ Wave 0 |
| USER-01 | change-password revokes all sessions | integration | `pytest tests/test_auth_change.py::test_change_revokes_sessions -x` | ❌ Wave 0 |
| USER-03 | Create API key returns plaintext once + sha256 in DB | integration | `pytest tests/test_keys.py::test_create_returns_plaintext_once -x` | ❌ Wave 0 |
| USER-03 | List API keys does not expose plaintext or hash | integration | `pytest tests/test_keys.py::test_list_no_secrets -x` | ❌ Wave 0 |
| USER-03 | Disable/delete are soft (deleted_at set, not row delete) | unit | `pytest tests/test_api_key_service.py::test_delete_is_soft -x` | ❌ Wave 0 |
| USER-04 | /billing/balance returns int fields, computed available_balance | integration | `pytest tests/test_billing_balance.py::test_balance_fields -x` | ❌ Wave 0 |
| USER-04 | /billing/transactions paginates with filter by type | integration | `pytest tests/test_billing_tx.py::test_tx_filter_by_type -x` | ❌ Wave 0 |
| USER-04 | /billing/vouchers/redeem is idempotent on duplicate code | integration | `pytest tests/test_voucher.py::test_redeem_idempotent -x` | ❌ Wave 0 |
| USER-04 | /billing/usage time range validates max 90 days | integration | `pytest tests/test_usage.py::test_range_capped -x` | ❌ Wave 0 |
| USER-04 | /billing/usage/analytics granularity switches at 48h | unit | `pytest tests/test_usage_stat_service.py::test_granularity_switch -x` | ❌ Wave 0 |
| USER-05 | /model-vendors uses cache (second call ≪ first call) | integration | `pytest tests/test_model_catalog.py::test_cache_hits -x` | ❌ Wave 0 |
| USER-05 | /models filters by vendors + q correctly | integration | `pytest tests/test_model_catalog.py::test_filter -x` | ❌ Wave 0 |
| USER-05 | /models/{slug} returns 404 on missing slug | integration | `pytest tests/test_model_catalog.py::test_404 -x` | ❌ Wave 0 |
| USER-06 | send-email-code rate-limits to 3/day | integration | `pytest tests/test_email_send.py::test_daily_limit -x` | ❌ Wave 0 |
| USER-06 | verify-email accepts valid code, increments error_count on bad | integration | `pytest tests/test_email_verify.py::test_error_count -x` | ❌ Wave 0 |
| USER-06 | send-email-code enqueues ARQ job (D-02 behavior change) | integration | `pytest tests/test_email_send.py::test_enqueues_arq -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd services/api-service && pytest tests/ -x -q -k "<relevant_module>"` — runs only related tests (~1-3s)
- **Per wave merge:** `cd services/api-service && pytest tests/ -x -q` — full quick run (~10-15s)
- **Phase gate:** `pytest tests/ --cov=api_service --cov-fail-under=80` — full suite with coverage gate before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_auth_register.py` — covers USER-01
- [ ] `tests/test_auth_login.py` — covers USER-01 (login + lockout)
- [ ] `tests/test_auth_logout.py` — covers USER-01
- [ ] `tests/test_auth_refresh.py` — covers USER-01
- [ ] `tests/test_auth_me.py` — covers USER-01
- [ ] `tests/test_auth_change.py` — covers USER-01
- [ ] `tests/test_auth_reset.py` — covers USER-01
- [ ] `tests/test_keys.py` — covers USER-03
- [ ] `tests/test_api_key_service.py` — unit tests for ApiKeyService
- [ ] `tests/test_billing_balance.py`, `test_billing_tx.py`, `test_voucher.py`, `test_topup.py` — covers USER-04
- [ ] `tests/test_usage.py`, `test_usage_stat_service.py` — covers USER-04
- [ ] `tests/test_model_catalog.py` — covers USER-05
- [ ] `tests/test_email_send.py`, `test_email_verify.py` — covers USER-06
- [ ] `tests/conftest.py` — shared fixtures: in-memory or sqlite DB, mock ARQ pool, mock Redis cache, fixture user
- [ ] `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]` block — `asyncio_mode = "auto"` + `asyncio_default_fixture_loop_scope = "function"` (STATE.md mentions strict mode)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | bcrypt password hash via passlib (already locked); login lockout on N failures (LOGIN_MAX_FAILURES) |
| V3 Session Management | yes | Server-side `user_sessions` row with `refresh_token_hash` (bcrypt of refresh token); jti index for O(1) lookup; revoke-on-logout; expire after JWT_REFRESH_TOKEN_EXPIRE_DAYS |
| V4 Access Control | yes | `Depends(require_active_user)` on every authenticated endpoint; user_id scoping in every billing/keys query (no cross-user leak path) |
| V5 Input Validation | yes | Pydantic v2 schemas with EmailStr + length/pattern bounds; `normalize_email`, `normalize_allow_ips`, `normalize_allowed_models` for canonicalization |
| V6 Cryptography | yes | python-jose (HS256), passlib[bcrypt], hashlib.sha256 for API key hash. Never hand-roll. |
| V7 Error Handling | yes | All exceptions go through `register_exception_handlers` (Phase 1 D-01); structured logs via `log_event` with auto-PII masking from observability layer |
| V8 Data Protection | yes | API key plaintext returned only once on creation; hash-only in DB; password never logged |
| V9 Communication | partial | TLS termination at reverse proxy; SameSite=strict + Secure=true cookies; HTTPS enforced via deployment (Phase 10) |
| V13 API & Web Service | yes | OpenAPI auto-generated; rate limit on `/auth/send-email-code` via CODE_DAILY_SEND_LIMIT (3/day); on `/auth/login` via LOGIN_MAX_FAILURES |

### Known Threat Patterns for Cookie-Based JWT + ARQ Email

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Refresh token theft via XSS | Spoofing | HttpOnly cookie (already set); no JS-readable token storage |
| CSRF on logout/refresh | Tampering | SameSite=strict on cookies; refresh-endpoint requires cookie present (no header-only attack surface). **Open question for /auth/login**: a CSRF login attack can log victim into attacker's account — out of scope for this migration since same behavior exists in source. `[CITED: stackhawk.com CSRF in FastAPI]` |
| Email enumeration via /auth/register | Information disclosure | Source returns generic `EmailAlreadyExistsException` (status 400, message in zh). Verify this is enough — alternative is constant-time fail. Phase 4 preserves source behavior. |
| Bcrypt timing leak on `/auth/login` for non-existent users | Information disclosure | Source uses `_get_dummy_hash()` to equalize verify time on missing users. Preserve verbatim `[VERIFIED]`. |
| Code brute-force on /auth/verify-email | Spoofing | `error_count` + `locked_until` (24h after 5 wrong tries); `CODE_DAILY_SEND_LIMIT` (3/day per email+purpose) |
| Voucher code double-redeem | Tampering | `SELECT FOR UPDATE` on voucher row + status check + ref_id idempotency on balance_transactions |
| Insufficient-balance race on relay | Tampering | `SELECT FOR UPDATE` on user row in `BalanceService.consume_for_call_log` / `freeze` / `settle` |
| API key leakage in logs | Information disclosure | observability layer has auto-masking; do not `log_event(..., api_key=raw_key)`. Use `key_prefix` only. |
| ARQ job payload contains plaintext verification code | Information disclosure | The job receives plaintext code in Redis. Redis is internal; mitigated by Redis ACL + network isolation. Not logged in worker logs (verify with `log_event` discipline). |
| SMTP credentials in env vars | Information disclosure | Standard practice; secret manager in Phase 10 deployment if needed. |

**Security review must-pass before phase ends:**
- [ ] No new endpoint returns `id` (only `uid`) to frontend
- [ ] No endpoint returns API key plaintext except on creation
- [ ] No endpoint returns `password_hash`, `code_hash`, `key_hash`, or `refresh_token_hash`
- [ ] All authenticated endpoints scope queries by `int(current_user.id)`
- [ ] `register_exception_handlers` is wired in Phase 1 main.py (already done — verify still present)

## Project Constraints (from CLAUDE.md)

From `services/user-service/CLAUDE.md` (applies to api-service user domain per CONTEXT.md canonical_refs):

- [ ] Controller layer薄: parameters → service call → ApiResponse only — no ORM mutations in controllers
- [ ] Service layer: `@staticmethod` + `db: AsyncSession` first param; methods instantiate repos internally
- [ ] Transactions: service/controller explicitly `await db.commit()` — `get_db` is rollback-on-exception only, no auto-commit
- [ ] Idempotency: `ref_id` dedupe; balance changes use `SELECT FOR UPDATE`
- [ ] Blocking IO must be `await asyncio.to_thread(...)` (bcrypt already wrapped; SMTP moved to ARQ in D-02)
- [ ] No `httpx.AsyncClient(...)` ad-hoc in business code — D-02 deletes the gateway pattern entirely for Phase 4
- [ ] Logging: `log_event(logger, level, "eventName", k=v)` — no string interpolation
- [ ] Settings: `from api_service.core.config import settings` singleton; min length 32 for `JWT_SECRET_KEY` / `INTERNAL_SECRET` (already enforced in `BaseServiceSettings.validate_required_fields`)

From root `CLAUDE.md`:

- [ ] **User identity rule (用户标识规范):** Frontend responses must never include `user_id: int`. Use `user_uid: str` (NanoID). Internal service-to-service may use `user_id`. **Internal endpoints** are NOT migrated this phase — so the only context where `user_id` appears in Phase 4 is purely internal (passing `int(current_user.id)` from controller to service). Final responses serialize `uid` only.
- [ ] Branch name: `feat/04-user-domain-controllers` or `refactor/04-user-domain-controllers` (current branch `refactor/merge-api-service` already covers it)
- [ ] Commit messages: 中文 + conventional commits format (e.g., `feat(auth): 迁移用户认证 controller 到 api-service`)
- [ ] PR target: `develop`; squash-merge

From admin-service CLAUDE.md (consulted because D-06 pulls schemas from admin):

- [ ] Admin schema file uses `AdminBaseResponse` — Phase 4 does NOT pull this; only pulls read-only `ModelVendorItem`, `ModelCategoryItem`, `SupportedModelItem`, `SupportedModelDetail`, `ModelVendorBrief`, `ModelCategoryBrief`. The admin-side `ModelVendorListResponse(AdminBaseResponse)` and write schemas are deferred to Phase 5.
- [ ] Admin schemas import `from common.api import PaginatedResponse` — translate to `from api_service.common.api.pagination import PaginatedResponse` during port.

## Sources

### Primary (HIGH confidence)

**Source repository files (verified via Read):**
- `services/user-service/src/controllers/auth.py` — 10 endpoints, cookie helpers, dependencies
- `services/user-service/src/controllers/keys.py` — 5 endpoints
- `services/user-service/src/controllers/billing.py` — 8 endpoints, ListParams build helper
- `services/user-service/src/controllers/model_catalog.py` — 4 endpoints, gateway delegation
- `services/user-service/src/services/auth_service.py` — full register/login/logout/refresh/verify/change/reset flow
- `services/user-service/src/services/api_key_service.py` — CRUD + validate_by_hash
- `services/user-service/src/services/balance_service.py` — wallet mutations with SELECT FOR UPDATE
- `services/user-service/src/services/email_service.py` — current sync SMTP implementation
- `services/user-service/src/services/topup_order_service.py` — order create
- `services/user-service/src/services/usage_stat_service.py` — analytics + bucketing
- `services/user-service/src/services/voucher_service.py` — generate + redeem
- `services/user-service/src/schemas/{common,auth,keys,billing}.py` — all request/response models
- `services/user-service/src/core/{config,worker,jobs,policies,router}.py` — settings + ARQ wiring
- `services/user-service/src/utils/{email,password,api_key_policy}.py` — schema validators
- `services/user-service/src/gateways/{model_catalog,system_settings}.py` — gateways to delete
- `services/user-service/CLAUDE.md` — service-layer conventions (auth, async, transactions, logging)
- `services/admin-service/src/services/model_catalog_service.py` — read methods to copy
- `services/admin-service/src/schemas/model_catalog.py` — read-only schema subset
- `services/admin-service/CLAUDE.md` — confirms shared conventions
- `services/api-service/api_service/main.py` — current lifespan; ARQ to be added
- `services/api-service/api_service/core/{config,db,router,lifespan}.py` — Phase 1-3 baseline
- `services/api-service/api_service/core/dependencies/{user,admin}.py` — auth deps Phase 3
- `services/api-service/api_service/common/security/{jwt,password}.py` — already-migrated security utils
- `services/api-service/api_service/common/infra/{redis,cache}.py` — Phase 2 Redis pools
- `services/api-service/api_service/common/api/pagination.py` — PaginatedResponse
- `services/api-service/api_service/common/infra/db/{repository,query}.py` — BaseRepository + ListParams
- `services/api-service/api_service/repositories/{user,api_key,billing,voucher,model_catalog}_repository.py` — Phase 3 merged repos (CRITICAL for translation table)
- `services/api-service/pyproject.toml` — dependency list (arq, redis, jose, passlib, bcrypt, email-validator)
- `services/api-service/api_service/common/config.py` — `BaseServiceSettings` with JWT/COOKIE/PASSWORD defaults
- `services/api-service/tests/test_auth_dependencies.py` — existing test patterns to follow
- `.planning/phases/04-user-domain-controllers/04-CONTEXT.md` — D-01..D-08 locked decisions
- `.planning/REQUIREMENTS.md` — USER-01, USER-04, USER-05, USER-06 traceability
- `.planning/STATE.md` — Phase 3 decisions (D-04 repo merge, D-08 user no blacklist)

### Secondary (MEDIUM confidence)

- [ARQ documentation](https://arq-docs.helpmanual.io/) — lifespan + enqueue_job + Retry patterns
- [Building Resilient Task Queues with ARQ Retries](https://davidmuraya.com/blog/fastapi-arq-retries/) — backoff strategies
- [FastAPI cookie/CSRF best practices](https://github.com/fastapi-users/fastapi-users/discussions/291) — SameSite + double-submit
- [Pydantic v2 generic models](https://docs.pydantic.dev/latest/concepts/models/) — `Generic[T]` envelope pattern

### Tertiary (LOW confidence)

None — this phase is grounded in source-code reads.

## Plan Difficulty Estimates

| Plan | Difficulty | Estimated Tasks | Key Files | Primary Risks |
|------|------------|-----------------|-----------|---------------|
| 04-01: Auth controllers + ARQ + worker | **HIGH** | 12-16 | auth.py controller, auth_service.py, email_service.py, arq_pool.py, worker.py, jobs.py (4 crons + send_verification_email), schemas/{auth,common}.py, common/utils/{email,password_policy}.py, core/policies.py, missing Settings keys, main.py lifespan registration | (1) ARQ pool lifespan wiring brand new; (2) email_service shift from sync→ARQ; (3) repository method-name rewrites at 15+ call sites; (4) get_db_session→get_db rename; (5) schemas/common.py + DateTimeModel port |
| 04-02: API Key + Billing controllers | **MEDIUM** | 10-14 | keys.py, billing.py controllers, api_key_service, balance_service, topup_order_service, voucher_service, usage_stat_service, schemas/{keys,billing}.py, common/utils/api_key_policy.py | (1) Heavy repo-method rewrites for billing (BillingRepository merged 3 sources); (2) verify SELECT FOR UPDATE preserved through translation; (3) ref_id idempotency check at every TX |
| 04-03: Model catalog + cleanup | **LOW** | 6-9 | model_catalog.py controller, model_catalog_service.py (new user variant), schemas/model_catalog.py (read-only subset from admin), Redis cache integration, router.include_router final wiring | (1) Cross-domain schema copy from admin-service (D-06); (2) deciding sort_order/active_only/category filter equivalence with admin internal endpoint; (3) cache key naming and TTLs |

**Recommended task ordering (cross-plan):**
1. Wave 0 (foundational, must precede everything): Settings keys + `common/utils/{email,password_policy,api_key_policy}.py` + `core/policies.py` + ARQ pool lifespan + `core/worker.py` + `core/jobs.py` skeleton + `schemas/common.py`. ~6-8 tasks. *Should land in plan 04-01.*
2. Wave 1 (plan 04-01 continues): schemas/auth.py + auth_service.py + email_service.py (with ARQ enqueue) + controllers/auth.py + tests.
3. Wave 2 (plan 04-02): schemas/{keys,billing}.py + ApiKeyService + BalanceService + TopupOrderService + VoucherService + UsageStatService + controllers/{keys,billing}.py + tests.
4. Wave 3 (plan 04-03): schemas/model_catalog.py + ModelCatalogReadService + controllers/model_catalog.py + router include_router for all 4 routers + integration test that all routes register.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every dependency verified in api-service/pyproject.toml
- Architecture / patterns: HIGH — sourced from verified file reads
- Pitfalls: HIGH — translation tables built from side-by-side Read of source + target
- ARQ wiring: MEDIUM-HIGH — pattern is standard but `api_service.core.arq_pool` is a new module that hasn't been written or tested yet; the planner should treat the example code in Pattern 2 as a starting point, not a verified implementation
- O-1 (system_settings replacement): LOW until user confirms in discuss — recommendation is to use constant fallback

**Research date:** 2026-05-19
**Valid until:** 2026-06-19 (30 days for migration phases — source code doesn't drift fast, but repo method names may evolve if Phase 3 gets follow-up commits)
