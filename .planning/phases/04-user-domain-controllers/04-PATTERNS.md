# Phase 4: User Domain Controllers — Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 27 new files + 2 modifications
**Analogs found:** 27 / 27 (every new file has a 1:1 user-service source; modifications anchor on existing api-service files)

This phase is a **1:1 port** of `services/user-service/src/` into `services/api-service/api_service/`. For every new file there is a direct source analog. Diverges from source are listed under the **Divergences** column of each pattern assignment.

## File Classification

Legend — Wave column refers to RESEARCH.md "Recommended task ordering": Wave 0 (foundational, plan 04-01 prerequisite), Wave 1 (auth + ARQ + worker, plan 04-01), Wave 2 (keys + billing, plan 04-02), Wave 3 (model catalog + cleanup, plan 04-03).

| New / Modified File | Role | Data Flow | Closest Analog | Match | Wave / Plan |
|---------------------|------|-----------|----------------|-------|-------------|
| `api_service/common/utils/email.py` | utility | pure-function | `services/user-service/src/utils/email.py` | exact | Wave 0 / 04-01 |
| `api_service/common/utils/password_policy.py` | utility | pure-function | `services/user-service/src/utils/password.py` | exact | Wave 0 / 04-01 |
| `api_service/common/utils/api_key_policy.py` | utility | pure-function | `services/user-service/src/utils/api_key_policy.py` | exact | Wave 0 / 04-01 |
| `api_service/core/policies.py` | dependency / guard | request-response | `services/user-service/src/core/policies.py` | exact | Wave 0 / 04-01 |
| `api_service/core/arq_pool.py` | infrastructure / lifespan | event-driven (pub) | `services/api-service/api_service/common/infra/cache.py` (module-global accessor) + `services/user-service/src/core/jobs.py:23-36 build_redis_settings` | role-match (new module — pattern composed of two analogs) | Wave 0 / 04-01 |
| `api_service/core/worker.py` | config / worker entrypoint | event-driven (sub) | `services/user-service/src/core/worker.py` | exact | Wave 0 / 04-01 |
| `api_service/core/jobs.py` | worker / cron + ARQ job | event-driven (handler) | `services/user-service/src/core/jobs.py` | exact (extended with `send_verification_email` job) | Wave 0 / 04-01 |
| `api_service/core/config.py` (MODIFY — add Settings keys) | config | n/a | itself; defaults from `services/user-service/src/core/config.py:28-51` | exact | Wave 0 / 04-01 |
| `api_service/main.py` (MODIFY — register ARQ lifespan) | bootstrap | request-response | `services/api-service/api_service/main.py:85-118` (existing redis + cache_redis registration) | exact | Wave 0 / 04-01 |
| `api_service/schemas/common.py` | schema (envelope + serializer) | request-response | `services/user-service/src/schemas/common.py` | exact (verbatim copy) | Wave 0 / 04-01 |
| `api_service/schemas/auth.py` | schema (request/response models) | request-response | `services/user-service/src/schemas/auth.py` | exact | Wave 1 / 04-01 |
| `api_service/services/auth_service.py` | service | CRUD + request-response | `services/user-service/src/services/auth_service.py` | exact (with repo-method rewrites) | Wave 1 / 04-01 |
| `api_service/services/email_service.py` | service | event-driven (enqueue) | `services/user-service/src/services/email_service.py` | exact (D-02 divergence: SMTP → ARQ enqueue) | Wave 1 / 04-01 |
| `api_service/controllers/auth.py` | controller | request-response | `services/user-service/src/controllers/auth.py` | exact (no `system_settings_gateway`, no `internal_*`) | Wave 1 / 04-01 |
| `api_service/schemas/keys.py` | schema | request-response | `services/user-service/src/schemas/keys.py` | exact | Wave 2 / 04-02 |
| `api_service/schemas/billing.py` | schema | request-response | `services/user-service/src/schemas/billing.py` | exact | Wave 2 / 04-02 |
| `api_service/services/api_key_service.py` | service | CRUD | `services/user-service/src/services/api_key_service.py` | exact (path imports only) | Wave 2 / 04-02 |
| `api_service/services/balance_service.py` | service | CRUD (SELECT FOR UPDATE) | `services/user-service/src/services/balance_service.py` | exact (with repo-method rewrites) | Wave 2 / 04-02 |
| `api_service/services/topup_order_service.py` | service | CRUD | `services/user-service/src/services/topup_order_service.py` | exact (with repo-method rewrites) | Wave 2 / 04-02 |
| `api_service/services/usage_stat_service.py` | service | aggregate / read-heavy | `services/user-service/src/services/usage_stat_service.py` | exact (with repo-method rewrites) | Wave 2 / 04-02 |
| `api_service/services/voucher_service.py` | service | CRUD (SELECT FOR UPDATE) | `services/user-service/src/services/voucher_service.py` | exact (with repo-method rewrites) | Wave 2 / 04-02 |
| `api_service/controllers/keys.py` | controller | request-response | `services/user-service/src/controllers/keys.py` | exact | Wave 2 / 04-02 |
| `api_service/controllers/billing.py` | controller | request-response | `services/user-service/src/controllers/billing.py` | exact | Wave 2 / 04-02 |
| `api_service/schemas/model_catalog.py` | schema (read-only) | request-response | `services/admin-service/src/schemas/model_catalog.py` (read-only subset only) | role-match (cross-domain copy, no Admin write schemas) | Wave 3 / 04-03 |
| `api_service/services/model_catalog_service.py` | service | read-heavy + cache | `services/user-service/src/gateways/model_catalog.py` (cache scaffolding) + `services/admin-service/src/services/model_catalog_service.py:108-180` (read methods) | role-match (two analogs combined — HTTP gateway becomes direct call) | Wave 3 / 04-03 |
| `api_service/controllers/model_catalog.py` | controller | request-response | `services/user-service/src/controllers/model_catalog.py` | exact (gateway call → local service call) | Wave 3 / 04-03 |
| `api_service/core/router.py` (MODIFY — include_router) | wiring | n/a | itself + RESEARCH.md Code Example "Controller mounting" | exact | Wave 3 / 04-03 |
| `api_service/schemas/__init__.py` (NEW) | export aggregator | n/a | `services/user-service/src/schemas/__init__.py` | exact | Wave 1-3 (additive) |
| `tests/test_auth_*.py` + `tests/test_keys.py` + `tests/test_billing_*.py` + `tests/test_model_catalog.py` + `tests/test_email_*.py` + `tests/conftest.py` | test | unit / integration | `services/api-service/tests/test_auth_dependencies.py` (mocking style) + `services/api-service/tests/test_repositories_import.py` (import-shape tests) | role-match — no user-service tests exist | Wave 0–3 |

---

## Pattern Assignments

### `api_service/common/utils/email.py` (utility, pure-function)

**Analog:** `services/user-service/src/utils/email.py`

**Whole file (lines 1-9 of source — port verbatim, no changes):**
```python
"""Email normalization helpers for user-service."""

from __future__ import annotations


def normalize_email(email: str) -> str:
    """Normalize user-facing email input for consistent storage and lookup."""
    return email.strip().lower()
```

**Divergences:** None. Update docstring service name from "user-service" to "api-service".

---

### `api_service/common/utils/password_policy.py` (utility, pure-function)

**Analog:** `services/user-service/src/utils/password.py`

**Why renamed:** Target tree already has `api_service/common/security/password.py` (bcrypt hashing). To avoid name clash and clearly separate "strength check" from "bcrypt hash", source `utils/password.py` → target `common/utils/password_policy.py`. RESEARCH.md Import Translation Table line: `from utils.password import check_password_strength` → `from api_service.common.utils.password_policy import check_password_strength`.

**Imports pattern** (source lines 1-9):
```python
import re
from typing import Tuple

from core.config import settings
```

**Rewrite to:**
```python
import re
from typing import Tuple

from api_service.core.config import settings
```

**Core pattern (source lines 33-66):** `check_password_strength(password, lang)` reads `settings.PASSWORD_MIN_LENGTH`, `settings.PASSWORD_REQUIRE_UPPERCASE`, etc. — all already exist in `BaseServiceSettings` (verified: `common/config.py:65-69`). Port verbatim, only the `from core.config` import changes.

**Divergences:** None besides import path.

---

### `api_service/common/utils/api_key_policy.py` (utility, pure-function)

**Analog:** `services/user-service/src/utils/api_key_policy.py`

**Whole file is import-free Python stdlib (`ipaddress`).** Port verbatim — zero rewrite needed. Lines 1-75 of source are byte-for-byte reusable.

```python
# source: services/user-service/src/utils/api_key_policy.py:1-23 [VERIFIED]
def normalize_allowed_models(value: str | None) -> str | None:
    """Normalize comma-separated allowed model names."""
    if value is None:
        return None
    raw_items = [item.strip() for item in value.split(",")]
    if not raw_items or any(not item for item in raw_items):
        raise ValueError("allowed_models must be a comma-separated list of non-empty model names")
    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return ",".join(normalized)
```

**Divergences:** None.

---

### `api_service/core/policies.py` (dependency / guard, request-response)

