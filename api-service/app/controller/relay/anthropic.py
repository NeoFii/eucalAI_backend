"""POST /v1/anthropic/messages — Anthropic Messages API compatible endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.relay.auth import ValidatedApiKey, require_api_key
from app.relay.rate_limiter import require_rate_limit
from app.relay.schemas.anthropic import AnthropicMessagesRequest
from app.relay.adapters.anthropic_messages import AnthropicMessagesAdapter
from app.relay.lifecycle import CallLifecycle

router = APIRouter()


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
