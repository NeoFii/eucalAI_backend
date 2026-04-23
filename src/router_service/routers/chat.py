"""POST /v1/chat/completions — async gateway with inference-service routing."""

from __future__ import annotations

import json
import time
import uuid

import litellm
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from common.observability import get_request_id
from router_service.dependencies import extract_client_ip, get_settings, require_api_key
from router_service.gateway import ValidatedApiKey
from router_service.gateway_calllog import CallLogGateway
from router_service.logging import get_app_logger, log_upstream_call
from router_service.schemas.requests import ChatCompletionRequest
from router_service.services.routing import RoutingError, route_and_resolve, sanitize_error
from router_service.services.upstream import strip_think_tags
from router_service.utils.text import stringify_message_content

router = APIRouter()
logger = get_app_logger()


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
):
    is_stream = request.stream
    requested_model = str(request.model).strip()
    request_id = get_request_id() or uuid.uuid4().hex
    router_trace_id = f"chat-{uuid.uuid4().hex[:12]}"
    settings = get_settings()

    input_preview = ""
    if request.messages:
        for msg in reversed(request.messages):
            if str(msg.get("role", "")).lower() == "user":
                input_preview = stringify_message_content(msg.get("content", ""))
                break
        if not input_preview:
            input_preview = stringify_message_content(request.messages[-1].get("content", ""))

    t_start = time.monotonic()
    create_result = await CallLogGateway.create_call_log(
        settings=settings,
        request_id=request_id,
        user_id=principal.user_id,
        api_key_id=principal.id,
        model_name=requested_model,
        is_stream=is_stream,
        ip=extract_client_ip(raw_request),
        status=0,
    )
    call_log_created = create_result is not None

    try:
        selected_model, target_info, route_result, route_meta = await route_and_resolve(
            requested_model=requested_model,
            messages=request.messages,
            request_id=request_id,
            input_preview=input_preview,
            messages_count=len(request.messages),
            is_stream=is_stream,
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
        exclude={"model", "messages", "stream"},
        exclude_none=True,
    )

    t_upstream = time.monotonic()
    try:
        litellm_response = await litellm.acompletion(
            model=target_info["upstream_model"],
            messages=request.messages,
            api_key=target_info["api_key"],
            api_base=target_info["api_base"],
            base_url=target_info["api_base"],
            custom_llm_provider="openai",
            stream=is_stream,
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
            is_stream=is_stream,
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

    headers = {
        "X-Router-Selected-Model": selected_model,
        "X-Router-Provider": target_info["provider_slug"],
        "X-Router-Config-Version": str(config_version) if config_version is not None else "local",
        "X-Router-Config-Source": config_source,
    }

    if is_stream:
        async def _stream_sse():
            collected_content = ""
            stream_ok = False
            try:
                async for chunk in litellm_response:
                    chunk_dict = chunk.model_dump(exclude_none=True)
                    chunk_dict["model"] = selected_model
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
                stream_ok = True
            finally:
                final_latency = (time.monotonic() - t_upstream) * 1000
                log_upstream_call(
                    request_id=request_id,
                    selected_model=selected_model,
                    provider_slug=target_info["provider_slug"],
                    upstream_model=target_info["upstream_model"],
                    api_base=target_info["api_base"],
                    status_code=200 if stream_ok else 502,
                    ok=stream_ok,
                    latency_ms=final_latency,
                    is_stream=True,
                    response_preview=collected_content[:300],
                    config_version=config_version,
                    config_source=config_source,
                    router_trace_id=router_trace_id,
                )
                if call_log_created:
                    final_status = 1 if stream_ok else 4
                    await CallLogGateway.update_call_log(
                        settings=settings,
                        request_id=request_id,
                        status=final_status,
                        duration_ms=int((time.monotonic() - t_start) * 1000),
                        error_code="client_aborted" if not stream_ok else None,
                    )

        return StreamingResponse(
            _stream_sse(),
            media_type="text/event-stream",
            headers={**headers, "cache-control": "no-cache", "connection": "keep-alive"},
        )

    response_payload = litellm_response.model_dump(exclude_none=True)
    response_payload["model"] = selected_model

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
        upstream_model=target_info["upstream_model"],
        api_base=target_info["api_base"],
        status_code=200, ok=True,
        latency_ms=upstream_latency_ms,
        is_stream=False,
        response_preview=resp_preview,
        config_version=config_version,
        config_source=config_source,
        router_trace_id=router_trace_id,
    )

    if call_log_created:
        usage = response_payload.get("usage") or {}
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

    return JSONResponse(content=response_payload, headers=headers)