**Analog:** `services/user-service/src/core/policies.py`

**Whole file (source lines 1-19):**
```python
"""Authorization guards for user-service."""

from __future__ import annotations

from fastapi import Depends

from common.core.exceptions import EmailNotVerifiedException, UserDisabledException
from core.dependencies import get_current_user
from models import User


async def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Require a non-disabled, non-pending user."""

    if current_user.status == 0:
        raise UserDisabledException()
    if current_user.status == 2:
        raise EmailNotVerifiedException()
    return current_user
```

**Rewrite imports to:**
```python
from api_service.common.core.exceptions import EmailNotVerifiedException, UserDisabledException
from api_service.core.dependencies.user import get_current_user  # Phase 3 path
from api_service.models import User
```

**Verified:** `api_service.core.dependencies.user.get_current_user` exists `[VERIFIED: api_service/core/dependencies/user.py:26-70]`.

**Divergences:** None.

---

### `api_service/core/arq_pool.py` (infrastructure / lifespan, event-driven pub)

**Analogs (composed):**
- `api_service/common/infra/cache.py` — module-global accessor pattern (init / close / get / check-ready)
- `services/user-service/src/core/jobs.py:23-36` — `build_redis_settings()` parsing `WORKER_QUEUE_REDIS_URL`

**Imports + accessor scaffold (copy from `cache.py:1-43`):**
```python
# source: api_service/common/infra/cache.py:13-43 [VERIFIED]
_cache_redis: aioredis.Redis | None = None

async def init_cache_redis(url: str) -> None:
    global _cache_redis
    _cache_redis = aioredis.from_url(url, decode_responses=True)
    await _cache_redis.ping()

def get_cache_redis() -> aioredis.Redis:
    if _cache_redis is None:
        raise RuntimeError("Cache Redis not initialised — call init_cache_redis() first")
    return _cache_redis

async def close_cache_redis() -> None:
    global _cache_redis
    if _cache_redis is not None:
        await _cache_redis.aclose()
        _cache_redis = None
```

**Apply same shape to ArqRedis** — use `arq.create_pool(_build_redis_settings())` instead of `aioredis.from_url(url)`, and `_arq_pool.close()` (no `aclose` on ArqRedis).

**RedisSettings builder (port from `jobs.py:23-36`):**
```python
# source: services/user-service/src/core/jobs.py:23-36 [VERIFIED]
def build_redis_settings(redis_url: str | None = None) -> RedisSettings:
    parsed = urlparse(redis_url or settings.USER_QUEUE_REDIS_URL)
    database = 0
    path = (parsed.path or "").lstrip("/")
    if path:
        database = int(path)
    return RedisSettings(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        database=database,
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )
```

**Rewrite `settings.USER_QUEUE_REDIS_URL` → `settings.WORKER_QUEUE_REDIS_URL`** (already defined in api-service config `core/config.py:27`).

**Divergences:**
- Module is **NEW** in api-service (no existing file). RESEARCH.md Pattern 2 lays out the full skeleton.
- Lifespan registration in `main.py` uses priority=40 (after redis priority=30, after database priority=20).

---

### `api_service/core/worker.py` (config / worker entrypoint, event-driven sub)

**Analog:** `services/user-service/src/core/worker.py`

**Whole file (source lines 1-19) — port verbatim with import rewrites:**
```python
"""ARQ worker entrypoint for user-service jobs."""

from __future__ import annotations

import models  # noqa: F401
from common.observability import configure_logging_from_settings
from core.config import settings
from core.jobs import get_worker_settings_kwargs

configure_logging_from_settings(settings)


class WorkerSettings:
    pass


for _key, _value in get_worker_settings_kwargs().items():
    setattr(WorkerSettings, _key, _value)
```

**Rewrite imports to:**
```python
import api_service.models  # noqa: F401
from api_service.common.observability import configure_logging_from_settings
from api_service.core.config import settings
from api_service.core.jobs import get_worker_settings_kwargs
```

**Deployment-side runtime command:** `arq api_service.core.worker.WorkerSettings` (documented as a Phase 10 concern in RESEARCH.md, but the module path is locked here).

---

### `api_service/core/jobs.py` (worker / cron + ARQ job handler, event-driven)

**Analog:** `services/user-service/src/core/jobs.py` (entire file)

**Imports pattern** (source lines 1-19):
```python
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select, text

from common.observability import log_event
from common.utils.timezone import now
from core.config import settings
from core.db import close_db, create_engine, get_db_context, init_session_factory
from models import EmailVerificationCode
from services.usage_stat_service import UsageStatService
```

**Rewrite to:**
```python
from api_service.common.observability import log_event
from api_service.common.utils.timezone import now
from api_service.core.config import settings
from api_service.core.db import close_db, create_engine, get_db_context, init_session_factory
from api_service.models import EmailVerificationCode
from api_service.services.usage_stat_service import UsageStatService
```

**Worker startup pattern (lines 39-50) — keep verbatim except settings keys:**
```python
async def on_worker_startup(ctx: dict) -> None:
    create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    )
    init_session_factory()
    ctx["settings"] = settings
    logger.info("User worker started")
```

**4 existing cron jobs to port verbatim** (lines 58-123): `aggregate_usage_stats`, `cleanup_expired_verification_codes`, `cleanup_expired_sessions`, `reconcile_balance_ledger`. All use `get_db_context()` (already in `api_service/core/db.py:14`).

**NEW job `send_verification_email` (per D-02)** — full skeleton in RESEARCH.md Code Examples §"ARQ job — send_verification_email". Key shape:

```python
# CITED: RESEARCH.md Code Examples + arq-docs.helpmanual.io retry pattern
_JOB_SEND_VERIFICATION_EMAIL = "send_verification_email"  # locked name (Pitfall 9)

async def send_verification_email(ctx: dict, email: str, code: str, purpose: str) -> None:
    try:
        await asyncio.to_thread(_send_smtp_sync, email, code, purpose)
    except Exception as exc:
        job_try = ctx.get("job_try", 1)
        if job_try < 3:
            raise Retry(defer=job_try * 5) from exc
        logger.error("emailSendFailedPermanently email=%s purpose=%s", email, purpose)
```

**`get_worker_settings_kwargs` registration (source lines 126-145)** — append `send_verification_email` to the `functions` list:
```python
"functions": [
    aggregate_usage_stats,
    cleanup_expired_verification_codes,
    cleanup_expired_sessions,
    reconcile_balance_ledger,
    send_verification_email,  # NEW (D-02)
],
```

**Divergences:**
- **D-02:** add `send_verification_email` job + SMTP send helper (Pitfall 9: function `__name__` must match enqueue name).
- Settings key `USER_QUEUE_REDIS_URL` → `WORKER_QUEUE_REDIS_URL`.
- Settings keys `USER_WORKER_CONCURRENCY`, `USER_JOB_TIMEOUT_SECONDS`, `VERIFICATION_CODE_RETENTION_DAYS` must exist on `ApiServiceSettings` (see Settings Gap table in RESEARCH.md and Shared Patterns §Settings below).

---

### `api_service/core/config.py` (MODIFY — append settings keys)

**Analog (for defaults):** `services/user-service/src/core/config.py:28-51` — defaults are the source of truth.

**Append to `class ApiServiceSettings(BaseServiceSettings)` (RESEARCH.md Settings Gap table verbatim):**
```python
# ── User-domain extras (Phase 4) ──────────────────────────────────────
LOGIN_LOCK_DURATION_HOURS: int = 1
MAX_CODE_ERRORS: int = 5
CODE_ERROR_LOCK_HOURS: int = 24
CODE_DAILY_SEND_LIMIT: int = 3
VERIFICATION_CODE_RETENTION_DAYS: int = 7
MIN_TOPUP_AMOUNT: int = 1_000_000
MAX_TOPUP_AMOUNT: int = 10_000_000_000
USER_WORKER_CONCURRENCY: int = 5
USER_JOB_TIMEOUT_SECONDS: int = 300
DEFAULT_USER_RPM: int = 20  # D-09: read in /auth/me + register; replaces system_settings_gateway
```

**Already-present keys** (no changes needed — verified `api_service/core/config.py:42-50` + `common/config.py:51-69`): `SMTP_*`, `EMAIL_CODE_EXPIRE_MINUTES`, `MAX_API_KEYS_PER_USER`, `LOGIN_MAX_FAILURES`, `JWT_*`, `COOKIE_*`, `PASSWORD_*`, `WORKER_QUEUE_REDIS_URL`.

**Divergences:**
- **D-09:** `DEFAULT_USER_RPM=20` is the **only** source of default RPM in Phase 4 (no DB read, no `system_settings_gateway`). Add a `# TODO(phase-5): read from system_settings table` comment.

---

### `api_service/main.py` (MODIFY — register ARQ lifespan)

**Analog:** existing redis + cache_redis registration in `api_service/main.py:85-118`.

