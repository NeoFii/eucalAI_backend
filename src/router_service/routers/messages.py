"""POST /v1/messages — Anthropic Messages API compatible endpoint."""

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
from router_service.schemas.anthropic import AnthropicMessagesRequest
from router_service.services.anthropic_convert import (
    AnthropicStreamState,
    anthropic_error_response,
    anthropic_to_openai,
    convert_chunk,
    init_anthropic_stream,
    openai_response_to_anthropic,
)
from router_service.services.routing import RoutingError, route_and_resolve, sanitize_error
from router_service.services.upstream import strip_think_tags
from router_service.utils.text import stringify_message_content

router = APIRouter()
logger = get_app_logger()


@router.post("/v1/messages")
async def anthropic_messages(
    request: AnthropicMessagesRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
):
    is_stream = request.stream
    requested_model = str(request.model).strip()
    request_id = get_request_id() or uuid.uuid4().hex
    router_trace_id = f"msg-{uuid.uuid4().hex[:12]}"
    settings = get_settings()

    # --- Convert Anthropic request to OpenAI format ---
    try:
        openai_messages, extra_kwargs = anthropic_to_openai(
            model=request.model,
            messages=request.messages,
            system=request.system,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            stop_sequences=request.stop_sequences,
            tools=request.tools,
            tool_choice=request.tool_choice,
        )
    except Exception as exc:
        body, status = anthropic_error_response(400, f"request conversion failed: {exc}")
        raise HTTPException(status_code=status, detail=body) from exc

    input_preview = ""
    if openai_messages:
        for msg in reversed(openai_messages):
            if str(msg.get("role", "")).lower() == "user":
                input_preview = stringify_message_content(msg.get("content", ""))
                break
        if not input_preview:
            input_preview = stringify_message_content(
                openai_messages[-1].get("content", "")
            )

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
            messages=openai_messages,
            request_id=request_id,
            input_preview=input_preview,
            messages_count=len(openai_messages),
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
        body, status = anthropic_error_response(exc.status_code, str(exc.detail))
        raise HTTPException(status_code=status, detail=body) from exc

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

    t_upstream = time.monotonic()
    try:
        litellm_response = await litellm.acompletion(
            model=target_info["upstream_model"],
            messages=openai_messages,
            api_key=target_info["api_key"],
            api_base=target_info["api_base"],
            base_url=target_info["api_base"],
            custom_llm_provider="openai",
            stream=is_stream,
            timeout=45.0,
            **extra_kwargs,
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
        body, status = anthropic_error_response(502, "upstream service error")
        raise HTTPException(status_code=status, detail=body) from exc
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
            state = AnthropicStreamState(model=selected_model)

            try:
                yield init_anthropic_stream(state)

                async for chunk in litellm_response:
                    chunk_dict = chunk.model_dump(exclude_none=True)
                    events = convert_chunk(state, chunk_dict)
                    for event in events:
                        yield event
                        # Collect text content for logging
                        if "text_delta" in event:
                            try:
                                data_start = event.index('"text":') + len('"text":')
                                remaining = event[data_start:]
                                text_val = json.loads(
                                    "{" + remaining.split("}", 1)[0] + "}"
                                ).get("text", "")
                                collected_content += text_val
                            except (json.JSONDecodeError, ValueError):
                                pass

                # If stream ended without finish_reason (edge case), finalize
                if state.content_block_open:
                    yield state._sse_event("content_block_stop", {
                        "type": "content_block_stop",
                        "index": state.content_block_index,
                    })
                    state.content_block_open = False
                    yield state._sse_event("message_delta", {
                        "type": "message_delta",
                        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                        "usage": {"output_tokens": max(state.total_output_tokens, 1)},
                    })
                    yield state._sse_event("message_stop", {"type": "message_stop"})

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

    # --- Non-streaming ---
    response_payload = litellm_response.model_dump(exclude_none=True)

    # Strip think tags from content
    choices = response_payload.get("choices") or []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and "bstract" in content:
                message["content"] = strip_think_tags(content)

    anthropic_response = openai_response_to_anthropic(response_payload, selected_model)

    resp_preview = ""
    try:
        content_blocks = anthropic_response.get("content") or []
        for block in content_blocks:
            if block.get("type") == "text":
                resp_preview = block.get("text", "")[:300]
                break
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
        openai_usage = response_payload.get("usage") or {}
        await CallLogGateway.update_call_log(
            settings=settings,
            request_id=request_id,
            status=1,
            prompt_tokens=openai_usage.get("prompt_tokens", 0),
            completion_tokens=openai_usage.get("completion_tokens", 0),
            cached_tokens=openai_usage.get("cached_tokens", 0),
            total_tokens=openai_usage.get("total_tokens", 0),
            duration_ms=int((time.monotonic() - t_start) * 1000),
        )

    return JSONResponse(content=anthropic_response, headers=headers)
