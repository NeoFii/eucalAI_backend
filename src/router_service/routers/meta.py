"""Meta endpoints: /ready, /v1/models, /v1/router/config."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from router_service.dependencies import get_config_manager, require_api_key

router = APIRouter()


@router.get("/ready")
def ready() -> Dict[str, Any]:
    return {"status": "ok", "service": "router-service"}


@router.get("/v1/models")
def list_models(_: str = Depends(require_api_key)) -> Dict[str, Any]:
    config = get_config_manager().load()
    models = [config["router_alias"]] + [
        config["tier_model_map"][tier] for tier in sorted(config["tier_model_map"])
    ]
    seen: list[str] = []
    for item in models:
        if item not in seen:
            seen.append(item)
    return {
        "object": "list",
        "data": [{"id": item, "object": "model", "owned_by": "router-service"} for item in seen],
    }


@router.get("/v1/router/config")
def get_router_config(_: str = Depends(require_api_key)) -> Dict[str, Any]:
    cm = get_config_manager()
    config = cm.load()
    return {
        "router_alias": config["router_alias"],
        "route_order": config["route_order"],
        "weights": config["weights"],
        "score_bands": config["score_bands_raw"],
        "tier_model_map": config["tier_model_map"],
        "config_version": cm.config_version,
        "config_source": cm.config_source,
        "last_updated_at": cm.last_updated_at.isoformat() if cm.last_updated_at else None,
    }
