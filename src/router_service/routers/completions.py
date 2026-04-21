"""POST /v1/completions — async legacy completions endpoint."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List

import litellm
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from router_service.dependencies import get_inference_client, get_runtime_store, require_api_key
from router_service.logging import log_routing_decision, log_upstream_call
from router_service.schemas.requests import CompletionRequest
from router_service.services.upstream import resolve_model_provider_target, strip_think_tags

router = APIRouter()


def _extract_messages_from_prompt(prompt: str | List[str]) -> List[Dict[str, Any]]:
    if isinstance(prompt, list):
        content = "\n".join(str(item) for item in prompt)
    else:
        content = str(prompt)
    return [{"role": "user", "content": content}]


def _completion_from_chat_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    choices = payload.get("choices") or []
    converted = []
    for index, choice in enumerate(choices):
        message = choice.get("message") if isinstance(choice, dict) else None
        converted.append({
            "text": message.get("content", "") if isinstance(message, dict) else "",
            "index": choice.get("index", index) if isinstance(choice, dict) else index,
            "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "logprobs": None,
        })
    return {
        "id": payload.get("id"),
        "object": "text_completion",
        "created": payload.get("created"),
        "model": payload.get("model"),
        "choices": converted,
        "usage": payload.get("usage"),
    }


@router.post("/v1/completions")
async def completions(
    request: CompletionRequest,
    _: str = Depends(require_api_key),
):
    t_start = time.monotonic()
    request_payload = request.model_dump(mode="python")
    if request_payload.get("stream"):
        raise HTTPException(status_code=400, detail="stream not supported for /v1/completions")

    config = get_runtime_store().load()
    requested_model = str(request.model).strip()
    messages = _extract_messages_from_prompt(request.prompt)
    request_id = f"completion-{uuid.uuid4().hex[:12]}"
    input_preview = str(request.prompt)[:300]

    # Routing via inference-service
    route_result = None
    selected_model = requested_model
    if requested_model == config["router_alias"]:
        inference_client = get_inference_client()
        route_result = await inference_client.classify(
            messages, request_id=request_id,
        )
        selected_model = route_result["selected_model"]
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
            messages_count=len(messages),
        )
    elif requested_model not in config["model_providers"]:
        raise HTTPException(status_code=404, detail=f"unsupported model: {requested_model}")

    # Upstream (async)
    target_info = resolve_model_provider_target(selected_model, config["model_providers"])
    forward_payload = dict(request_payload)
    forward_payload.pop("model", None)
    forward_payload.pop("prompt", None)
    forward_payload.pop("stream", None)
    forward_payload.pop("stream_options", None)

    t_upstream = time.monotonic()
    try:
        litellm_response = await litellm.acompletion(
            model=target_info["upstream_model"],
            messages=messages,
            api_key=target_info["api_key"],
            api_base=target_info["api_base"],
            base_url=target_info["api_base"],
            custom_llm_provider="openai",
            stream=False,
            timeout=45.0,
            **{k: v for k, v in forward_payload.items() if k not in ("model", "messages")},
        )
    except Exception as exc:
        upstream_latency_ms = (time.monotonic() - t_upstream) * 1000
        log_upstream_call(
            request_id=request_id,
            selected_model=selected_model,
            provider_slug=target_info["provider_slug"],
            upstream_model=target_info["upstream_model"],
            api_base=target_info["api_base"],
            status_code=502, ok=False,
            latency_ms=upstream_latency_ms,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail="upstream service error")
    upstream_latency_ms = (time.monotonic() - t_upstream) * 1000

    response_json = litellm_response.model_dump(exclude_none=True)
    completion_payload = _completion_from_chat_response(response_json)
    completion_payload["model"] = selected_model

    log_upstream_call(
        request_id=request_id,
        selected_model=selected_model,
        provider_slug=target_info["provider_slug"],
        upstream_model=target_info["upstream_model"],
        api_base=target_info["api_base"],
        status_code=200, ok=True,
        latency_ms=upstream_latency_ms,
    )

    return JSONResponse(
        content=completion_payload,
        headers={
            "X-Router-Selected-Model": selected_model,
            "X-Router-Provider": target_info["provider_slug"],
        },
    )