**Imports + lifespan registration pattern (lines 85-118):**
```python
# source: api_service/main.py:102-118 [VERIFIED]
async def _init_cache_redis() -> None:
    from api_service.common.infra.cache import init_cache_redis
    await init_cache_redis(settings.CACHE_REDIS_URL)

async def _shutdown_cache_redis() -> None:
    from api_service.common.infra.cache import close_cache_redis
    await close_cache_redis()

registry.register(
    "cache_redis", init_fn=_init_cache_redis, shutdown_fn=_shutdown_cache_redis, priority=30
)
```

**Append below the `cache_redis` registration:**
```python
async def _init_arq_pool() -> None:
    from api_service.core.arq_pool import init_arq_pool
    await init_arq_pool()

async def _shutdown_arq_pool() -> None:
    from api_service.core.arq_pool import close_arq_pool
    await close_arq_pool()

registry.register(
    "arq_pool", init_fn=_init_arq_pool, shutdown_fn=_shutdown_arq_pool, priority=40
)
```

**Divergences:** Priority **40** ensures ARQ starts after Redis (30) and DB (20); shuts down before them on teardown (reverse priority order — verified `lifespan.py:74-98`).

---

### `api_service/schemas/common.py` (schema envelope, request-response)

**Analog:** `services/user-service/src/schemas/common.py` (verbatim copy — 40 lines)

**Imports pattern + full file (source lines 1-40 — port verbatim):**
```python
"""Shared schema primitives for user-service packages."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field, model_serializer

from common.utils.timezone import format_iso

T = TypeVar("T")


class DateTimeModel(BaseModel):
    """Serialize datetimes as ISO strings."""

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class AuthBaseResponse(BaseModel):
    code: int = Field(default=200, description="Status code")
    message: str = Field(default="success", description="Message")


class AuthErrorResponse(AuthBaseResponse):
    code: int = Field(default=400, description="Status code")
    message: str = Field(default="error", description="Message")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=200)
    message: str = Field(default="success")
    data: Optional[T] = None
```

**Single import rewrite:**
```python
from api_service.common.utils.timezone import format_iso
```

**Pitfall 7 (CRITICAL):** Keep the `list(data.items())` copy in `serialize_model`. Iterating `data.items()` directly will `RuntimeError` on dicts that get mutated in the loop. Do NOT lint-clean.

**Divergences:**
- **D-10:** Phase 5 will extend this same file to add `AdminBaseResponse` (no second file).

---

### `api_service/schemas/auth.py` (schema, request-response)

**Analog:** `services/user-service/src/schemas/auth.py` (225 lines)

**Imports pattern (source lines 1-13):**
```python
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from schemas.common import AuthBaseResponse, DateTimeModel
from utils.email import normalize_email
from utils.password import check_password_strength
```

**Rewrite to:**
```python
from api_service.schemas.common import AuthBaseResponse, DateTimeModel
from api_service.common.utils.email import normalize_email
from api_service.common.utils.password_policy import check_password_strength  # renamed
```

**Field-validator chaining example (source lines 36-48 — port verbatim):**
```python
@field_validator("confirm_password")
@classmethod
def validate_password_match(cls, value: str, info) -> str:
    if "password" in info.data and value != info.data["password"]:
        raise ValueError("Passwords do not match")
    return value

@model_validator(mode="after")
def validate_password_strength(self):
    ok, message = check_password_strength(self.password, lang=self.lang)
    if not ok:
        raise ValueError(message)
    return self
```

**`UserInfoResponseData` fields (source lines 101-116) — preserve `rpm_limit`, `default_rpm`, `current_tpm` exactly** — front-end depends on them.

**Divergences:** None besides import paths.

---

### `api_service/services/auth_service.py` (service, CRUD + request-response)

**Analog:** `services/user-service/src/services/auth_service.py` (393 lines)

**Imports rewrite (source lines 12-40 → target):**
```python
# source [VERIFIED]:
from common.utils.jwt import create_access_token, create_refresh_token, decode_token, get_token_jti
from common.utils.password import hash_password, hash_password_async, verify_password_async
from common.utils.nanoid_uid import generate_nanoid_uid
from common.utils.snowflake import generate_snowflake_id
from gateways.system_settings import system_settings_gateway   # DELETE
from repositories import SessionRepository, UserRepository      # SessionRepository ← merge to UserRepository
from services.email_service import email_service                # → EmailService
from utils.email import normalize_email
```

**Rewrite to:**
```python
from api_service.common.security.jwt import create_access_token, create_refresh_token, decode_token, get_token_jti
from api_service.common.security.password import hash_password, hash_password_async, verify_password_async
from api_service.common.utils.nanoid_uid import generate_nanoid_uid
from api_service.common.utils.snowflake import generate_snowflake_id
from api_service.repositories.user_repository import UserRepository
from api_service.services.email_service import EmailService
from api_service.common.utils.email import normalize_email
# DELETE: gateways.system_settings → replaced by settings.DEFAULT_USER_RPM (D-09)
```

**Repository method rewrites (all session_* operations) — examples:**

| Source call | Target call |
|-------------|-------------|
| `session_repo = SessionRepository(db)` | `user_repo = UserRepository(db)` (re-use the same repo) |
| `session_repo.get_by_token_jti(jti)` | `user_repo.get_session_by_token_jti(jti)` |
| `session_repo.list_active_for_user(uid)` | `user_repo.list_active_sessions_for_user(uid)` |
| `session_repo.revoke(session)` | `user_repo.revoke_session(session)` |
| `session_repo.add(session)` | `user_repo.add_session(session)` |

**Verified target methods exist** `[VERIFIED: api_service/repositories/user_repository.py:121-139]`.

**Register flow (source lines 59-111) — DEFAULT_USER_RPM divergence (D-09):**
```python
# source: services/user-service/src/services/auth_service.py:85-94 [VERIFIED]
try:
    snapshot_rpm = await system_settings_gateway.get_default_user_rpm()
except Exception:
    log_event(logger, logging.WARNING, "userRegisterRpmSnapshotFailed", email=email)
    snapshot_rpm = settings.DEFAULT_USER_RPM
```

**Rewrite to (D-09):**
```python
# D-09: Phase 4 always reads DEFAULT_USER_RPM constant; admin DB read deferred to Phase 5
snapshot_rpm = settings.DEFAULT_USER_RPM
# TODO(phase-5): re-introduce dynamic DB read when admin domain ships
```

**Session creation (source lines 287-324) — port verbatim** with the repo rename above.

**Refresh-token rotation (source lines 236-240 — CRITICAL, port verbatim):**
```python
session.token_jti = get_token_jti(new_refresh_token)
session.refresh_token_hash = await hash_password_async(new_refresh_token)
session.expires_at = now() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
await db.commit()
```

**Dummy-hash timing equalizer (source lines 46-53) — port verbatim** (avoids email-enumeration timing leak).

**Divergences:**
- **D-09:** drop `system_settings_gateway` call; always use `settings.DEFAULT_USER_RPM`.
- All `session_repo.*` calls → `user_repo.get_session_* / list_active_sessions_for_user / revoke_session / add_session`.
- `email_service.X(...)` (module instance) → `EmailService.X(...)` (staticmethod class — see email_service entry below).

---

### `api_service/services/email_service.py` (service, event-driven enqueue)

**Analog:** `services/user-service/src/services/email_service.py` (172 lines)

**Imports rewrite (source lines 1-23):**
```python
# source [VERIFIED]:
from common.utils.password import hash_password_async, verify_password_async
from common.utils.timezone import now
from repositories.email_code_repository import EmailCodeRepository  # → merged into UserRepository
from utils.email import normalize_email
```

**Rewrite to:**
```python
from api_service.common.security.password import hash_password_async, verify_password_async
from api_service.common.utils.timezone import now
from api_service.repositories.user_repository import UserRepository  # email_code_* methods
from api_service.common.utils.email import normalize_email
from api_service.core.arq_pool import get_arq_pool  # D-02 NEW
from api_service.core.config import settings
```

**Repository method rewrites (Pitfall 1 — Translation Table):**

| Source call | Target call |
|-------------|-------------|
| `EmailCodeRepository(db).count_created_since(...)` | `UserRepository(db).email_code_count_created_since(...)` |
| `EmailCodeRepository(db).latest_for_email(...)` | `UserRepository(db).email_code_latest_for_email(...)` |
| `EmailCodeRepository(db).latest_unused_for_email(..., for_update=True)` | `UserRepository(db).email_code_latest_unused_for_email(..., for_update=True)` |
| `EmailCodeRepository(db).list_unused_for_email(...)` | `UserRepository(db).email_code_list_unused_for_email(...)` |
| `repo.delete(old_code)` (sync) | **`await repo.email_code_delete(old_code)`** — Pitfall A5: now async |
| `repo.add(verification)` | `repo.email_code_add(verification)` (sync — `session.add`) |

**Verified target signatures** `[VERIFIED: api_service/repositories/user_repository.py:145-200]`.

**D-02 divergence — Class conversion (Pitfall 4):**
```python
# source: services/user-service/src/services/email_service.py:28-41 [VERIFIED]
class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        # ... 6 instance attributes
email_service = EmailService()  # module singleton
```

