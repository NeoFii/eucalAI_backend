"""Meta endpoints: /ready, /v1/models, /v1/router/config."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from core.dependencies import get_config_manager, require_api_key

router = APIRouter()


@router.get("/ready")
def ready() -> Dict[str, Any]:
    return {"status": "ok", "service": "router-service"}


@router.get("/v1/models")
def list_models(_: str = Depends(require_api_key)) -> Dict[str, Any]:
    """Expose only the public-facing aliases (default `auto`).

    Underlying tier model names are intentionally NOT advertised so that
    clients are guided to the alias entry-point. Add additional public
    aliases via the `routing_settings.user_facing_aliases` admin setting.
    """
    config = get_config_manager().load()
    aliases = config.get("user_facing_aliases") or [config["router_alias"]]
    seen: list[str] = []
    for item in aliases:
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
        "user_facing_aliases": config.get("user_facing_aliases") or [config["router_alias"]],
        "route_order": config["route_order"],
        "weights": config["weights"],
        "score_bands": config["score_bands_raw"],
        "tier_model_map": config["tier_model_map"],
        "config_version": cm.config_version,
        "config_source": cm.config_source,
        "last_updated_at": cm.last_updated_at.isoformat() if cm.last_updated_at else None,
    }
