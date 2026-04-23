"""POST /v1/completions — async legacy completions endpoint."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List

import litellm
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from router_service.dependencies import require_api_key
from router_service.logging import log_upstream_call
from router_service.schemas.requests import CompletionRequest
from router_service.services.routing import route_and_resolve, sanitize_error

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
    if request.stream:
        raise HTTPException(status_code=400, detail="stream not supported for /v1/completions")

    messages = _extract_messages_from_prompt(request.prompt)
    request_id = f"completion-{uuid.uuid4().hex[:12]}"
    input_preview = str(request.prompt)[:300]

    selected_model, target_info, route_result = await route_and_resolve(
        requested_model=str(request.model).strip(),
        messages=messages,
        request_id=request_id,
        input_preview=input_preview,
        messages_count=len(messages),
    )

    forward_payload = request.model_dump(
        mode="python",
        exclude={"model", "prompt", "stream", "stream_options", "suffix"},
        exclude_none=True,
    )

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
            **forward_payload,
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
            error=sanitize_error(exc),
        )
        raise HTTPException(status_code=502, detail="upstream service error") from exc
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
