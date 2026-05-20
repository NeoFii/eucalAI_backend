"""GET /v1/models — Model listing endpoint (D-19).

Returns all available models to authenticated users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.relay.auth import ValidatedApiKey, require_api_key
from app.relay.dependencies import get_routing_config_cache

router = APIRouter()


@router.get("/v1/models")
async def list_models(
    principal: ValidatedApiKey = Depends(require_api_key),
):
    """Return all available models (D-19)."""
    config_cache = get_routing_config_cache()
    config = config_cache.load()
    all_models = sorted(config.get("user_facing_aliases") or [])

    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "eucal-ai",
            }
            for model_id in all_models
        ],
    }