**Rewrite to staticmethod class (no `__init__`, no module instance):**
```python
class EmailService:
    @staticmethod
    def generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    async def send_verification_code(db: AsyncSession, email: str, purpose: str = "register") -> tuple[bool, str]:
        # ... validate + insert code + commit ...
        pool = get_arq_pool()
        await pool.enqueue_job(_JOB_SEND_VERIFICATION_EMAIL, email, code, purpose)
        return True, "queued"
```

**`get_valid_code_or_raise` (source lines 137-165) — port verbatim including the inner `await db.commit()` (D-11):**
```python
# Pitfall O-3: inner commit MUST stay
if record.error_count >= settings.MAX_CODE_ERRORS:
    record.locked_until = now() + timedelta(hours=settings.CODE_ERROR_LOCK_HOURS)
    await db.commit()  # ← D-11: keep verbatim
    raise InvalidCodeException(detail="Too many invalid verification attempts")
```

**`mark_code_used` (source lines 167-169) — convert to `@staticmethod`:**
```python
@staticmethod
def mark_code_used(record: EmailVerificationCode) -> None:
    record.used_at = now()
    record.error_count = 0
```

**Divergences:**
- **D-02:** SMTP `_send_email()` instance method removed from this file → ARQ job in `core/jobs.py:send_verification_email`. `send_verification_code` now enqueues instead of sending.
- **Pitfall 4:** drop `__init__` and module-level `email_service = EmailService()`. Callers use `EmailService.X(...)` (already corrected in auth_service entry above).
- **D-11:** keep inner `await db.commit()` inside `get_valid_code_or_raise`.

---

### `api_service/controllers/auth.py` (controller, request-response)

**Analog:** `services/user-service/src/controllers/auth.py` (390 lines)

**Imports pattern (source lines 9-46):**
```python
from common.core.exceptions import AuthenticationException, SessionNotFoundException, ServiceUnavailableException
from core.config import settings
from core.dependencies import get_db_session
from models import User
from core.policies import require_active_user
from schemas import AuthBaseResponse, ChangePasswordRequest, ...
from services.auth_service import AuthService
from services.email_service import email_service
from repositories.usage_stat_repository import UsageStatRepository
from gateways.system_settings import system_settings_gateway   # DELETE
```

**Rewrite to:**
```python
from api_service.common.core.exceptions import AuthenticationException, SessionNotFoundException, ServiceUnavailableException
from api_service.core.config import settings
from api_service.core.db import get_db                              # renamed (Pitfall 3)
from api_service.models import User
from api_service.core.policies import require_active_user
from api_service.schemas.auth import (
    AuthBaseResponse, ChangePasswordRequest, ..., VerifyEmailRequest,
)
from api_service.services.auth_service import AuthService
from api_service.services.email_service import EmailService          # class, not module-instance
from api_service.repositories.billing_repository import BillingRepository  # stat_get_user_tpm_last_minute
# DELETE: gateways.system_settings  (D-09 — use settings.DEFAULT_USER_RPM)
```

**Cookie helpers — port verbatim (source lines 55-89):**
```python
USER_ACCESS_COOKIE = "user_access_token"
USER_REFRESH_COOKIE = "user_refresh_token"
USER_COOKIE_PATH = "/"  # Pitfall 6: do not change

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
    # ... refresh cookie identical shape ...
```

**Endpoint pattern (source lines 92-129 register endpoint) — controller is thin:**
```python
@router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, response: Response,
                   db: AsyncSession = Depends(get_db), request_obj: Request = None) -> RegisterResponse:
    user_agent = request_obj.headers.get("user-agent") if request_obj else None
    ip_address = request_obj.client.host if request_obj and request_obj.client else None
    try:
        user = await AuthService.register(db, request)
        user, access_token, refresh_token = await AuthService.login(
            db, user.email, request.password, user_agent, ip_address,
        )
    except Exception:
        logger.exception("用户注册失败")
        raise
    _set_auth_cookies(response, access_token, refresh_token)
    return RegisterResponse(code=201, message="注册成功", data=RegisterResponseData(...))
```

**`/auth/me` endpoint (source lines 277-303) — D-09 divergence:**
```python
# source [VERIFIED]:
current_tpm = await UsageStatRepository(db).get_user_tpm_last_minute(int(current_user.id))
default_rpm = await system_settings_gateway.get_default_user_rpm()
```

**Rewrite to:**
```python
# D-09: drop gateway; D-04 P3 repo merge: UsageStatRepository → BillingRepository
current_tpm = await BillingRepository(db).stat_get_user_tpm_last_minute(int(current_user.id))
default_rpm = settings.DEFAULT_USER_RPM
```

**`/auth/send-email-code` endpoint (source lines 351-370) — D-02 method call rewrite:**
```python
# source [VERIFIED]:
sent, message = await email_service.send_verification_code(db, request.email, request.purpose)
```

**Rewrite to:**
```python
sent, message = await EmailService.send_verification_code(db, request.email, request.purpose)
```

**Router declaration (source line 49):** keep `router = APIRouter(tags=["认证"])` (per-endpoint paths include `/auth/*`). Claude's Discretion (CONTEXT.md) permits switching to `APIRouter(prefix="/auth", tags=["认证"])` + paths-without-`/auth`. Planner picks one — both produce identical final URLs.

**Divergences:**
- **D-09:** drop `system_settings_gateway`, use `settings.DEFAULT_USER_RPM`.
- **Pitfall 3:** `get_db_session` → `get_db`.
- **D-04 (Phase 3):** `UsageStatRepository(db).get_user_tpm_last_minute` → `BillingRepository(db).stat_get_user_tpm_last_minute`.
- `email_service.X(...)` → `EmailService.X(...)`.

---

### `api_service/schemas/keys.py` (schema, request-response)

**Analog:** `services/user-service/src/schemas/keys.py`

**Imports rewrite (source lines 8-12):**
```python
from common.utils.timezone import to_shanghai_naive
from schemas.common import DateTimeModel
from utils.api_key_policy import normalize_allow_ips, normalize_allowed_models
```

**Rewrite to:**
```python
from api_service.common.utils.timezone import to_shanghai_naive
from api_service.schemas.common import DateTimeModel
from api_service.common.utils.api_key_policy import normalize_allow_ips, normalize_allowed_models
```

**Critical field — `ApiKeyItem` exposes `key_prefix` only (NOT `key`) — anti-pattern verbatim (source lines 15-30):**
```python
class ApiKeyItem(DateTimeModel):
    id: int
    key_prefix: str     # ← only this — never the raw key
    name: str
    status: int
    quota_mode: int
    quota_limit: int
    quota_used: int
    allowed_models: Optional[str] = None
    allow_ips: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
```

**`ApiKeyCreateData` returns plaintext `key` only on create response (source lines 57-59) — port verbatim:**
```python
class ApiKeyCreateData(BaseModel):
    key: str     # ← only place plaintext appears in API surface
    item: ApiKeyItem
```

**Divergences:** None.

---

### `api_service/schemas/billing.py` (schema, request-response)

**Analog:** `services/user-service/src/schemas/billing.py`

**Imports rewrite:** `from schemas.common import DateTimeModel` → `from api_service.schemas.common import DateTimeModel`.

**`BalanceResponseData` computed field (source lines 14-25 — port verbatim):**
```python
class BalanceResponseData(BaseModel):
    balance: int
    frozen_amount: int
    used_amount: int
    total_requests: int
    total_tokens: int

    @computed_field
    @property
    def available_balance(self) -> int:
        return self.balance - self.frozen_amount
```

**`ApiCallLogItem.from_orm_instance` (source lines 165-170) — port verbatim** (loads `api_key.name` via the eager-loaded relationship `[VERIFIED: billing_repository.py:237]`):
```python
@classmethod
def from_orm_instance(cls, obj: object) -> "ApiCallLogItem":
    data = {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
    key_rel = getattr(obj, "api_key", None)
    data["api_key_name"] = key_rel.name if key_rel else None
    return cls.model_validate(data)
```

**`UsageAnalyticsRange` literal (source line 97):** `Literal["8h", "24h", "7d", "30d"]` — port verbatim, used by `usage_stat_service` for window dispatch.

**Divergences:** None.

---

### `api_service/services/api_key_service.py` (service, CRUD)

**Analog:** `services/user-service/src/services/api_key_service.py` (196 lines)

**Imports rewrite — only paths change** (`from common.utils.timezone` → `from api_service.common.utils.timezone`; `from utils.api_key_policy` → `from api_service.common.utils.api_key_policy`; `from repositories.X` → `from api_service.repositories.X`).

**No repository method renames needed** — `ApiKeyRepository` is preserved as-is `[VERIFIED: api_service/repositories/api_key_repository.py:11-61]`.

**Plaintext key returned once pattern (source lines 55-73 — port verbatim):**
```python
raw_key = "sk-" + "".join(secrets.choice(_KEY_ALPHABET) for _ in range(46))
key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
api_key = UserApiKey(
    user_id=user_id, key_hash=key_hash, key_prefix=raw_key[:8],
    name=name, status=UserApiKey.STATUS_ACTIVE, ...
)
repo.add(api_key)
await db.commit()
await db.refresh(api_key)
return api_key, raw_key   # ← (model, plaintext) tuple — plaintext only here
```

