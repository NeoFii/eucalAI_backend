"""FastAPI dependency injection: global singletons + API key auth."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import Header, HTTPException, Request

from common.core.exceptions import ServiceUnavailableException
from common.internal import InternalServiceError, InternalServiceResponseError
from router_service.config import ModelPathsConfig
from router_service.gateway import UserIdentityGateway, ValidatedApiKey

if TYPE_CHECKING:
    from router_service.services.router_engine import HybridIntegratedDifficultyRouter
    from router_service.utils.runtime_config import RuntimeConfigStore

# Global singletons — initialized in lifespan
_router_engine: Optional["HybridIntegratedDifficultyRouter"] = None
_runtime_store: Optional["RuntimeConfigStore"] = None


def init_globals(
    *,
    runtime_config_path: str,
    model_paths: ModelPathsConfig,
) -> None:
    global _router_engine, _runtime_store
    from router_service.services.router_engine import HybridIntegratedDifficultyRouter
    from router_service.utils.runtime_config import RuntimeConfigStore

    _runtime_store = RuntimeConfigStore(runtime_config_path)
    _runtime_store.ensure_exists()
    _router_engine = HybridIntegratedDifficultyRouter(
        model_paths,
        runtime_config=_runtime_store.load(),
    )


def get_runtime_store() -> "RuntimeConfigStore":
    if _runtime_store is None:
        raise RuntimeError("runtime store not initialized")
    return _runtime_store


def get_router_engine() -> "HybridIntegratedDifficultyRouter":
    if _router_engine is None:
        raise RuntimeError("router engine not initialized")
    return _router_engine


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

    request.state.api_key_principal = principal
    return principal
