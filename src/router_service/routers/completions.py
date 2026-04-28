"""POST /v1/completions — async legacy completions endpoint."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List

import litellm
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from common.observability import get_request_id
from router_service.dependencies import extract_client_ip, get_channel_selector, get_config_manager, get_settings, require_api_key
from router_service.gateway import ValidatedApiKey
from router_service.gateway_calllog import CallLogGateway
from router_service.logging import log_upstream_call
from router_service.schemas.requests import CompletionRequest
from router_service.services.routing import RoutingError, route_and_resolve, sanitize_error

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
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
):
    if request.stream:
        raise HTTPException(status_code=400, detail="stream not supported for /v1/completions")

    requested_model = str(request.model).strip()
    messages = _extract_messages_from_prompt(request.prompt)
    request_id = get_request_id() or uuid.uuid4().hex
    router_trace_id = f"completion-{uuid.uuid4().hex[:12]}"
    input_preview = str(request.prompt)[:300]
    settings = get_settings()

    t_start = time.monotonic()
    create_result = await CallLogGateway.create_call_log(
        settings=settings,
        request_id=request_id,
        user_id=principal.user_id,
        api_key_id=principal.id,
        model_name=requested_model,
        is_stream=False,
        ip=extract_client_ip(raw_request),
        status=0,
    )
    call_log_created = create_result is not None

    try:
        selected_model, target_info, route_result, route_meta = await route_and_resolve(
            requested_model=requested_model,
            messages=messages,
            request_id=request_id,
            input_preview=input_preview,
            messages_count=len(messages),
        )
    except RoutingError as exc:
        if call_log_created:
            await CallLogGateway.update_call_log(
                settings=settings,
                request_id=request_id,
                status=2,
                error_code=exc.error_code,
                error_msg=str(exc.detail)[:512],
                duration_ms=int((time.monotonic() - t_start) * 1000),
            )
        raise

    config_version = route_meta.get("config_version")
    config_source = route_meta.get("config_source", "")

    if call_log_created:
        await CallLogGateway.update_call_log(
            settings=settings,
            request_id=request_id,
            selected_model=selected_model,
            provider_slug=target_info["provider_slug"],
            upstream_model=target_info["upstream_model"],
            config_version=config_version,
            config_source=config_source,
            inference_config_version=route_meta.get("inference_config_version"),
            inference_config_source=route_meta.get("inference_config_source"),
            routing_tier=(route_result or {}).get("routing_tier"),
            score_source=(route_result or {}).get("score_source"),
            router_trace_id=router_trace_id,
            inference_error_code=route_meta.get("error_code"),
        )

    forward_payload = request.model_dump(
        mode="python",
        exclude={"model", "prompt", "stream", "stream_options", "suffix"},
        exclude_none=True,
    )

    t_upstream = time.monotonic()
    channel_slug = target_info.get("channel_slug")
    max_channel_retries = settings.channel_max_retries if channel_slug else 0
    tried_slugs: set[str] = set()

    for _attempt in range(max_channel_retries + 1):
        if channel_slug:
            tried_slugs.add(channel_slug)
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
            if channel_slug:
                get_channel_selector().report_success(channel_slug)
            break
        except Exception as exc:
            from router_service.services.retry_policy import extract_status_code, should_retry

            status_code = extract_status_code(exc)
            if channel_slug:
                get_channel_selector().report_failure(channel_slug)
            if _attempt < max_channel_retries and should_retry(exc, status_code):
                from router_service.services.routing import _resolve_target
                config = get_config_manager().load()
                try:
                    target_info = _resolve_target(
                        selected_model, config,
                        excluded_slugs=frozenset(tried_slugs),
                        retry_tier=_attempt + 1,
                    )
                    channel_slug = target_info.get("channel_slug")
                    t_upstream = time.monotonic()
                    continue
                except Exception:
                    pass
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
                config_version=config_version,
                config_source=config_source,
                router_trace_id=router_trace_id,
            )
            if call_log_created:
                await CallLogGateway.update_call_log(
                    settings=settings,
                    request_id=request_id,
                    status=2,
                    error_code="upstream_error",
                    error_msg=sanitize_error(exc)[:512],
                    duration_ms=int((time.monotonic() - t_start) * 1000),
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
        config_version=config_version,
        config_source=config_source,
        router_trace_id=router_trace_id,
    )

    if call_log_created:
        usage = response_json.get("usage") or {}
        await CallLogGateway.update_call_log(
            settings=settings,
            request_id=request_id,
            status=1,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            duration_ms=int((time.monotonic() - t_start) * 1000),
        )

    return JSONResponse(
        content=completion_payload,
        headers={
            "X-Router-Selected-Model": selected_model,
            "X-Router-Provider": target_info["provider_slug"],
            "X-Router-Config-Version": str(config_version) if config_version is not None else "local",
            "X-Router-Config-Source": config_source,
        },
    )
