"""FastAPI dependency injection: global singletons + API key auth with cache."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, Optional

import cachetools
from fastapi import Depends, Header, HTTPException, Request

from common.core.exceptions import ServiceUnavailableException
from common.internal import InternalServiceError, InternalServiceResponseError
from common.observability import set_uid
from gateways.user_identity import ValidatedApiKey

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from gateways.admin_config import AdminConfigGateway
    from gateways.calllog import CallLogGateway
    from gateways.calllog_batch import BatchCallLogGateway
    from gateways.user_identity import UserIdentityGateway
    from services.calllog_buffer import CallLogBuffer
    from services.channel_affinity import ChannelAffinityStore
    from services.channel_selector import ChannelSelector
    from services.config_manager import ConfigManager
    from services.inference_client import InferenceClient
    from services.rate_limiter import RateLimiter
    from core.config import RouterSettings

# Global singletons — initialized in lifespan
_inference_client: Optional["InferenceClient"] = None
_config_manager: Optional["ConfigManager"] = None
_settings: Optional["RouterSettings"] = None
_channel_selector: Optional["ChannelSelector"] = None
_redis: Optional["aioredis.Redis"] = None
_calllog_buffer: Optional["CallLogBuffer"] = None
_rate_limiter: Optional["RateLimiter"] = None
_affinity_store: Optional["ChannelAffinityStore"] = None

# Gateway instances
_user_identity_gateway: Optional["UserIdentityGateway"] = None
_admin_config_gateway: Optional["AdminConfigGateway"] = None
_calllog_gateway: Optional["CallLogGateway"] = None
_batch_calllog_gateway: Optional["BatchCallLogGateway"] = None

# API key cache: sha256(raw_key) -> ValidatedApiKey
_API_KEY_CACHE_TTL = 60.0
_api_key_cache: cachetools.TTLCache[str, ValidatedApiKey] = cachetools.TTLCache(
    maxsize=10000, ttl=_API_KEY_CACHE_TTL,
)


def init_globals(
    *,
    config_manager: "ConfigManager",
    settings: "RouterSettings",
    inference_client: "InferenceClient",
    channel_selector: "ChannelSelector",
    redis_conn: "aioredis.Redis | None" = None,
    calllog_buffer: "CallLogBuffer | None" = None,
    rate_limiter: "RateLimiter | None" = None,
    affinity_store: "ChannelAffinityStore | None" = None,
) -> None:
    global _inference_client, _config_manager, _settings, _channel_selector
    global _redis, _calllog_buffer, _rate_limiter, _affinity_store
    global _user_identity_gateway, _admin_config_gateway, _calllog_gateway, _batch_calllog_gateway

    _settings = settings
    _inference_client = inference_client
    _config_manager = config_manager
    _channel_selector = channel_selector
    _redis = redis_conn
    _calllog_buffer = calllog_buffer
    _rate_limiter = rate_limiter
    _affinity_store = affinity_store

    from gateways.admin_config import AdminConfigGateway
    from gateways.calllog import CallLogGateway
    from gateways.calllog_batch import BatchCallLogGateway
    from gateways.user_identity import UserIdentityGateway

    _user_identity_gateway = UserIdentityGateway(settings)
    _admin_config_gateway = AdminConfigGateway(settings)
    _calllog_gateway = CallLogGateway(calllog_buffer)
    _batch_calllog_gateway = BatchCallLogGateway(settings)


def get_config_manager() -> "ConfigManager":
    if _config_manager is None:
        raise RuntimeError("config manager not initialized")
    return _config_manager


def get_inference_client() -> "InferenceClient":
    if _inference_client is None:
        raise RuntimeError("inference client not initialized")
    return _inference_client


def get_settings() -> "RouterSettings":
    if _settings is None:
        raise RuntimeError("settings not initialized")
    return _settings


def get_channel_selector() -> "ChannelSelector":
    if _channel_selector is None:
        raise RuntimeError("channel selector not initialized")
    return _channel_selector


def get_redis() -> "aioredis.Redis | None":
    return _redis


def get_calllog_buffer() -> "CallLogBuffer | None":
    return _calllog_buffer


def get_rate_limiter() -> "RateLimiter | None":
    return _rate_limiter


def get_affinity_store() -> "ChannelAffinityStore | None":
    return _affinity_store


def get_user_identity_gateway() -> "UserIdentityGateway":
    if _user_identity_gateway is None:
        raise RuntimeError("user identity gateway not initialized")
    return _user_identity_gateway


def get_admin_config_gateway() -> "AdminConfigGateway":
    if _admin_config_gateway is None:
        raise RuntimeError("admin config gateway not initialized")
    return _admin_config_gateway


def get_calllog_gateway() -> "CallLogGateway":
    if _calllog_gateway is None:
        raise RuntimeError("calllog gateway not initialized")
    return _calllog_gateway


def get_batch_calllog_gateway() -> "BatchCallLogGateway":
    if _batch_calllog_gateway is None:
        raise RuntimeError("batch calllog gateway not initialized")
    return _batch_calllog_gateway


def extract_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if first_hop:
            return first_hop
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return str(host) if host else None


async def _extract_requested_model(request: Request) -> str | None:
    if request.method.upper() not in {"POST", "PUT", "PATCH"}:
        return None
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" not in content_type:
        return None
    try:
        payload = json.loads((await request.body()) or b"{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    model = payload.get("model")
    if model is None:
        return None
    return str(model).strip() or None


async def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> ValidatedApiKey:
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
        request.state.api_key_principal = cached
        request.state.api_key_prefix = raw_key[:8]
        set_uid(str(cached.user_id))
        return cached

    try:
        principal = await get_user_identity_gateway().validate_api_key(
            api_key=raw_key,
            model=await _extract_requested_model(request),
            client_ip=extract_client_ip(request),
        )
    except InternalServiceResponseError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=401, detail="invalid api key") from exc
        raise HTTPException(
            status_code=exc.status_code or 403,
            detail=exc.detail or "api key rejected",
        ) from exc
    except (InternalServiceError, ServiceUnavailableException) as exc:
        raise HTTPException(status_code=503, detail="user-service unavailable") from exc

    _api_key_cache[cache_key] = principal
    request.state.api_key_principal = principal
    request.state.api_key_prefix = raw_key[:8]
    set_uid(str(principal.user_id))
    return principal


async def require_rate_limit(
    request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
) -> None:
    """Check global and user-level rate limits. Raises 429 if exceeded."""
    limiter = get_rate_limiter()
    if limiter is None:
        return

    from services.rate_limiter import RateLimitExceeded

    # Effective RPM precedence: user-level override > runtime default > env fallback.
    # `user_rpm_limit` lives on `users.rpm_limit` (admin-controlled per user, snapshot
    # of the global default at registration time, modifiable only by super admins).
    # When NULL the limiter falls back to the runtime `default_user_rpm` (sourced from
    # admin-service `routing_settings`, refreshed every ~60s by ConfigManager) or,
    # ultimately, the env value baked into rate_limiter.
    #
    # On top of that: `system_rpm_cap` is a system-wide hard upper bound. We apply
    # `min(effective_rpm, system_rpm_cap)` so admins can clamp blast-radius without
    # editing every user row. NULL cap = no clamping.
    effective_rpm = principal.user_rpm_limit
    runtime_cfg = None
    if effective_rpm is None:
        try:
            runtime_cfg = get_config_manager().load()
            runtime_default = runtime_cfg.get("default_user_rpm")
            if isinstance(runtime_default, int) and runtime_default >= 1:
                effective_rpm = runtime_default
        except RuntimeError:
            # Config manager not started yet — fall through to env default below.
            pass

    # Pull the system cap from the same runtime config (load once if possible).
    try:
        if runtime_cfg is None:
            runtime_cfg = get_config_manager().load()
        system_cap = runtime_cfg.get("system_rpm_cap")
    except RuntimeError:
        system_cap = None
    if isinstance(system_cap, int) and system_cap >= 1:
        if effective_rpm is None or effective_rpm > system_cap:
            effective_rpm = system_cap

    try:
        await limiter.check_global()
        await limiter.check_user(principal.user_id, rpm_override=effective_rpm)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "message": exc.message,
                    "type": "rate_limit_error",
                    "code": "rate_limit_exceeded",
                }
            },
            headers={
                "Retry-After": str(exc.retry_after),
                "X-RateLimit-Limit-Requests": str(
                    effective_rpm or get_settings().RATE_LIMIT_DEFAULT_USER_RPM
                ),
            },
        ) from exc
