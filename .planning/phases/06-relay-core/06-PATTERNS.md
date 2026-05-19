# Phase 6: Relay Core - Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 12 (new files to create)
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `api_service/relay/__init__.py` | config | — | — | N/A (empty init) |
| `api_service/relay/auth.py` | middleware | request-response | `router-service/src/core/dependencies.py` | exact |
| `api_service/relay/billing.py` | service | CRUD | `api_service/services/balance_service.py` | role-match |
| `api_service/relay/config_cache.py` | service | request-response | `router-service/src/services/config_manager.py` | exact |
| `api_service/relay/runtime_config.py` | utility | transform | `router-service/src/utils/runtime_config.py` | exact |
| `api_service/relay/call_log_writer.py` | service | event-driven | `api_service/services/balance_service.py` (fire-and-forget pattern) | role-match |
| `api_service/relay/channel_selector.py` | service | request-response | `router-service/src/services/channel_selector.py` | exact |
| `api_service/relay/channel_affinity.py` | service | request-response | `router-service/src/services/channel_affinity.py` | exact |
| `api_service/relay/routing.py` | service | request-response | `router-service/src/services/routing.py` | exact |
| `api_service/relay/upstream.py` | utility | transform | `router-service/src/services/upstream.py` | exact |
| `api_service/relay/inference_client.py` | service | request-response | `router-service/src/services/inference_client.py` | exact |
| `api_service/core/config.py` (modify) | config | — | `api_service/core/config.py` | self |

## Pattern Assignments

### `api_service/relay/auth.py` (middleware, request-response)

**Analog:** `services/router-service/src/core/dependencies.py` (lines 1-237)

**Imports pattern** (lines 1-18):
```python
from __future__ import annotations

import hashlib
import json
from typing import Any

import cachetools
from fastapi import Header, HTTPException, Request
import redis.asyncio as aioredis

from api_service.common.infra.cache import get_cache_redis
from api_service.services.api_key_service import ApiKeyService
from api_service.common.observability import set_uid
```

**Core auth pattern** (lines 194-236 — three-tier lookup: in-process TTLCache -> Redis -> DB):
```python
# API key cache: sha256(raw_key) -> dict principal
_API_KEY_CACHE_TTL = 60.0
_api_key_cache: cachetools.TTLCache[str, dict] = cachetools.TTLCache(
    maxsize=2048, ttl=_API_KEY_CACHE_TTL,
)

async def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> "ValidatedApiKey":
    bearer = (authorization or "").strip()
    raw_key: str | None = None
    if bearer.lower().startswith("bearer ") and bearer[7:].strip():
        raw_key = bearer[7:].strip()
    elif x_api_key and str(x_api_key).strip():
        raw_key = str(x_api_key).strip()
    if not raw_key:
        raise HTTPException(status_code=401, detail="missing api key")

    cache_key = hashlib.sha256(raw_key.encode()).hexdigest()
    cached = _api_key_cache.get(cache_key)
    if cached is not None:
        # ... return cached principal
        return cached

    # Tier 2: Redis (shared across requests in same worker)
    # Tier 3: DB (authoritative source via ApiKeyService.validate_by_hash)
```

**Error handling pattern** (lines 222-231):
```python
except InternalServiceResponseError as exc:
    if exc.status_code == 404:
        raise HTTPException(status_code=401, detail="invalid api key") from exc
    raise HTTPException(
        status_code=exc.status_code or 403,
        detail=exc.detail or "api key rejected",
    ) from exc
```

---

### `api_service/relay/billing.py` (service, CRUD)

**Analog:** `services/api-service/api_service/services/balance_service.py` (lines 1-434)

**Imports pattern** (lines 1-16):
```python
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from api_service.common.core.exceptions import ValidationException
from api_service.services.balance_service import BalanceService
from api_service.core.config import settings

logger = logging.getLogger(__name__)
```

**Service class pattern** (lines 20-30 — @staticmethod + explicit params):
```python
class RelayBillingService:
    """Encapsulates pre-consume / settle / refund lifecycle.

    Redis is the hot-path source for quota; DB is persisted via
    asyncio.create_task (fire-and-forget).
    """

    @staticmethod
    async def pre_consume(
        cache_redis: aioredis.Redis,
        user_id: int,
        estimated_cost: int,
        balance: int,
    ) -> tuple[int, bool]:
        """Pre-consume quota. Returns (pre_consumed_amount, is_trusted)."""
        ...
```

**Error handling pattern** (balance_service lines 55-70 — idempotent check + explicit error):
```python
if cost <= 0:
    return True
billing_repo = BillingRepository(db)
if await billing_repo.exists_by_ref(
    tx_type=BalanceTransaction.TYPE_CONSUME,
    ref_type="api_call",
    ref_id=request_id,
):
    return True  # idempotent
```

