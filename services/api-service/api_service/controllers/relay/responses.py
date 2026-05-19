"""POST /v1/responses — OpenAI Responses API compatible endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api_service.relay.auth import ValidatedApiKey, require_api_key
from api_service.relay.rate_limiter import require_rate_limit
from api_service.relay.schemas.responses import ResponsesRequest
from api_service.relay.adapters.openai_responses import OpenAIResponsesAdapter
from api_service.relay.lifecycle import CallLifecycle

router = APIRouter()


@router.post("/v1/responses")
async def responses(
    request: ResponsesRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    adapter = OpenAIResponsesAdapter()
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
