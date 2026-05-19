"""GET /v1/models — Model listing endpoint (D-19, D-20).

Returns models filtered by user's allowed_models permission.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api_service.relay.auth import ValidatedApiKey, require_api_key
from api_service.relay.dependencies import get_routing_config_cache

router = APIRouter()


@router.get("/v1/models")
async def list_models(
    principal: ValidatedApiKey = Depends(require_api_key),
):
    """Return available models filtered by user permissions (D-19, D-20)."""
    config_cache = get_routing_config_cache()
    config = config_cache.load()
    all_models = config.get("user_facing_aliases") or []

    # D-20: If allowed_models is set, filter to intersection
    if principal.allowed_models:
        allowed_set = set(
            m.strip() for m in principal.allowed_models.split(",") if m.strip()
        )
        visible_models = [m for m in all_models if m in allowed_set]
    else:
        visible_models = list(all_models)

    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "eucal-ai",
            }
            for model_id in visible_models
        ],
    }