---

### `api_service/relay/config_cache.py` (service, request-response)

**Analog:** `services/router-service/src/services/config_manager.py` (lines 1-148)

**Imports pattern** (lines 1-18):
```python
from __future__ import annotations

import logging
from typing import Any, Dict

import redis.asyncio as aioredis

from api_service.common.observability import log_event
from api_service.relay.runtime_config import normalize_runtime_config

logger = logging.getLogger(__name__)
```

**Core singleton pattern** (lines 23-112 — start/load/check_and_reload):
```python
class RoutingConfigCache:
    """Per-worker singleton. Checks version on every request, reloads on mismatch."""

    def __init__(self, cache_redis: aioredis.Redis) -> None:
        self._redis = cache_redis
        self._cached_config: Dict[str, Any] | None = None
        self._version: int = 0

    async def start(self, db_session_factory) -> None:
        """Must succeed or raise RuntimeError (D-12)."""
        config = await self._load_from_db(db_session_factory)
        if not config.get("model_channels") and not config.get("model_providers"):
            raise RuntimeError("RoutingConfigCache: no model config found in DB")
        self._cached_config = config
        try:
            v = await self._redis.get("routing_config:version")
            self._version = int(v) if v else 0
        except Exception:
            self._version = 0

    def load(self) -> Dict[str, Any]:
        """Synchronous read — called on every request."""
        if self._cached_config is None:
            raise RuntimeError("RoutingConfigCache not started")
        return self._cached_config

    async def check_and_reload(self, db_session_factory) -> None:
        """Called at request start. GET version, reload if changed."""
        try:
            v = await self._redis.get("routing_config:version")
            current = int(v) if v else 0
        except Exception:
            return  # Redis down -> use cached
        if current != self._version:
            config = await self._load_from_db(db_session_factory)
            self._cached_config = config
            self._version = current
```

**Startup failure pattern** (config_manager lines 85-99):
```python
if not local.get("model_providers"):
    raise RuntimeError(
        "local runtime_config.json has no model_providers — "
        "router-service cannot start without provider configuration"
    )
```

---

### `api_service/relay/runtime_config.py` (utility, transform)

**Analog:** `services/router-service/src/utils/runtime_config.py` (lines 1-310)

**Direct port.** Copy `normalize_runtime_config()` and `parse_score_bands()` verbatim. Adapt imports:

```python
# Original imports from router-service:
from core.config import (
    DEFAULT_ROUTER_ALIAS,
    FIVEWAY_DEFAULT_WEIGHTS,
    FIVEWAY_ROUTE_ORDER,
)

# Adapted for api-service — define constants locally or import from relay constants:
DEFAULT_ROUTER_ALIAS = "auto"
FIVEWAY_ROUTE_ORDER = ("纠错", "工具调用", "通用任务", "任务拆解", "编程")
FIVEWAY_DEFAULT_WEIGHTS = {k: 1.0 for k in FIVEWAY_ROUTE_ORDER}
```

**Key function signature** (lines 83-251):
```python
def normalize_runtime_config(raw: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Validate and normalize raw routing config dict.
    
    Returns standardized dict with keys:
    router_alias, user_facing_aliases, route_order, weights,
    score_bands_raw, score_bands, tier_model_map, model_providers,
    model_channels, model_prices, default_user_rpm, system_rpm_cap
    """
```

---

### `api_service/relay/call_log_writer.py` (service, event-driven)

**Analog:** `services/api-service/api_service/services/balance_service.py` (fire-and-forget pattern from Phase 4 email)

**Imports pattern:**
```python
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api_service.models import ApiCallLog
from api_service.services.balance_service import BalanceService

logger = logging.getLogger(__name__)
```

**Fire-and-forget pattern** (asyncio.create_task with independent session):
```python
async def _write_call_log_create(
    session_factory: async_sessionmaker[AsyncSession],
    log_data: dict,
) -> None:
    """Independent session — fire-and-forget. D-15."""
    async with session_factory() as session:
        try:
            log = ApiCallLog(**log_data)
            session.add(log)
            await session.commit()
        except Exception as exc:
            logger.warning("call_log create failed: %s", exc)


async def _write_call_log_update_and_settle(
    session_factory: async_sessionmaker[AsyncSession],
    request_id: str,
    update_data: dict,
    billing_params: dict,
    max_retries: int = 3,
) -> None:
    """Update call log + settle billing in same task (D-17)."""
    ...

# Usage:
# asyncio.create_task(_write_call_log_create(get_session_factory(), initial_data))
```

---

### `api_service/relay/channel_selector.py` (service, request-response)

**Analog:** `services/router-service/src/services/channel_selector.py` (lines 1-155)