**Status refresh pattern (source lines 163-173 — port verbatim):**
```python
@staticmethod
def _refresh_status(api_key: UserApiKey) -> None:
    if api_key.status == UserApiKey.STATUS_DISABLED:
        return
    if api_key.expires_at and api_key.expires_at <= now():
        api_key.status = UserApiKey.STATUS_EXPIRED
        return
    if api_key.is_exhausted:
        api_key.status = UserApiKey.STATUS_EXHAUSTED
        return
    api_key.status = UserApiKey.STATUS_ACTIVE
```

**Soft-delete pattern (source lines 127-131 — port verbatim):**
```python
@staticmethod
async def delete(db: AsyncSession, key_id: int, user_id: int) -> None:
    api_key = await ApiKeyService.verify_key_ownership(db, key_id, user_id)
    api_key.deleted_at = now()
    await db.commit()
```

**Divergences:** None besides imports.

---

### `api_service/services/balance_service.py` (service, CRUD with SELECT FOR UPDATE)

**Analog:** `services/user-service/src/services/balance_service.py` (411 lines)

**Imports rewrite (source lines 9-17):**
```python
from common.db import ListParams, PaginatedResult
from repositories import ApiKeyRepository, BalanceTxRepository, TopupOrderRepository, UserRepository
```

**Rewrite to:**
```python
from api_service.common.infra.db.query import ListParams, PaginatedResult
from api_service.repositories.api_key_repository import ApiKeyRepository
from api_service.repositories.billing_repository import BillingRepository      # merged
from api_service.repositories.user_repository import UserRepository
# DELETE: BalanceTxRepository, TopupOrderRepository (merged into BillingRepository)
```

**Critical repo-method rewrites (RESEARCH.md Translation Table):**

| Source call | Target call |
|-------------|-------------|
| `tx_repo = BalanceTxRepository(db)` | `billing_repo = BillingRepository(db)` |
| `tx_repo.exists_by_ref(tx_type=..., ref_type=..., ref_id=...)` | `billing_repo.exists_by_ref(...)` (same kwargs) |
| `tx_repo.add(BalanceTransaction(...))` | `billing_repo.add_tx(BalanceTransaction(...))` |
| `tx_repo.list_for_user(...)` | `billing_repo.list_tx_for_user(...)` |
| `tx_repo.list_all(...)` | `billing_repo.list_tx_all(...)` |
| `TopupOrderRepository(db).get_for_user_by_order_no(...)` | `BillingRepository(db).topup_get_for_user_by_order_no(...)` |

**Verified target signatures** `[VERIFIED: api_service/repositories/billing_repository.py:37-145]`.

**SELECT FOR UPDATE pattern (source lines 60, 102, 150, 214, 253, 297 — port verbatim, only repo class changes):**
```python
# Wallet mutation always loads user with row lock
user = await BalanceService._get_user(db, user_id, for_update=True)
# ... mutate user.balance ...
billing_repo.add_tx(BalanceTransaction(...))
await db.commit()
```

**Idempotency check (source lines 393-404 — port verbatim with repo rename):**
```python
@staticmethod
async def _transaction_exists(db, *, tx_type: int, ref_type: str, ref_id: str) -> bool:
    return await BillingRepository(db).exists_by_ref(
        tx_type=tx_type, ref_type=ref_type, ref_id=ref_id,
    )
```

**`consume_for_call_log` (source lines 37-90) — port verbatim** with renames. This method is used by Phase 6 relay layer, not by Phase 4 controllers, but must compile.

**Divergences:** None semantically; repo-method renames only.

---

### `api_service/services/topup_order_service.py` (service, CRUD)

**Analog:** `services/user-service/src/services/topup_order_service.py` (82 lines)

**Imports rewrite:**
```python
# source:
from common.db import ListParams, PaginatedResult
from repositories import TopupOrderRepository
# target:
from api_service.common.infra.db.query import ListParams, PaginatedResult
from api_service.repositories.billing_repository import BillingRepository
```

**Repo-method rewrites:**

| Source | Target |
|--------|--------|
| `TopupOrderRepository(db).add(order)` | `BillingRepository(db).topup_add(order)` |
| `TopupOrderRepository(db).list_for_user(...)` | `BillingRepository(db).topup_list_for_user(...)` |
| `TopupOrderRepository(db).list_all(...)` | `BillingRepository(db).topup_list_all(...)` |

**Order-number generator (source lines 79-82 — port verbatim):**
```python
@staticmethod
def _generate_order_no() -> str:
    return "TP" + now().strftime("%Y%m%d") + "".join(secrets.choice(_ORDER_ALPHABET) for _ in range(8))
```

**Divergences:** None semantically.

---

### `api_service/services/usage_stat_service.py` (service, aggregate / read-heavy)

**Analog:** `services/user-service/src/services/usage_stat_service.py` (338 lines)

**Imports rewrite:**
```python
# source:
from common.db import ListParams, PaginatedResult
from repositories import UsageStatRepository
from schemas.billing import UsageAnalyticsBucket, UsageAnalyticsBucketCost, ...
# target:
from api_service.common.infra.db.query import ListParams, PaginatedResult
from api_service.repositories.billing_repository import BillingRepository    # merged
from api_service.schemas.billing import UsageAnalyticsBucket, UsageAnalyticsBucketCost, ...
```

**Repo-method rewrites (heavy — 9 call sites):**

| Source | Target |
|--------|--------|
| `UsageStatRepository(db).get_bucket(...)` | `BillingRepository(db).stat_get_bucket(...)` |
| `UsageStatRepository(db).get_user_stats(...)` | `BillingRepository(db).stat_get_user_stats(...)` |
| `UsageStatRepository(db).get_all_stats(...)` | `BillingRepository(db).stat_get_all_stats(...)` |
| `UsageStatRepository(db).list_usage_logs(...)` | `BillingRepository(db).stat_list_usage_logs(...)` |
| `UsageStatRepository(db).list_analytics_logs(...)` | `BillingRepository(db).stat_list_analytics_logs(...)` |
| `UsageStatRepository(db).list_logs_for_hour(...)` | `BillingRepository(db).stat_list_logs_for_hour(...)` |
| `repo.add(bucket)` (UsageStat) | `billing_repo.session.add(bucket)` (no per-row helper — RESEARCH.md Translation Table note) |

**Analytics window dispatch (source lines 198-220) — port verbatim:**
```python
if start is not None and end is not None:
    granularity = "hour" if (end - start) <= timedelta(hours=48) else "day"
    range_label: str | None = "custom"
elif range_name is not None:
    start, end, granularity = UsageStatService._build_usage_analytics_window(range_name, now())
    range_label = range_name
else:
    start, end, granularity = UsageStatService._build_usage_analytics_window("24h", now())
    range_label = "24h"
```

**Pitfall 8:** **Do NOT** add `error_code='invalid_model'` filtering at the service layer — `BillingRepository.stat_list_analytics_logs` / `stat_list_logs_for_hour` already embed it via `_exclude_invalid_model()` `[VERIFIED: billing_repository.py:21-27, 263, 275]`.

**Divergences:** Repo-method renames only.

---

### `api_service/services/voucher_service.py` (service, CRUD with SELECT FOR UPDATE)

**Analog:** `services/user-service/src/services/voucher_service.py` (185 lines)

**Imports rewrite:**
```python
# source:
from common.db import ListParams, PaginatedResult
from repositories import BalanceTxRepository, UserRepository, VoucherRedemptionCodeRepository
# target:
from api_service.common.infra.db.query import ListParams, PaginatedResult
from api_service.repositories.billing_repository import BillingRepository
from api_service.repositories.user_repository import UserRepository
from api_service.repositories.voucher_repository import VoucherRepository     # class renamed
```

**Class rename:** `VoucherRedemptionCodeRepository` → `VoucherRepository` (Phase 3). Same method names `[VERIFIED: api_service/repositories/voucher_repository.py:13-95]`.

**Balance ref_id idempotency (source lines 170-182 — port verbatim with repo rename):**
```python
# source [VERIFIED]:
BalanceTxRepository(db).add(
    BalanceTransaction(
        user_id=user_id,
        type=BalanceTransaction.TYPE_VOUCHER_REDEEM,
        amount=int(code.amount),
        balance_before=balance_before,
        balance_after=int(user.balance),
        ref_type="voucher_code",
        ref_id=str(code.id),       # ← idempotency key
        ...
    )
)
```

**Rewrite to:**
```python
BillingRepository(db).add_tx(
    BalanceTransaction(
        user_id=user_id,
        type=BalanceTransaction.TYPE_VOUCHER_REDEEM,
        amount=int(code.amount),
        balance_before=balance_before,
        balance_after=int(user.balance),
        ref_type="voucher_code",
        ref_id=str(code.id),
        ...
    )
)
```

