"""FastAPI dependency injection: global singletons + API key auth."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Header, HTTPException, Request

from router_service.config import ModelPathsConfig
from router_service.services.router_engine import HybridIntegratedDifficultyRouter
from router_service.utils.runtime_config import RuntimeConfigStore

# Global singletons — initialized in lifespan
_router_engine: Optional[HybridIntegratedDifficultyRouter] = None
_runtime_store: Optional[RuntimeConfigStore] = None


def init_globals(
    *,
    runtime_config_path: str,
    model_paths: ModelPathsConfig,
) -> None:
    global _router_engine, _runtime_store
    _runtime_store = RuntimeConfigStore(runtime_config_path)
    _runtime_store.ensure_exists()
    _router_engine = HybridIntegratedDifficultyRouter(
        model_paths,
        runtime_config=_runtime_store.load(),
    )


def get_runtime_store() -> RuntimeConfigStore:
    if _runtime_store is None:
        raise RuntimeError("runtime store not initialized")
    return _runtime_store


def get_router_engine() -> HybridIntegratedDifficultyRouter:
    if _router_engine is None:
        raise RuntimeError("router engine not initialized")
    return _router_engine


def require_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> str:
    bearer = (authorization or "").strip()
    if bearer.lower().startswith("bearer ") and bearer[7:].strip():
        return bearer[7:].strip()
    if x_api_key and str(x_api_key).strip():
        return str(x_api_key).strip()
    raise HTTPException(status_code=401, detail="missing api key")
