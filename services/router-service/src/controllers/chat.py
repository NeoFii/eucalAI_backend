"""POST /v1/chat/completions — OpenAI Chat Completions protocol."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from core.dependencies import require_api_key, require_rate_limit
from gateways.user_identity import ValidatedApiKey
from schemas.requests import ChatCompletionRequest
from services.adapters.openai_chat import OpenAIChatAdapter
from services.call_lifecycle import CallLifecycle

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