**Hash normalization (source lines 33-43 — port verbatim, Pitfall 10):**
```python
@staticmethod
def normalize_code(raw_code: str) -> str:
    return raw_code.strip().lower()   # single source of truth — do not double-normalize at controller

@staticmethod
def hash_code(raw_code: str) -> str:
    normalized = VoucherService.normalize_code(raw_code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

**Divergences:** Repo class rename + `add_tx` method name.

---

### `api_service/controllers/keys.py` (controller, request-response)

**Analog:** `services/user-service/src/controllers/keys.py` (107 lines)

**Imports rewrite — same shape as auth.py.** `get_db_session` → `get_db` (Pitfall 3). Schemas from `api_service.schemas.keys` instead of `schemas`.

**APIRouter with prefix (source line 21 — port verbatim):**
```python
router = APIRouter(prefix="/keys", tags=["keys"])
```

**Thin controller endpoint (source lines 24-34 — port verbatim, only deps imports change):**
```python
@router.get("", response_model=ApiResponse[list[ApiKeyItem]], summary="List my API keys")
async def list_keys(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    keys = await ApiKeyService.list(db, int(current_user.id))
    return {
        "code": 200, "message": "success",
        "data": [ApiKeyItem.model_validate(key) for key in keys],
    }
```

**Plaintext-on-create-only pattern (source lines 37-60 — port verbatim):**
```python
key, raw_key = await ApiKeyService.create(db, user_id=int(current_user.id), ...)
return {
    "code": 201, "message": "created",
    "data": {"key": raw_key, "item": ApiKeyItem.model_validate(key)},
}
```

**Provided-fields propagation (source line 80 — port verbatim):** `provided_fields=set(payload.model_fields_set)` — service uses this to distinguish "field absent" from "field set to None".

**Divergences:** None.

---

### `api_service/controllers/billing.py` (controller, request-response)

**Analog:** `services/user-service/src/controllers/billing.py` (309 lines)

**Imports rewrite:**
```python
# source:
from common.api import PaginatedResponse
from common.db import ListParams
from common.utils.timezone import now
from core.dependencies import get_db_session
from schemas import ApiCallLogItem, ApiResponse, BalanceResponseData, ...
# target:
from api_service.common.api.pagination import PaginatedResponse
from api_service.common.infra.db.query import ListParams
from api_service.common.utils.timezone import now
from api_service.core.db import get_db
from api_service.schemas.common import ApiResponse
from api_service.schemas.billing import (
    ApiCallLogItem, BalanceResponseData, BalanceTransactionItem,
    TopupOrderItem, UsageAnalyticsData, UsageAnalyticsRange,
    UsageStatItem, VoucherRedeemRequest, VoucherRedeemResponseData,
    VoucherRedemptionItem,
)
```

**`_build_list_params` helper (source lines 44-65 — port verbatim):**
```python
def _build_list_params(*, page=1, page_size=20, start=None, end=None,
                      time_field=None, default_days=30, order_by=None) -> ListParams:
    params = ListParams(
        page=page, page_size=page_size, order_by=order_by,
        time_field=time_field, start=start, end=end,
        max_span_days=MAX_BILLING_RANGE_DAYS,
    )
    if time_field is not None:
        params.validate_time_range(default_end=now(), default_days=default_days)
    return params
```

**Pagination response build pattern (source lines 105-114 — port verbatim — used by 4 endpoints):**
```python
return {
    "code": 200, "message": "success",
    "data": {
        "items": [BalanceTransactionItem.model_validate(item) for item in result.items],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
    },
}
```

**Key-ownership pre-check pattern (source lines 209-210, 240-241, 280-281 — port verbatim):**
```python
if api_key_id is not None:
    await ApiKeyService.verify_key_ownership(db, api_key_id, int(current_user.id))
```

**Usage logs return path (source lines 290-308 — uses `ApiCallLogItem.from_orm_instance` because `api_key.name` is eager-loaded):**
```python
result = await UsageStatService.list_usage_logs(db, params=params, user_id=int(current_user.id), ...)
return {
    "code": 200, "message": "success",
    "data": {
        "items": [ApiCallLogItem.from_orm_instance(item) for item in result.items],
        ...
    },
}
```

**Divergences:** None besides imports.

---

### `api_service/schemas/model_catalog.py` (schema, read-only — D-06)

**Analog:** `services/admin-service/src/schemas/model_catalog.py` (read-only subset)

**Imports rewrite:**
```python
# source:
from schemas.common import AdminBaseResponse, DateTimeModel
from common.api import PaginatedResponse
# target:
from api_service.schemas.common import DateTimeModel  # NO AdminBaseResponse in Phase 4
from api_service.common.api.pagination import PaginatedResponse
```

**Port these classes verbatim** (source lines 13-68): `ModelVendorItem`, `ModelVendorBrief`, `ModelCategoryItem`, `ModelCategoryBrief`, `SupportedModelItem`, `SupportedModelDetail`.

**Do NOT port** (admin write — Phase 5): `ModelVendorCreate`, `ModelVendorUpdate`, `ModelCategoryCreate`, `ModelCategoryUpdate`, `SupportedModelCreate`, `SupportedModelUpdate`, all `*Response(AdminBaseResponse)` classes.

**`SupportedModelItem` shape (source lines 47-64 — preserve relationships):**
```python
class SupportedModelItem(DateTimeModel):
    id: int
    slug: str
    routing_slug: str | None = None
    name: str
    summary: str | None = None
    description: str | None = None
    sale_input_per_million: int | None = None
    sale_output_per_million: int | None = None
    sale_cached_input_per_million: int | None = None
    capability_tags: list[str] = Field(default_factory=list)
    context_window: int | None = None
    max_output_tokens: int | None = None
    is_reasoning_model: bool
    is_active: bool
    sort_order: int
    vendor: ModelVendorBrief
    categories: list[ModelCategoryBrief] = Field(default_factory=list)


class SupportedModelDetail(SupportedModelItem):
    pass
```

**Divergences:**
- **D-06:** read-only subset only.
- **D-10:** uses `AuthBaseResponse` envelope (via `ApiResponse[T]`) rather than `AdminBaseResponse` (which doesn't exist yet in Phase 4).

---

### `api_service/services/model_catalog_service.py` (service, read-heavy + cache)

**Analogs (composed):**
- Cache scaffolding: `services/user-service/src/gateways/model_catalog.py:16-105`
- Read methods: `services/admin-service/src/services/model_catalog_service.py:108-180` (`list_vendors`, `list_categories`, `list_models`, `get_model_by_slug`, `_vendor_item`, `_category_item`, `_model_item`)

**Cache constants (source lines 17-21 of gateway — port verbatim):**
```python
_CACHE_PREFIX = "mc:"
_VENDORS_TTL = 300
_CATEGORIES_TTL = 300
_MODELS_LIST_TTL = 120
_MODEL_DETAIL_TTL = 300
```

**Cache key + fetch pattern (gateway lines 35-46 — adapt: HTTP fetch → direct repo call):**
```python
# source [VERIFIED]:
async def list_vendors(self, *, page: int = 1, page_size: int = 100) -> dict:
    cache_key = f"{_CACHE_PREFIX}vendors:{page}:{page_size}"

    async def _fetch() -> dict:
        return await self._get(
            "/api/v1/internal/model-catalog/vendors",
            query_params={"page": page, "page_size": page_size},
        )

    return await cache_get_or_fetch(cache_key, _fetch, _VENDORS_TTL)
```

**Rewrite the inner `_fetch` to call repo + serializer directly:**
```python
from api_service.common.infra.cache import cache_get_or_fetch
from api_service.repositories.model_catalog_repository import (
    ModelVendorRepository, ModelCategoryRepository, ModelCatalogRepository,
)
from api_service.schemas.model_catalog import (
    ModelVendorItem, ModelCategoryItem, SupportedModelItem, SupportedModelDetail,
    ModelVendorBrief, ModelCategoryBrief,
)

class ModelCatalogReadService:
    @staticmethod
    async def list_vendors(db: AsyncSession, *, page: int = 1, page_size: int = 100) -> dict:
        cache_key = f"{_CACHE_PREFIX}vendors:{page}:{page_size}"

        async def _fetch() -> dict:
            vendors, total = await ModelVendorRepository(db).list_vendors(
                page=page, page_size=page_size, active_only=True,
            )
            return {
                "items": [ModelVendorItem.model_validate(v).model_dump() for v in vendors],
                "total": total, "page": page, "page_size": page_size,
            }
        return await cache_get_or_fetch(cache_key, _fetch, _VENDORS_TTL)
```

**Serializer pattern (admin service lines 44-106 — port `_vendor_item`, `_category_item`, `_model_item` verbatim):**
```python
@staticmethod
def _model_item(model: ModelCatalog, *, detail: bool = False) -> SupportedModelItem:
    categories = [
        ModelCategoryBrief(
            key=link.category.key, name=link.category.name, sort_order=link.sort_order,
        )
        for link in sorted(model.category_links, key=lambda item: item.sort_order)
        if link.category is not None
    ]
    payload = {
        "id": model.id, "slug": model.slug, "routing_slug": model.routing_slug,
        "name": model.name, "summary": model.summary, ...
        "vendor": ModelVendorBrief(
            id=model.vendor.id, slug=model.vendor.slug, name=model.vendor.name, logo_url=model.vendor.logo_url,
        ),
        "categories": categories,
    }
    if detail:
        return SupportedModelDetail(**payload)
    return SupportedModelItem(**payload)
```

**`active_only=True` parameter (D-04):** every read call passes `active_only=True` — the user-facing surface filters to active models/vendors only.

**Eager loading (verified):** `ModelCatalogRepository._with_relationships` already calls `selectinload(ModelCatalog.vendor)` + `selectinload(ModelCatalog.category_links).selectinload(ModelCatalogCategoryMap.category)` `[VERIFIED: api_service/repositories/model_catalog_repository.py:89-95]`.

**Cache invalidation:** None at Phase 4 (D-05 — admin write invalidation deferred to Phase 5; cache is correct-up-to-TTL).

**Divergences:**
- HTTP gateway → direct service call (removes one network hop).
- Class name `ModelCatalogReadService` (not `ModelCatalogService`) to leave the latter free for Phase 5 admin write variant (D-07).
- `active_only=True` hardcoded — D-04 says user surface always filters.

---

### `api_service/controllers/model_catalog.py` (controller, request-response)

**Analog:** `services/user-service/src/controllers/model_catalog.py` (54 lines)

**Imports rewrite (source lines 6-9):**
```python
# source [VERIFIED]:
from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse
from gateways.model_catalog import model_catalog_gateway   # DELETE
```

**Rewrite to:**
```python
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.core.db import get_db
from api_service.services.model_catalog_service import ModelCatalogReadService
```

**Endpoint pattern (source lines 16-22 — replace gateway call with service call):**
```python
# source [VERIFIED]:
@router.get("/model-vendors", summary="List model vendors")
async def list_model_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
):
    payload = await _gateway.list_vendors(page=page, page_size=page_size)
    return JSONResponse(content=payload)
