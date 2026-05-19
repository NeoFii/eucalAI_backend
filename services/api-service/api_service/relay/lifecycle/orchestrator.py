"""CallLifecycle — request lifecycle orchestrator.

Orchestrates: init_log -> pre_consume -> route -> retry_upstream -> response.
Stream and finalize logic live in sibling modules.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from api_service.core.config import settings
from api_service.relay.auth import ValidatedApiKey
from api_service.relay.call_log_writer import create_call_log
from api_service.relay.dependencies import (
    get_affinity_store, get_channel_selector,
    get_routing_config_cache, get_inference_client, get_sdk_client_pool,
)
from api_service.relay.routing import RoutingError, route_and_resolve
from api_service.relay.upstream_dispatch import dispatch

logger = logging.getLogger(__name__)


class CallLifecycle:
    """Orchestrates the full relay request lifecycle."""

    def __init__(
        self,
        *,
        adapter: Any,
        principal: ValidatedApiKey,
        raw_request: Request,
        openai_messages: list[dict],
        forward_payload: dict[str, Any],
        is_stream: bool,
        requested_model: str,
        protocol_context: dict[str, Any],
    ) -> None:
        self.adapter = adapter
        self.principal = principal
        self.raw_request = raw_request
        self.openai_messages = openai_messages
        self.forward_payload = forward_payload
        self.is_stream = is_stream
        self.requested_model = requested_model
        self.ctx = protocol_context

        self.request_id = uuid.uuid4().hex
        self.t_start = time.monotonic()
        self.selected_model: str = ""
        self.target_info: dict[str, Any] = {}
        self.route_result: dict[str, Any] | None = None
        self.route_meta: dict[str, Any] = {}
        self.response: Any = None
        self.call_log_data: dict[str, Any] = {}
        self.pre_consumed: int = 0
        self.trusted: bool = False

    async def execute(self) -> JSONResponse | StreamingResponse:
        """Run the full lifecycle and return the HTTP response."""
        await self._init_call_log()

        if error := await self._check_balance():
            return error
        if error := await self._route():
            return error

        if self.is_stream:
            self.forward_payload.setdefault("stream_options", {"include_usage": True})

        if error := await self._call_upstream():
            return error

        if self.is_stream:
            return self._build_stream_response()
        return await self._build_non_stream_response()

    async def _init_call_log(self) -> None:
        from api_service.core.db import get_session_factory
        self.call_log_data = {
            "request_id": self.request_id,
            "user_id": self.principal.user_id,
            "api_key_id": self.principal.id,
            "model_name": self.requested_model,
            "is_stream": self.is_stream,
            "status": 0,
        }
        await create_call_log(get_session_factory(), self.call_log_data)

    async def _check_balance(self) -> JSONResponse | None:
        if self.principal.balance <= 0:
            return self.adapter.format_error(
                402, "insufficient balance", error_code="insufficient_balance"
            )
        return None

    async def _route(self) -> JSONResponse | None:
        config_cache = get_routing_config_cache()
        inference_client = get_inference_client()
        channel_selector = get_channel_selector()
        affinity_store = get_affinity_store()
        affinity_key = self.raw_request.headers.get("x-conversation-id")

        try:
            self.selected_model, self.target_info, self.route_result, self.route_meta = (
                await route_and_resolve(
                    requested_model=self.requested_model,
                    messages=self.openai_messages,
                    request_id=self.request_id,
                    config_cache=config_cache,
                    inference_client=inference_client,
                    channel_selector=channel_selector,
                    affinity_store=affinity_store,
                    affinity_key=affinity_key or None,
                    is_stream=self.is_stream,
                )
            )
        except RoutingError as exc:
            return self.adapter.format_error(
                exc.status_code, str(exc.detail), error_code=exc.error_code
            )
        return None

    async def _call_upstream(self) -> JSONResponse | None:
        max_retries = settings.CHANNEL_MAX_RETRIES if self.target_info.get("channel_slug") else 0
        timeout = self.adapter.get_timeout(self.is_stream)
        incoming_protocol = "anthropic" if self.adapter.protocol_name == "messages" else "openai"
        anthropic_request = self.ctx.get("anthropic_request")
        pool = get_sdk_client_pool()
        tried_slugs: set[str] = set()

        for attempt in range(max_retries + 1):
            try:
                self.response = await dispatch(
                    pool, self.target_info,
                    messages=self.openai_messages,
                    forward_payload=self.forward_payload,
                    stream=self.is_stream,
                    timeout=timeout,
                    incoming_protocol=incoming_protocol,
                    anthropic_request=anthropic_request,
                )
                channel_slug = self.target_info.get("channel_slug")
                if channel_slug:
                    get_channel_selector().report_success(channel_slug)
                break
            except Exception as exc:
                channel_slug = self.target_info.get("channel_slug")
                if channel_slug:
                    tried_slugs.add(channel_slug)
                    get_channel_selector().report_failure(channel_slug)
                if attempt >= max_retries:
                    logger.warning(
                        "upstream failed after %d retries: %s", attempt + 1, exc
                    )
                    return self.adapter.format_error(
                        502, "upstream service error", error_code="upstream_error"
                    )
                # Re-resolve excluding tried channels
                await self._re_resolve(tried_slugs)

        # Detect native Anthropic pass-through
        if self.adapter.protocol_name == "messages":
            is_native = self.target_info.get("provider_slug") in settings.ANTHROPIC_NATIVE_SLUGS
            self.ctx["is_native_passthrough"] = is_native

        return None

    async def _re_resolve(self, tried_slugs: set[str]) -> None:
        config_cache = get_routing_config_cache()
        channel_selector = get_channel_selector()
        from api_service.relay.upstream import resolve_model_channel_target

        config = config_cache.load()
        if "model_channels" in config and config["model_channels"]:
            self.target_info = resolve_model_channel_target(
                self.selected_model,
                config["model_channels"],
                channel_selector,
                excluded_slugs=frozenset(tried_slugs),
            )

    def _build_stream_response(self) -> StreamingResponse:
        from api_service.relay.lifecycle.stream import stream_events, stream_native_anthropic
        headers = {"cache-control": "no-cache", "connection": "keep-alive"}
        if self.ctx.get("is_native_passthrough"):
            return StreamingResponse(
                stream_native_anthropic(self),
                media_type="text/event-stream",
                headers=headers,
            )
        converter = self.adapter.create_stream_converter(self.selected_model, self.ctx)
        return StreamingResponse(
            stream_events(self, converter),
            media_type="text/event-stream",
            headers=headers,
        )

    async def _build_non_stream_response(self) -> JSONResponse:
        response_payload = self.response.model_dump(exclude_none=True)
        return self.adapter.format_non_stream_response(
            response_payload, self.selected_model, self.ctx
        )

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self.t_start) * 1000)
