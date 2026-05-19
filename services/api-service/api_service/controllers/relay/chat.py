"""POST /v1/chat/completions — OpenAI Chat Completions protocol."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api_service.relay.auth import ValidatedApiKey, require_api_key
from api_service.relay.rate_limiter import require_rate_limit
from api_service.relay.schemas.chat import ChatCompletionRequest
from api_service.relay.adapters.openai_chat import OpenAIChatAdapter
from api_service.relay.lifecycle import CallLifecycle

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    adapter = OpenAIChatAdapter()
    messages, payload, ctx = adapter.parse_request(request)
    lifecycle = CallLifecycle(
        adapter=adapter,
        principal=principal,
        raw_request=raw_request,
        openai_messages=messages,
        forward_payload=payload,
        is_stream=request.stream,
        requested_model=str(request.model).strip(),
        protocol_context=ctx,
    )
    return await lifecycle.execute()