```

**Rewrite to:**
```python
@router.get("/model-vendors", summary="List model vendors")
async def list_model_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    payload = await ModelCatalogReadService.list_vendors(db, page=page, page_size=page_size)
    return JSONResponse(content=payload)
```

**Slug pattern validator (source line 50 — port verbatim):**
```python
slug: str = Path(..., pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=120)
```

**Router declaration (source line 11):**
```python
router = APIRouter(tags=["model-catalog"])
```

**Endpoints (4 — port URL/method/pattern verbatim):** `GET /model-vendors`, `GET /models/categories`, `GET /models`, `GET /models/{slug}`.

**Divergences:**
- Gateway call → direct service call.
- Adds `db: AsyncSession = Depends(get_db)` parameter to every handler (service is stateless but needs DB).
- D-04: no `pool_model_configs` JOIN; `active_only=True` enforced by the service layer.

---

### `api_service/core/router.py` (MODIFY — include_router calls)

**Analog:** itself + RESEARCH.md Code Examples "Controller mounting".

**Current state (verified `api_service/core/router.py:1-12`):** `api_router = APIRouter(prefix="/api/v1")` with Phase 4 placeholder comments.

**Append after `api_router = APIRouter(...)` line:**
```python
# Phase 4: User domain routes
from api_service.controllers import auth, keys, billing, model_catalog

api_router.include_router(auth.router)             # /auth/* — 10 endpoints
api_router.include_router(keys.router)             # /keys — 5 endpoints (prefix in router)
api_router.include_router(billing.router)          # /billing/* — 8 endpoints (prefix in router)
api_router.include_router(model_catalog.router)    # /model-vendors, /models, /models/categories, /models/{slug}
```

**Verified `app.include_router(api_router)` at `api_service/main.py:164`** — no main.py change required for routes.

**Divergences:** None.

---

### `api_service/schemas/__init__.py` (NEW — export aggregator)

**Analog:** `services/user-service/src/schemas/__init__.py` (~83 lines)

**Pattern (source lines 1-39):** module exports flatten the four files into a single namespace. Port the same `__all__` list with rewritten import paths:
```python
# source [VERIFIED]:
from schemas.auth import ChangePasswordRequest, ..., VerifyEmailRequest
from schemas.billing import ApiCallLogItem, ...
from schemas.common import ApiResponse, AuthBaseResponse, AuthErrorResponse, DateTimeModel
from schemas.keys import ApiKeyCreateData, ApiKeyCreateRequest, ApiKeyItem, ApiKeyUpdateRequest
```

**Rewrite to:**
```python
from api_service.schemas.auth import ChangePasswordRequest, ..., VerifyEmailRequest
from api_service.schemas.billing import ApiCallLogItem, ...
from api_service.schemas.common import ApiResponse, AuthBaseResponse, AuthErrorResponse, DateTimeModel
from api_service.schemas.keys import ApiKeyCreateData, ApiKeyCreateRequest, ApiKeyItem, ApiKeyUpdateRequest
```

**Add in Wave 3** when model_catalog schemas land:
```python
from api_service.schemas.model_catalog import (
    ModelCategoryBrief, ModelCategoryItem,
    ModelVendorBrief, ModelVendorItem,
    SupportedModelDetail, SupportedModelItem,
)
```

**Divergences:** Built up incrementally over Waves 1-3 (not all at once).

---

### Test files (test, unit/integration)

**Analog:** `services/api-service/tests/test_auth_dependencies.py` (mock style) + `services/api-service/tests/test_repositories_import.py` (import-shape tests).

**Note:** user-service has no `tests/` directory (verified: `ls services/user-service/tests/ → not found`). All test files are NEW.

**Mocking pattern (test_auth_dependencies.py lines 80-91 — port for service tests):**
```python
# CITED: api-service tests/test_auth_dependencies.py:80-91 [VERIFIED]
@pytest.mark.asyncio
@patch("api_service.core.dependencies.user.decode_token", return_value=None)
async def test_get_current_user_invalid_token(mock_decode):
    """Raises InvalidTokenException when token cannot be decoded."""
    request = _make_request()
    db = AsyncMock()

    with pytest.raises(InvalidTokenException):
        await get_current_user(
            request=request, credentials=_make_credentials("bad-token"), access_token=None, db=db
        )
```

**Adapt for service tests** (mock the repo classes the same way controllers/services mock the dependency injection target):
```python
@pytest.mark.asyncio
@patch("api_service.services.api_key_service.ApiKeyRepository")
async def test_create_returns_plaintext_once(mock_repo_cls):
    db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.count_for_user = AsyncMock(return_value=0)
    mock_repo_cls.return_value = mock_repo
    key, raw_key = await ApiKeyService.create(db, user_id=1, name="test")
    assert raw_key.startswith("sk-")
    assert len(raw_key) == 49
    assert ApiKeyItem.model_validate(key).key_prefix == raw_key[:8]
```

**Integration test for ARQ enqueue (D-02):**
```python
@pytest.mark.asyncio
@patch("api_service.services.email_service.get_arq_pool")
async def test_send_verification_code_enqueues_arq(mock_pool_fn):
    pool = AsyncMock()
    mock_pool_fn.return_value = pool
    db = AsyncMock()
    # ... set up email_code_count_created_since to return 0, latest_for_email None ...
    sent, _ = await EmailService.send_verification_code(db, "user@example.com", "register")
    assert sent is True
    pool.enqueue_job.assert_called_once()
    args = pool.enqueue_job.call_args.args
    assert args[0] == "send_verification_email"
```

**`conftest.py` shared fixtures** (NEW — required for the test pyramid):
```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_user():
    from unittest.mock import MagicMock
    user = MagicMock()
    user.id = 1
    user.uid = "u_test01"
    user.status = 1
    user.email = "test@example.com"
    return user

@pytest.fixture
def mock_db():
    return AsyncMock()
```

**Divergences:** All tests are new — no source analog. Pattern is api-service's own existing mocking style (`unittest.mock.patch` + `AsyncMock`), NOT a real DB fixture.

---

## Shared Patterns

### Authentication

**Source:** `api_service/core/policies.py` (this phase — see entry above) + `api_service/core/dependencies/user.py` (Phase 3, verified).

**Apply to:** Every controller endpoint in `auth.py` (except `/auth/register`, `/auth/login`, `/auth/login-with-code`, `/auth/logout`, `/auth/refresh`, `/auth/reset-password`, `/auth/send-email-code`, `/auth/verify-email`), all of `keys.py`, all of `billing.py`. Public endpoints in `model_catalog.py` need NO auth (per source behavior).

**Excerpt (target — to be ported from user-service `core/policies.py:12-19`):**
```python
async def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.status == 0:
        raise UserDisabledException()
    if current_user.status == 2:
        raise EmailNotVerifiedException()
    return current_user