**Direct port — copy verbatim with import path adjustments.**

**Imports pattern** (lines 1-13):
```python
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from api_service.common.core.exceptions import APIException

logger = logging.getLogger(__name__)

_DEFAULT_COOLDOWN_SECONDS = 30.0
```

**Core class pattern** (lines 27-155):
```python
class ChannelSelector:
    """Select a channel using weighted round-robin with priority-tier descent and auto-disable."""

    def __init__(
        self,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
        auto_disable_enabled: bool = True,
        auto_disable_threshold: int = 5,
        auto_disable_cooldown_seconds: float = 300.0,
    ) -> None:
        self._cooldown = cooldown_seconds
        self._auto_disable_enabled = auto_disable_enabled
        self._auto_disable_threshold = auto_disable_threshold
        self._auto_disable_cooldown = auto_disable_cooldown_seconds

        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._failures: dict[str, float] = {}
        self._failure_counts: dict[str, int] = {}
        self._disabled_until: dict[str, float] = {}
        self._health_cache: dict[str, str] = {}
```

---

### `api_service/relay/channel_affinity.py` (service, request-response)

**Analog:** `services/router-service/src/services/channel_affinity.py` (lines 1-54)

**Direct port — copy verbatim with import path adjustments.**

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cachetools

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "affinity:"


class ChannelAffinityStore:
    def __init__(
        self,
        *,
        redis: "aioredis.Redis | None",
        ttl: int = 300,  # D-22: TTL 300s
        lru_maxsize: int = 10000,
    ) -> None:
        ...
```

---

### `api_service/relay/routing.py` (service, request-response)

**Analog:** `services/router-service/src/services/routing.py` (lines 1-259)

**Imports pattern** (lines 1-12):
```python
from __future__ import annotations

import logging
from typing import Any

from api_service.relay.config_cache import RoutingConfigCache
from api_service.relay.inference_client import InferenceClient
from api_service.relay.channel_selector import ChannelSelector
from api_service.relay.channel_affinity import ChannelAffinityStore
from api_service.relay.upstream import resolve_model_channel_target, normalize_api_base

logger = logging.getLogger(__name__)
```

**Core orchestration pattern** (lines 19-174 — route_and_resolve):
```python
async def route_and_resolve(
    *,
    requested_model: str,
    messages: list[dict[str, Any]],
    request_id: str,
    config_cache: RoutingConfigCache,
    inference_client: InferenceClient,
    channel_selector: ChannelSelector,
    affinity_store: ChannelAffinityStore | None = None,
    affinity_key: str | None = None,
) -> tuple[str, dict[str, str], dict[str, Any] | None, dict[str, Any]]:
    """Validate model, route via inference-service, resolve upstream target."""
    config = config_cache.load()
    ...
```

**Key difference from analog:** Dependencies passed as explicit params instead of module-level `get_*()` singletons. This aligns with api-service's DI pattern.

---

### `api_service/relay/upstream.py` (utility, transform)

**Analog:** `services/router-service/src/services/upstream.py` (lines 1-124)

**Direct port — copy verbatim.** Pure functions, no state.

```python
from __future__ import annotations

import re
from typing import Any, Dict
from urllib.parse import urlparse

_BLOCKED_HOSTS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "metadata.google.internal", "169.254.169.254",
})


def _validate_upstream_url(url: str) -> None:
    ...

def normalize_api_base(value: str) -> str:
    ...

def resolve_model_channel_target(
    logical_model: str,
    model_channels: Dict[str, list],
    channel_selector: Any,
    *,
    excluded_slugs: frozenset[str] | None = None,
    retry_tier: int = 0,
    rate_limited_accounts: frozenset[int] | None = None,
) -> Dict[str, str]:
    ...
```

---

### `api_service/relay/inference_client.py` (service, request-response)

**Analog:** `services/router-service/src/services/inference_client.py` (lines 1-182)

**Direct port with import path adjustments.**

**Imports pattern** (lines 1-10):
```python
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx

from api_service.common.observability import (
    REQUEST_ID_HEADER, TRACE_ID_HEADER,
    get_request_id, get_trace_id, log_event,
)

logger = logging.getLogger(__name__)
```

**Core class pattern** (lines 26-182):
```python
@dataclass
class ClassifyResult:
    success: bool
    data: Dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    http_status: int | None = None


class InferenceClient:
    """Async HTTP client for inference-service /internal/v1/classify.
    
    Includes retry (5xx/connection errors) and circuit breaker.
    """

    def __init__(
        self,
        base_url: str,
        secret: str,
        timeout: float = 10.0,
        max_retries: int = 1,
        retry_backoff: float = 0.2,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_cooldown: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )
        ...

    async def close(self) -> None:
        await self._client.aclose()
