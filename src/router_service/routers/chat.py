"""POST /v1/chat/completions — v3: always invoke upstream, no routing data in response."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict

import litellm
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from router_service.dependencies import get_router_engine, get_runtime_store, require_api_key
from router_service.logging import log_routing_decision, log_upstream_call, get_app_logger
from router_service.schemas import ChatCompletionRequest
from router_service.services.upstream import resolve_model_provider_target, strip_think_tags
from router_service.utils.text import stringify_message_content

router = APIRouter()
logger = get_app_logger()


@router.post("/v1/chat/completions")
def chat_completions(
    request: ChatCompletionRequest,
    _: str = Depends(require_api_key),
):
    t_start = time.monotonic()
    request_payload = request.model_dump(mode="python")
    is_stream = bool(request_payload.get("stream"))
    requested_model = str(request.model).strip()
    request_id = f"chat-{uuid.uuid4().hex[:12]}"

    # Extract input preview
    input_preview = ""
    if request.messages:
        for msg in reversed(request.messages):
            if str(msg.get("role", "")).lower() == "user":
                input_preview = stringify_message_content(msg.get("content", ""))
                break
        if not input_preview:
            input_preview = stringify_message_content(request.messages[-1].get("content", ""))

    config = get_runtime_store().load()
    engine = get_router_engine()

    # Routing decision
    route_result = None
    selected_model = requested_model
    if requested_model == config["router_alias"]:
        route_result = engine.predict_chat_messages(
            request.messages,
            request_id=request_id,
            runtime_config=config,
        )
        selected_model = route_result["selected_model"]

        # Log routing decision (internal only, not returned to client)
        log_routing_decision(
            request_id=request_id,
            requested_model=requested_model,
            scores_0_2=route_result.get("scores_0_2"),
            proto_weighted_0_2=route_result.get("proto_weighted_0_2"),
            total_score_0_10=route_result.get("total_score_0_10"),
            score_source=route_result.get("score_source"),
            routing_tier=route_result.get("routing_tier"),
            selected_model=selected_model,
            input_preview=input_preview,
            messages_count=len(request.messages),
            is_stream=is_stream,
        )
    elif requested_model not in config["model_providers"]:
        raise HTTPException(status_code=404, detail=f"unsupported model: {requested_model}")

    # Upstream invocation via litellm
    target_info = resolve_model_provider_target(selected_model, config["model_providers"])
    upstream_model = target_info["upstream_model"]
    upstream_api_base = target_info["api_base"]
    upstream_api_key = target_info["api_key"]

    forward_payload = dict(request_payload)
    forward_payload.pop("model", None)
    forward_payload.pop("stream", None)

    t_upstream = time.monotonic()
    try:
        litellm_response = litellm.completion(
            model=upstream_model,
            messages=forward_payload.pop("messages"),
            api_key=upstream_api_key,
            api_base=upstream_api_base,
            base_url=upstream_api_base,
            custom_llm_provider="openai",
            stream=is_stream,
            timeout=45.0,
            **{k: v for k, v in forward_payload.items() if k not in ("model",)},
        )
    except Exception as exc:
        upstream_latency_ms = (time.monotonic() - t_upstream) * 1000
        log_upstream_call(
            request_id=request_id,
            selected_model=selected_model,
            provider_slug=target_info["provider_slug"],
            upstream_model=upstream_model,
            api_base=upstream_api_base,
            status_code=502, ok=False,
            latency_ms=upstream_latency_ms,
            is_stream=is_stream,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc))
    upstream_latency_ms = (time.monotonic() - t_upstream) * 1000

    headers = {
        "X-Router-Selected-Model": selected_model,
        "X-Router-Provider": target_info["provider_slug"],
    }

    if is_stream:
        def _stream_sse():
            collected_content = ""
            try:
                for chunk in litellm_response:
                    chunk_dict = chunk.model_dump(exclude_none=True)
                    # v3: model field = actual selected model
                    chunk_dict["model"] = selected_model
                    # Clean reasoning_content
                    choices = chunk_dict.get("choices") or []
                    for c in choices:
                        delta = c.get("delta") or {}
                        delta.pop("reasoning_content", None)
                        psf = delta.get("provider_specific_fields")
                        if isinstance(psf, dict):
                            psf.pop("reasoning_content", None)
                        dc = delta.get("content")
                        if isinstance(dc, str):
                            collected_content += dc
                    yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                final_latency = (time.monotonic() - t_upstream) * 1000
                log_upstream_call(
                    request_id=request_id,
                    selected_model=selected_model,
                    provider_slug=target_info["provider_slug"],
                    upstream_model=upstream_model,
                    api_base=upstream_api_base,
                    status_code=200, ok=True,
                    latency_ms=final_latency,
                    is_stream=True,
                    response_preview=collected_content[:300],
                )

        return StreamingResponse(
            _stream_sse(),
            media_type="text/event-stream",
            headers={**headers, "cache-control": "no-cache", "connection": "keep-alive"},
        )

    # Non-streaming
    response_payload = litellm_response.model_dump(exclude_none=True)
    # v3: model field = actual selected model, no router data injected
    response_payload["model"] = selected_model

    # Strip <think> tags from content
    choices = response_payload.get("choices") or []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and "<think>" in content:
                message["content"] = strip_think_tags(content)

    resp_preview = ""
    try:
        if choices:
            msg = (choices[0].get("message") or {})
            resp_preview = str(msg.get("content") or "")[:300]
    except Exception:
        pass

    log_upstream_call(
        request_id=request_id,
        selected_model=selected_model,
        provider_slug=target_info["provider_slug"],
        upstream_model=upstream_model,
        api_base=upstream_api_base,
        status_code=200, ok=True,
        latency_ms=upstream_latency_ms,
        is_stream=False,
        response_preview=resp_preview,
    )

    return JSONResponse(content=response_payload, headers=headers)
