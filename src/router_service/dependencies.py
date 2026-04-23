"""FastAPI dependency injection: global singletons + API key auth with cache."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, Optional

import cachetools
from fastapi import Header, HTTPException, Request

from common.core.exceptions import ServiceUnavailableException
from common.internal import InternalServiceError, InternalServiceResponseError
from router_service.gateway import UserIdentityGateway, ValidatedApiKey

if TYPE_CHECKING:
    from router_service.services.inference_client import InferenceClient
    from router_service.settings import RouterSettings
    from router_service.utils.runtime_config import RuntimeConfigStore

# Global singletons — initialized in lifespan
_inference_client: Optional["InferenceClient"] = None
_runtime_store: Optional["RuntimeConfigStore"] = None
_settings: Optional["RouterSettings"] = None

# API key cache: sha256(raw_key) -> ValidatedApiKey
_API_KEY_CACHE_TTL = 60.0
_api_key_cache: cachetools.TTLCache[str, ValidatedApiKey] = cachetools.TTLCache(
    maxsize=10000, ttl=_API_KEY_CACHE_TTL,
)


def init_globals(
    *,
    runtime_config_path: str,
    settings: "RouterSettings",
    inference_client: "InferenceClient",
) -> None:
    global _inference_client, _runtime_store, _settings
    from router_service.utils.runtime_config import RuntimeConfigStore

    _settings = settings
    _inference_client = inference_client
    _runtime_store = RuntimeConfigStore(runtime_config_path)
    _runtime_store.ensure_exists()


def get_runtime_store() -> "RuntimeConfigStore":
    if _runtime_store is None:
        raise RuntimeError("runtime store not initialized")
    return _runtime_store


def get_inference_client() -> "InferenceClient":
    if _inference_client is None:
        raise RuntimeError("inference client not initialized")
    return _inference_client


def get_settings() -> "RouterSettings":
    if _settings is None:
        raise RuntimeError("settings not initialized")
    return _settings


def _extract_client_ip(request: Request) -> str | None:
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

    # Check cache first
    cache_key = hashlib.sha256(raw_key.encode()).hexdigest()
    cached = _api_key_cache.get(cache_key)
    if cached is not None:
        request.state.api_key_principal = cached
        return cached

    try:
        principal = await UserIdentityGateway.validate_api_key(
            api_key=raw_key,
            model=await _extract_requested_model(request),
            client_ip=_extract_client_ip(request),
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

    # Cache successful validation
    _api_key_cache[cache_key] = principal

    request.state.api_key_principal = principal
    return principal