```

---

### `api_service/core/config.py` (modify — add TRUST_QUOTA)

**Analog:** self (lines 93-104 — existing Relay section)

**Pattern for adding new config** (lines 93-104):
```python
    # -- Relay -----------------------------------------------------------------
    CHANNEL_MAX_RETRIES: int = 2
    CHANNEL_COOLDOWN_SECONDS: float = 30.0
    CHANNEL_AUTO_DISABLE_ENABLED: bool = True
    CHANNEL_AUTO_DISABLE_FAILURE_THRESHOLD: int = 5
    # ... existing fields ...

    # New fields to add:
    TRUST_QUOTA: int = 10_000_000  # 10 yuan in micro-units (D-04)
    RELAY_BILLING_FALLBACK_COST: int = 100_000  # 0.1 yuan fallback (D-05)
```

---

## Shared Patterns

### Authentication (Redis + DB fallback)
**Source:** `services/router-service/src/core/dependencies.py` lines 50-54 + 194-236
**Apply to:** `relay/auth.py`
```python
# Three-tier: in-process TTLCache -> Redis GET -> DB query
_api_key_cache: cachetools.TTLCache[str, ValidatedApiKey] = cachetools.TTLCache(
    maxsize=2048, ttl=60.0,
)
# Redis key format: token:{sha256_hash}
# DB fallback: ApiKeyService.validate_by_hash(db, key_hash, model=..., client_ip=...)
```

### Error Handling (Redis fail-open)
**Source:** `services/api-service/api_service/common/infra/cache.py` lines 45-66
**Apply to:** `relay/auth.py`, `relay/billing.py`, `relay/config_cache.py`, `relay/channel_affinity.py`
```python
# All Redis operations wrapped in try/except with fallback
try:
    cached = await r.get(key)
    if cached is not None:
        return json.loads(cached)
except Exception:
    logger.debug("cache read failed for %s, falling through to fetch", key)
# Fall through to DB or use cached value
```

### Service Singleton Registration (Lifespan)
**Source:** `services/api-service/api_service/core/lifespan.py` lines 1-99
**Apply to:** `relay/config_cache.py`, `relay/inference_client.py`, `relay/channel_selector.py`
```python
# Register in LifespanRegistry with priority ordering:
# RoutingConfigCache: priority=20 (must start before relay endpoints accept traffic)
# InferenceClient: priority=25
# ChannelSelector: priority=25

registry.register(
    name="routing_config_cache",
    init_fn=_init_routing_config_cache,
    shutdown_fn=None,  # stateless in-memory, no cleanup needed
    priority=20,
)
registry.register(
    name="inference_client",
    init_fn=_init_inference_client,
    shutdown_fn=_close_inference_client,
    priority=25,
)
```

### Fire-and-Forget DB Write
**Source:** Phase 4 email pattern + `balance_service.py` session pattern
**Apply to:** `relay/call_log_writer.py`
```python
# CRITICAL: create_task must use independent session (D-15)
# Never reuse request-scoped session in background tasks
async def _background_write(session_factory, data):
    async with session_factory() as session:
        try:
            ...
            await session.commit()
        except Exception as exc:
            logger.warning("background write failed: %s", exc)

# Caller:
asyncio.create_task(_background_write(get_session_factory(), data))
```

### Module-Level Singleton Getters
**Source:** `services/router-service/src/core/dependencies.py` lines 33-138
**Apply to:** All relay modules that need cross-module access
```python
# Module-level singleton pattern (initialized in lifespan)
_routing_config_cache: RoutingConfigCache | None = None
_inference_client: InferenceClient | None = None
_channel_selector: ChannelSelector | None = None

def get_routing_config_cache() -> RoutingConfigCache:
    if _routing_config_cache is None:
        raise RuntimeError("RoutingConfigCache not initialized")
    return _routing_config_cache

def init_relay_globals(
    *,
    config_cache: RoutingConfigCache,
    inference_client: InferenceClient,
    channel_selector: ChannelSelector,
    affinity_store: ChannelAffinityStore | None = None,
) -> None:
    global _routing_config_cache, _inference_client, _channel_selector
    ...
```

### Logging Pattern
**Source:** `services/api-service/api_service/common/observability.py` lines 1-50
**Apply to:** All relay modules
```python
# Use module-level logger
logger = logging.getLogger(__name__)

# Structured events via log_event for important state changes
from api_service.common.observability import log_event
log_event(logger, logging.INFO, "configReloaded", version=new_version)

# Warning for non-critical failures
logger.warning("call_log create failed: %s", exc)
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | All files have strong analogs from router-service or api-service |

## Metadata

**Analog search scope:** `services/router-service/src/`, `services/api-service/api_service/`
**Files scanned:** 15 analog candidates read
**Pattern extraction date:** 2026-05-19
