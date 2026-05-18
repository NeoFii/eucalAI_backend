"""POST /v1/anthropic/messages — Anthropic Messages API compatible endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from core.dependencies import get_config_manager, require_api_key, require_rate_limit
from gateways.user_identity import ValidatedApiKey
from schemas.anthropic import AnthropicMessagesRequest
from services.adapters.anthropic_messages import AnthropicMessagesAdapter
from services.call_lifecycle import CallLifecycle

router = APIRouter()


@router.get("/v1/anthropic/v1/models")
@router.get("/v1/anthropic/models")
async def list_anthropic_models(
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
):
    config = get_config_manager().load()
    aliases = config.get("user_facing_aliases") or [config["router_alias"]]
    seen: list[str] = []
    for item in aliases:
        if item not in seen:
            seen.append(item)
    return JSONResponse(content={
        "data": [
            {
                "id": item,
                "type": "model",
                "display_name": item,
                "created_at": "2024-01-01T00:00:00Z",
            }
            for item in seen
        ],
    })


@router.post("/v1/anthropic/v1/messages")
@router.post("/v1/anthropic/messages")
async def messages(
    request: AnthropicMessagesRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    adapter = AnthropicMessagesAdapter()
    openai_messages, payload, ctx = adapter.parse_request(request)
    lifecycle = CallLifecycle(
        adapter=adapter,
        principal=principal,
        raw_request=raw_request,
        openai_messages=openai_messages,
        forward_payload=payload,
        is_stream=request.stream,
        requested_model=str(request.model).strip(),
        protocol_context=ctx,
    )
    return await lifecycle.execute()