```

**Usage in controllers (one line per protected endpoint):**
```python
current_user: User = Depends(require_active_user),
```

---

### Error Handling

**Source:** `api_service/common/core/exceptions.py` (Phase 2 — already in place; verified via RESEARCH.md `[VERIFIED]` flags).

**Apply to:** All services and controllers — raise domain exceptions, let the global `register_exception_handlers` (Phase 1, verified `api_service/main.py:160`) map them.

**Exception classes used in this phase** (from RESEARCH.md "Code Context" + source review):
- Auth: `AuthenticationException`, `EmailAlreadyExistsException`, `EmailNotVerifiedException`, `InvalidCredentialsException`, `InvalidTokenException`, `SessionExpiredException`, `SessionNotFoundException`, `SessionRevokedException`, `TokenExpiredException`, `UserDisabledException`, `UserNotFoundException`, `WeakPasswordException`, `ServiceUnavailableException`
- Codes: `CodeExpiredException`, `CodeNotFoundException`, `InvalidCodeException`
- Keys: `ApiKeyDisabledException`, `ApiKeyExhaustedException`, `ApiKeyExpiredException`, `ApiKeyIpNotAllowedException`, `ApiKeyModelNotAllowedException`, `ApiKeyNotFoundException`
- Generic: `ValidationException`, `NotFoundException`

**Controller-level pattern (source `controllers/auth.py:108-115` — port verbatim):**
```python
try:
    user = await AuthService.register(db, request)
    user, access_token, refresh_token = await AuthService.login(...)
except Exception:
    logger.exception("用户注册失败")
    raise
```

---

### Validation

**Source:** `api_service/schemas/auth.py`, `keys.py`, `billing.py` field validators (this phase — port from user-service schemas).

**Apply to:** All controller endpoints — Pydantic v2 validates request body at the FastAPI boundary, schema field validators run normalization before the service layer sees data.

**Normalization pattern (source `schemas/auth.py:24-27` — port verbatim):**
```python
@field_validator("email", mode="before")
@classmethod
def normalize_email_field(cls, value: str) -> str:
    return normalize_email(value)
```

**Password strength via model_validator (source `schemas/auth.py:43-48` — port verbatim):**
```python
@model_validator(mode="after")
def validate_password_strength(self):
    ok, message = check_password_strength(self.password, lang=self.lang)
    if not ok:
        raise ValueError(message)
    return self
```

---

### Logging

**Source:** `api_service/common/observability.py:300+` — `log_event(logger, level, "eventName", **fields)` (verified).

**Apply to:** All services and controllers — never use string interpolation in log calls.

**Pattern (source `auth_service.py:122` — port verbatim):**
```python
log_event(logger, logging.INFO, "userLoginAttempt", email=email)
log_event(logger, logging.WARNING, "userLoginLocked", uid=user.uid)
log_event(logger, logging.INFO, "userPasswordReset", uid=user.uid)
```

**Anti-pattern (do NOT do):**
```python
logger.info("user %s registered with email %s", uid, email)   # ← string interpolation; banned
```

---

### Transaction Boundary

**Source:** `services/user-service/CLAUDE.md` 服务规范 — `get_db()` is rollback-on-exception only; service/controller must explicitly `await db.commit()`.

**Apply to:** Every service method that writes to DB.

**Pattern (`auth_service.py:107` — port verbatim):**
```python
user_repo.add(user)
EmailService.mark_code_used(code_record)
await db.commit()      # ← service explicitly commits
await db.refresh(user)
```

**Wallet mutation pattern (`balance_service.py:60-83` — port verbatim, with `SELECT FOR UPDATE`):**
```python
user = await BalanceService._get_user(db, user_id, for_update=True)
# ... mutate user.balance / user.frozen_amount ...
billing_repo.add_tx(BalanceTransaction(...))
await db.commit()
```

**Inner commit in `EmailService.get_valid_code_or_raise` (D-11, source line 160 — keep verbatim):**
```python
if record.error_count >= settings.MAX_CODE_ERRORS:
    record.locked_until = now() + timedelta(hours=settings.CODE_ERROR_LOCK_HOURS)
    await db.commit()        # ← D-11: keep
    raise InvalidCodeException(...)
```

---

### Idempotency (ref_id Dedup)

**Source:** RESEARCH.md Pattern 5 + `balance_service.py:53-58, 104-109, 152-157` — every `BalanceTransaction` insert is preceded by `exists_by_ref` check.

**Apply to:** Every wallet-mutating method (`consume_for_call_log`, `freeze`, `settle`, `refund`, `topup`, `redeem_code`).

**Pattern (source — port verbatim with `tx_repo` → `billing_repo` rename):**
```python
if await billing_repo.exists_by_ref(
    tx_type=BalanceTransaction.TYPE_CONSUME,
    ref_type="api_call",
    ref_id=request_id,
):
    return True   # already applied — short-circuit
```

**ref_id values per tx type:**
- `api_call` → `request_id` (consume / freeze / settle / refund)
- `topup_order` → `order_no`
- `voucher_code` → `str(code.id)`

---

### Cookie Set/Clear (auth endpoints only)

**Source:** `controllers/auth.py:55-89` (this phase — port verbatim).

**Apply to:** `auth.py` only. Controllers in `keys.py`, `billing.py`, `model_catalog.py` never touch cookies.

**Cookie names (locked):**
```python
USER_ACCESS_COOKIE = "user_access_token"      # ← matches Phase 3 get_current_user alias
USER_REFRESH_COOKIE = "user_refresh_token"
USER_COOKIE_PATH = "/"                         # Pitfall 6: do not change
```

**Settings used:** `COOKIE_SECURE`, `COOKIE_SAMESITE` (verified `common/config.py:57-58`), `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`.

---

### Settings (config injection)

**Source:** `api_service/core/config.py` singleton + RESEARCH.md Settings Gap.

**Apply to:** Every service/controller that needs configuration — never read env vars directly, never instantiate `ApiServiceSettings()` ad hoc.

**Import pattern (RESEARCH.md Translation Table):**
```python
from api_service.core.config import settings
```

**Settings that **must be added** in Wave 0 (RESEARCH.md Settings Gap, exact defaults):**
```python
LOGIN_LOCK_DURATION_HOURS: int = 1
MAX_CODE_ERRORS: int = 5
CODE_ERROR_LOCK_HOURS: int = 24
CODE_DAILY_SEND_LIMIT: int = 3
VERIFICATION_CODE_RETENTION_DAYS: int = 7
MIN_TOPUP_AMOUNT: int = 1_000_000
MAX_TOPUP_AMOUNT: int = 10_000_000_000
USER_WORKER_CONCURRENCY: int = 5
USER_JOB_TIMEOUT_SECONDS: int = 300
DEFAULT_USER_RPM: int = 20       # D-09 — drop-in for system_settings_gateway
```

**Already-present (do NOT re-add):** `SMTP_*`, `EMAIL_CODE_EXPIRE_MINUTES`, `MAX_API_KEYS_PER_USER`, `LOGIN_MAX_FAILURES`, `JWT_*`, `COOKIE_*`, `PASSWORD_*`, `WORKER_QUEUE_REDIS_URL`, `CACHE_REDIS_URL`.

---

### Cache (Redis db/2)

**Source:** `api_service/common/infra/cache.py:45-66` — `cache_get_or_fetch(key, fetch, ttl_seconds)`.

**Apply to:** `model_catalog_service.py` only (4 cache keys: `mc:vendors:*`, `mc:categories:*`, `mc:models:*`, `mc:model:{slug}`).

**Pattern (cache.py lines 45-66 — verified, fail-open):**
```python
async def cache_get_or_fetch(key, fetch, ttl_seconds):
    try:
        r = get_cache_redis()
        cached = await r.get(key)
        if cached is not None:
            return json.loads(cached)
    except Exception:
        logger.debug("cache read failed for %s, falling through to fetch", key)
    result = await fetch()
    try:
        r = get_cache_redis()
        await r.set(key, json.dumps(result, ensure_ascii=False), ex=ttl_seconds)
    except Exception:
        logger.debug("cache write failed for %s", key)
    return result
```

**TTLs (per D-05, sourced from `gateways/model_catalog.py:18-21`):** vendors=300s, categories=300s, models=120s, model_detail=300s.

**Invalidation:** None at Phase 4 (D-05 — admin write invalidation deferred to Phase 5).

---

## No Analog Found

None. Every file has a source analog (direct user-service port, cross-domain admin-service port, or composed pattern from two analogs as documented above).

---

## Metadata

**Analog search scope:**
- `services/user-service/src/{controllers,services,schemas,utils,core}/` — primary source
- `services/admin-service/src/{services,schemas}/model_catalog*` — D-06 cross-domain copy
- `services/api-service/api_service/{repositories,common,core}/` — Phase 1-3 baseline + pattern donors
- `services/api-service/tests/` — test mocking style donor

**Files scanned:** 27 source files + 9 target Phase 1-3 baseline files = 36 reads.

**Pattern extraction date:** 2026-05-19

**Confidence by file class:**
- utility / config / schema ports: **HIGH** — line-for-line copies with explicit import rewrites.
- service ports: **HIGH** — only repo-method renames + import paths; semantics preserved per `[VERIFIED]` flags.
- `core/arq_pool.py`: **MEDIUM** — new module composed of two analogs (cache.py accessor shape + jobs.py RedisSettings builder). RESEARCH.md Pattern 2 supplies the skeleton.
- `services/model_catalog_service.py`: **MEDIUM-HIGH** — read methods exist in admin-service; cache wrap is from user-service gateway. Two-source composition introduces non-zero merge risk.
- test files: **MEDIUM** — analog is api-service's own test style, but the user domain has no existing test scaffolding to mirror — patterns must be invented within the established mocking idiom.
