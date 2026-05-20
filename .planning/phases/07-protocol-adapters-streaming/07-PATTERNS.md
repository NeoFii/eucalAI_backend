# Phase 7: Protocol Adapters & Streaming - Pattern Map

**Mapped:** 2026-05-19
**Files analyzed:** 22 new files
**Analogs found:** 22 / 22

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `relay/lifecycle/orchestrator.py` | service | request-response | `router-service/src/services/call_lifecycle.py` | exact |
| `relay/lifecycle/stream.py` | service | streaming | `router-service/src/services/call_lifecycle.py` (lines 288-395) | exact |
| `relay/lifecycle/finalize.py` | service | request-response | `router-service/src/services/call_lifecycle.py` (lines 472-596) | exact |
| `relay/sdk_clients.py` | utility | request-response | `router-service/src/services/sdk_clients.py` | exact (原样移植) |
| `relay/rate_limiter.py` | middleware | request-response | `router-service/src/services/rate_limiter.py` | role-match |
| `relay/retry_policy.py` | utility | request-response | `router-service/src/services/retry_policy.py` | exact (原样移植) |
| `relay/upstream_dispatch.py` | service | request-response | `router-service/src/services/upstream_dispatch.py` | exact |
| `relay/upstream_caller.py` | service | request-response | `router-service/src/services/upstream_caller.py` | exact |
| `relay/backends/openai_backend.py` | service | streaming | `router-service/src/services/openai_backend.py` | exact |
| `relay/backends/anthropic_backend.py` | service | streaming | `router-service/src/services/anthropic_backend.py` | exact |
| `relay/adapters/protocol.py` | utility | request-response | `router-service/src/services/protocol_adapter.py` | exact (原样移植) |
| `relay/adapters/openai_chat.py` | service | request-response | `router-service/src/services/adapters/openai_chat.py` | exact |
| `relay/adapters/anthropic_messages.py` | service | request-response | `router-service/src/services/adapters/anthropic_messages.py` | exact |
| `relay/adapters/openai_responses.py` | service | request-response | `router-service/src/services/adapters/openai_responses.py` | exact |
| `relay/adapters/anthropic_convert.py` | utility | transform | `router-service/src/services/anthropic_convert.py` | exact |
| `relay/adapters/responses_convert.py` | utility | transform | `router-service/src/services/responses_convert.py` | exact |
| `relay/lua/token_bucket.lua` | config | request-response | `router-service/src/services/lua/token_bucket.lua` | exact (原样移植) |
| `relay/schemas/chat.py` | model | request-response | `router-service/src/schemas/requests.py` | exact |
| `relay/schemas/anthropic.py` | model | request-response | `router-service/src/schemas/anthropic.py` | exact |
| `relay/schemas/responses.py` | model | request-response | `router-service/src/schemas/responses.py` | exact |
| `controllers/relay/chat.py` | controller | request-response | `router-service/src/controllers/chat.py` | exact |
| `controllers/relay/anthropic.py` | controller | request-response | `router-service/src/controllers/messages.py` | exact |
| `controllers/relay/responses.py` | controller | request-response | `router-service/src/controllers/responses.py` | exact |
| `controllers/relay/models.py` | controller | request-response | `router-service/src/controllers/messages.py` (lines 17-39) | role-match |

## Pattern Assignments

### `relay/lifecycle/orchestrator.py` (service, request-response)

**Analog:** `services/router-service/src/services/call_lifecycle.py`

**Imports pattern** (lines 1-32):
```python
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from api_service.relay.auth import ValidatedApiKey
from api_service.relay.dependencies import get_routing_config_cache, get_channel_selector
from api_service.relay.routing import route_and_resolve
from api_service.relay.retry_policy import should_retry, extract_status_code
from api_service.relay.upstream_dispatch import dispatch
from api_service.relay.dependencies import get_sdk_client_pool
from api_service.core.config import settings
```

**Core pattern — CallLifecycle class** (lines 35-93):
```python
class CallLifecycle:
    """Orchestrates the request lifecycle shared by all protocols."""

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
        # ... init fields ...

    async def execute(self) -> JSONResponse | StreamingResponse:
        """Run full lifecycle with retry at this level (D-03)."""
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
```

**Retry loop pattern** (adapted from upstream_caller.py lines 47-98, lifted to lifecycle per D-03):
```python
# Inside _call_upstream():
max_retries = settings.CHANNEL_MAX_RETRIES if self.target_info.get("channel_slug") else 0
tried_slugs: set[str] = set()
for attempt in range(max_retries + 1):
    channel_slug = self.target_info.get("channel_slug")
    if channel_slug:
        tried_slugs.add(channel_slug)
    try:
        pool = get_sdk_client_pool()
        self.response = await dispatch(
            pool, self.target_info,
            messages=self.openai_messages,
            forward_payload=self.forward_payload,
            stream=self.is_stream,
            timeout=timeout,
            incoming_protocol=incoming_protocol,
            anthropic_request=anthropic_request,
        )
        if channel_slug:
            get_channel_selector().report_success(channel_slug)
        break
    except Exception as exc:
        if channel_slug:
            get_channel_selector().report_failure(channel_slug)
        if attempt < max_retries and should_retry(exc):
            self.target_info = await self._re_resolve(tried_slugs)
            continue
        return self._handle_upstream_error(exc)
```

---

### `relay/lifecycle/stream.py` (service, streaming)

**Analog:** `services/router-service/src/services/call_lifecycle.py` lines 288-395

**Core pattern — stream_events function** (lines 288-340):
```python
async def stream_events(
    lifecycle: "CallLifecycle", converter: Any
) -> AsyncIterator[str]:
    """Standard path: iterate SDK chunks, convert via StreamConverter."""
    collected_content = ""
    stream_usage: dict = {}
    stream_ok = False
    abort_reason: str | None = None
    stream_exc: BaseException | None = None
    t_stream_start = time.monotonic()
    try:
        async for chunk in lifecycle.response:
            chunk_dict = chunk.model_dump(exclude_none=True)
            chunk_dict["model"] = lifecycle.selected_model
            # Extract usage
            chunk_usage = chunk_dict.get("usage")
            if chunk_usage:
                stream_usage = chunk_usage
            # Collect content
            choices = chunk_dict.get("choices") or []
            for c in choices:
                delta = c.get("delta") or {}
                dc = delta.get("content")
                if isinstance(dc, str):
                    collected_content += dc
            # Emit SSE
            if converter:
                sse = converter.convert_chunk(chunk_dict)
                if sse:
                    yield sse
            else:
                yield f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"
        # Final event
        if converter:
            final = converter.get_final_event()
            if final:
                yield final
        else:
            yield "data: [DONE]\n\n"
        stream_ok = True
    except (asyncio.CancelledError, GeneratorExit):
        abort_reason = "client_cancelled"
        raise
    except Exception as exc:
        abort_reason = "stream_error"
        stream_exc = exc
    finally:
        await finalize_stream(lifecycle, collected_content, stream_usage, stream_ok, ...)
```

**Native Anthropic pass-through** (lines 342-388):
```python
async def stream_native_anthropic(lifecycle: "CallLifecycle") -> AsyncIterator[str]:
    """Stream raw Anthropic SDK events for native pass-through."""
    collected_content = ""
    input_tokens = 0
    output_tokens = 0
    # ... same try/except/finally pattern ...
    try:
        async for event in lifecycle.response:
            event_type = event.type
            event_dict = event.model_dump(exclude_none=True)
            if event_type == "message_start":
                msg = event_dict.get("message", {})
                msg["model"] = lifecycle.selected_model
            yield f"event: {event_type}\ndata: {json.dumps(event_dict, ensure_ascii=False)}\n\n"
        stream_ok = True
    except (asyncio.CancelledError, GeneratorExit):
        abort_reason = "client_cancelled"
        raise
    # ...
```

---

### `relay/lifecycle/finalize.py` (service, request-response)

**Analog:** `services/router-service/src/services/call_lifecycle.py` lines 472-596

**Core pattern — finalize_stream function**:
```python
async def finalize_stream(
    lifecycle: "CallLifecycle",
    collected_content: str,
    stream_usage: dict,
    stream_ok: bool,
    abort_reason: str | None,
    stream_exc: BaseException | None,
    t_stream_start: float,
) -> None:
    """Compute cost, settle billing, update call_log after stream ends."""
    final_status = 200 if stream_ok else (502 if abort_reason == "stream_error" else 499)
    # ... compute cost from stream_usage ...
    # ... update call_log ...
    # Shield finalize on client cancel (D-12):
    if abort_reason == "client_cancelled":
        update_task = asyncio.ensure_future(update_coro)
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.shield(update_task)
    else:
        await update_coro
```

---

### `relay/sdk_clients.py` (utility, request-response)

**Analog:** `services/router-service/src/services/sdk_clients.py` — 原样移植

**Complete pattern** (lines 1-53):
```python
"""SDK client pool: reusable AsyncOpenAI and AsyncAnthropic instances."""
from __future__ import annotations

import threading
from collections import OrderedDict

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI


class SdkClientPool:
    """LRU-bounded pool of SDK client instances keyed by (base_url, api_key)."""

    def __init__(self, max_size: int = 64) -> None:
        self._max_size = max_size
        self._openai_clients: OrderedDict[tuple[str, str], AsyncOpenAI] = OrderedDict()
        self._anthropic_clients: OrderedDict[tuple[str, str], AsyncAnthropic] = OrderedDict()
        self._lock = threading.Lock()

    def get_openai(self, base_url: str, api_key: str) -> AsyncOpenAI:
        key = (base_url, api_key)
        with self._lock:
            if key in self._openai_clients:
                self._openai_clients.move_to_end(key)
                return self._openai_clients[key]
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            self._openai_clients[key] = client
            if len(self._openai_clients) > self._max_size:
                self._openai_clients.popitem(last=False)
            return client

    def get_anthropic(self, base_url: str, api_key: str) -> AsyncAnthropic:
        key = (base_url, api_key)
        with self._lock:
            if key in self._anthropic_clients:
                self._anthropic_clients.move_to_end(key)
                return self._anthropic_clients[key]
            client = AsyncAnthropic(base_url=base_url, api_key=api_key)
            self._anthropic_clients[key] = client
            if len(self._anthropic_clients) > self._max_size:
                self._anthropic_clients.popitem(last=False)
            return client

    async def close_all(self) -> None:
        with self._lock:
            for client in self._openai_clients.values():
                await client.close()
            self._openai_clients.clear()
            for client in self._anthropic_clients.values():
                await client.close()
            self._anthropic_clients.clear()
```

---

### `relay/rate_limiter.py` (middleware, request-response)

**Analog:** `services/router-service/src/services/rate_limiter.py` (adapted per D-13: unified token bucket)

**Imports pattern** (lines 1-12):
```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

import cachetools
from fastapi import Depends

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from api_service.core.config import settings
from api_service.relay.auth import ValidatedApiKey, require_api_key
```

**Core pattern — RateLimiter class** (adapted from lines 46-134):
```python
class RateLimiter:
    def __init__(self, *, redis: "aioredis.Redis | None", settings: Any) -> None:
        self._redis = redis
        self._settings = settings
        self._fallback = InMemoryRateLimiter()
        self._token_bucket_script = None
        if redis is not None:
            lua_path = Path(__file__).parent / "lua" / "token_bucket.lua"
            self._token_bucket_script = redis.register_script(lua_path.read_text())

    async def check_all(self, *, user_id: int, key_rpm: int | None, user_rpm: int | None) -> None:
        """Check global -> per-user -> per-key (D-14). Raises RateLimitExceeded."""
        # 1. Global
        global_rpm = self._settings.RATE_LIMIT_GLOBAL_RPM
        if global_rpm > 0:
            if not await self._check("rl:global", global_rpm):
                raise RateLimitExceeded("Global rate limit exceeded", retry_after=2)
        # 2. Per-user
        effective_user_rpm = user_rpm or self._settings.RATE_LIMIT_DEFAULT_USER_RPM
        if effective_user_rpm > 0:
            if not await self._check(f"rl:user:{user_id}", effective_user_rpm):
                raise RateLimitExceeded(f"Rate limit exceeded: {effective_user_rpm} RPM", ...)
        # 3. Per-key
        if key_rpm and key_rpm > 0:
            if not await self._check(f"rl:key:{user_id}", key_rpm):
                raise RateLimitExceeded(f"API key rate limit exceeded: {key_rpm} RPM", ...)

    async def _check(self, key: str, capacity: int) -> bool:
        rate = capacity / 60.0
        if self._redis and self._token_bucket_script:
            try:
                result = await self._token_bucket_script(
                    keys=[key], args=[str(int(capacity)), str(rate), "1"]
                )
                return int(result) == 1
            except Exception:
                pass
        return self._fallback.check(key, capacity)
```

**Depends injection pattern** (D-17):
```python
async def require_rate_limit(
    principal: ValidatedApiKey = Depends(require_api_key),
) -> None:
    """Rate limit dependency — runs after auth, before CallLifecycle."""
    if not settings.RATE_LIMIT_ENABLED:
        return
    limiter = get_rate_limiter()
    await limiter.check_all(
        user_id=principal.user_id,
        key_rpm=principal.user_rpm_limit,
        user_rpm=None,
    )
```

---

### `relay/retry_policy.py` (utility, request-response)

**Analog:** `services/router-service/src/services/retry_policy.py` — 原样移植

**Complete pattern** (lines 1-29):
```python
"""Retry decision logic for upstream channel errors."""
from __future__ import annotations

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503})
NEVER_RETRY_STATUS_CODES: frozenset[int] = frozenset({400, 401, 403, 404})


def extract_status_code(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    return None


def should_retry(exc: Exception, status_code: int | None = None) -> bool:
    if status_code is None:
        status_code = extract_status_code(exc)
    if status_code is None:
        return True
    if status_code in NEVER_RETRY_STATUS_CODES:
        return False
    if status_code in RETRYABLE_STATUS_CODES:
        return True
    if 500 <= status_code < 600:
        return True
    return False
```

---

### `relay/upstream_dispatch.py` (service, request-response)

**Analog:** `services/router-service/src/services/upstream_dispatch.py`

**Complete pattern** (lines 1-47):
```python
"""SDK dispatch: routes upstream calls to the correct SDK backend."""
from __future__ import annotations

from typing import Any

from api_service.core.config import settings
from api_service.relay.backends.anthropic_backend import call_anthropic_from_openai, call_anthropic_native
from api_service.relay.adapters.anthropic_convert import build_anthropic_native_params
from api_service.relay.backends.openai_backend import call_openai
from api_service.relay.sdk_clients import SdkClientPool


async def dispatch(
    pool: SdkClientPool,
    target_info: dict[str, Any],
    *,
    messages: list[dict[str, Any]],
    forward_payload: dict[str, Any],
    stream: bool,
    timeout: float,
    incoming_protocol: str,
    anthropic_request: Any | None = None,
) -> Any:
    provider_slug = target_info.get("provider_slug", "")
    is_anthropic_upstream = provider_slug in settings.ANTHROPIC_NATIVE_SLUGS

    if is_anthropic_upstream:
        if incoming_protocol == "anthropic" and anthropic_request is not None:
            anthropic_params = build_anthropic_native_params(anthropic_request)
            return await call_anthropic_native(
                pool, target_info, anthropic_params, stream=stream, timeout=timeout,
            )
        return await call_anthropic_from_openai(
            pool, target_info, messages, forward_payload, stream=stream, timeout=timeout,
        )

    return await call_openai(
        pool, target_info, messages, forward_payload, stream=stream, timeout=timeout,
    )
```

---

### `relay/backends/openai_backend.py` (service, streaming)

**Analog:** `services/router-service/src/services/openai_backend.py`

**Complete pattern** (lines 1-72):
```python
"""OpenAI SDK backend: direct calls to OpenAI-compatible upstreams."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from api_service.relay.sdk_clients import SdkClientPool


@dataclass
class OpenAIResponse:
    _data: dict[str, Any] = field(repr=False)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        if not exclude_none:
            return self._data
        return {k: v for k, v in self._data.items() if v is not None}


@dataclass
class OpenAIStreamChunk:
    _data: dict[str, Any] = field(repr=False)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        if not exclude_none:
            return self._data
        return {k: v for k, v in self._data.items() if v is not None}


async def call_openai(
    pool: SdkClientPool,
    target_info: dict[str, Any],
    messages: list[dict[str, Any]],
    forward_payload: dict[str, Any],
    *,
    stream: bool,
    timeout: float = 45.0,
) -> OpenAIResponse | AsyncIterator[OpenAIStreamChunk]:
    client: AsyncOpenAI = pool.get_openai(target_info["api_base"], target_info["api_key"])
    kwargs: dict[str, Any] = {
        "model": target_info["upstream_model"],
        "messages": messages,
        "stream": stream,
        "timeout": timeout,
        **forward_payload,
    }
    if stream:
        raw_stream = await client.chat.completions.create(**kwargs)
        return _stream_iter(raw_stream)
    response = await client.chat.completions.create(**kwargs)
    return OpenAIResponse(_data=response.model_dump(exclude_none=True))
```

---

### `relay/backends/anthropic_backend.py` (service, streaming)

**Analog:** `services/router-service/src/services/anthropic_backend.py`

**Imports pattern** (lines 1-12):
```python
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from api_service.relay.sdk_clients import SdkClientPool
```

**Response wrapper pattern** (lines 19-53):
```python
@dataclass
class AnthropicAsOpenAIResponse:
    """Anthropic response normalized to OpenAI chat completion dict shape."""
    _data: dict[str, Any] = field(repr=False)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        if not exclude_none:
            return self._data
        return {k: v for k, v in self._data.items() if v is not None}


@dataclass
class AnthropicNativeResponse:
    """Raw Anthropic response for pass-through path."""
    _data: dict[str, Any] = field(repr=False)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        if not exclude_none:
            return self._data
        return {k: v for k, v in self._data.items() if v is not None}
```

**Dual-path call pattern** (lines 71-133):
```python
async def call_anthropic_native(
    pool: SdkClientPool, target_info: dict[str, Any],
    anthropic_params: dict[str, Any], *, stream: bool, timeout: float = 45.0,
) -> AnthropicNativeResponse | AsyncIterator[Any]:
    client: AsyncAnthropic = pool.get_anthropic(target_info["api_base"], target_info["api_key"])
    kwargs = {"model": target_info["upstream_model"], "stream": stream, "timeout": timeout, **anthropic_params}
    if stream:
        return await client.messages.create(**kwargs)
    response = await client.messages.create(**kwargs)
    return AnthropicNativeResponse(_data=response.model_dump(exclude_none=True))


async def call_anthropic_from_openai(
    pool: SdkClientPool, target_info: dict[str, Any],
    messages: list[dict[str, Any]], forward_payload: dict[str, Any],
    *, stream: bool, timeout: float = 45.0,
) -> AnthropicAsOpenAIResponse | AsyncIterator[Any]:
    client: AsyncAnthropic = pool.get_anthropic(target_info["api_base"], target_info["api_key"])
    anthropic_params = _openai_to_anthropic_params(messages, forward_payload)
    kwargs = {"model": target_info["upstream_model"], "stream": stream, "timeout": timeout, **anthropic_params}
    if stream:
        raw_stream = await client.messages.create(**kwargs)
        return _normalize_stream(raw_stream)
    response = await client.messages.create(**kwargs)
    return AnthropicAsOpenAIResponse(_data=_anthropic_resp_to_openai(response.model_dump(exclude_none=True)))
```

---

### `relay/adapters/protocol.py` (utility, request-response)

**Analog:** `services/router-service/src/services/protocol_adapter.py` — 原样移植

**Complete pattern** (lines 1-56):
```python
"""Protocol definitions for multi-protocol adapter pattern."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fastapi.responses import JSONResponse


@runtime_checkable
class StreamConverter(Protocol):
    def convert_chunk(self, chunk_dict: dict[str, Any]) -> str | None: ...
    def get_final_event(self) -> str | None: ...


@runtime_checkable
class ProtocolAdapter(Protocol):
    @property
    def protocol_name(self) -> str: ...
    def parse_request(self, request: Any) -> tuple[list[dict], dict[str, Any], dict[str, Any]]: ...
    def format_error(self, status_code: int, message: str, *, error_code: str | None = None) -> JSONResponse: ...
    def format_non_stream_response(self, openai_response: dict[str, Any], selected_model: str, ctx: dict[str, Any]) -> JSONResponse: ...
    def create_stream_converter(self, selected_model: str, ctx: dict[str, Any]) -> StreamConverter | None: ...
    def get_timeout(self, is_stream: bool) -> float: ...
```

---

### `relay/adapters/openai_chat.py` (service, request-response)

**Analog:** `services/router-service/src/services/adapters/openai_chat.py`

**Core pattern** (lines 1-71):
```python
"""OpenAI Chat Completions protocol adapter."""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


class OpenAIChatAdapter:
    @property
    def protocol_name(self) -> str:
        return "chat"

    def parse_request(self, request: Any) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
        messages = list(request.messages or [])
        forward_payload = request.model_dump(
            mode="python", exclude={"model", "messages", "stream"}, exclude_none=True,
        )
        ctx: dict[str, Any] = {"raw_messages": messages}
        return messages, forward_payload, ctx

    def format_error(self, status_code: int, message: str, *, error_code: str | None = None) -> JSONResponse:
        error_type = {401: "invalid_request_error", 402: "invalid_request_error",
                      403: "invalid_request_error", 429: "rate_limit_error"}.get(status_code, "server_error")
        return JSONResponse(
            status_code=status_code,
            content={"error": {"message": message, "type": error_type, "param": None, "code": error_code}},
        )

    def create_stream_converter(self, selected_model: str, ctx: dict[str, Any]) -> None:
        return None  # OpenAI native — no conversion needed

    def get_timeout(self, is_stream: bool) -> float:
        return 45.0
```

---

### `relay/adapters/anthropic_messages.py` (service, request-response)

**Analog:** `services/router-service/src/services/adapters/anthropic_messages.py`

**Core pattern** (lines 1-74):
```python
"""Anthropic Messages protocol adapter."""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from api_service.relay.adapters.anthropic_convert import (
    AnthropicStreamConverter, anthropic_to_openai_request, openai_to_anthropic_response,
)


class AnthropicMessagesAdapter:
    @property
    def protocol_name(self) -> str:
        return "messages"

    def parse_request(self, request: Any) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
        openai_messages, forward_payload = anthropic_to_openai_request(request)
        ctx: dict[str, Any] = {"anthropic_request": request}
        return openai_messages, forward_payload, ctx

    def format_error(self, status_code: int, message: str, *, error_code: str | None = None) -> JSONResponse:
        error_type = {429: "rate_limit_error", 500: "api_error", 502: "api_error",
                      503: "overloaded_error"}.get(status_code, "invalid_request_error")
        return JSONResponse(
            status_code=status_code,
            content={"type": "error", "error": {"type": error_type, "message": message}},
        )

    def format_non_stream_response(
        self, openai_response: dict[str, Any], selected_model: str, ctx: dict[str, Any],
    ) -> JSONResponse:
        is_native = ctx.get("is_native_passthrough", False)
        if is_native:
            openai_response["model"] = selected_model
            return JSONResponse(content=openai_response)
        openai_response["model"] = selected_model
        anthropic_response = openai_to_anthropic_response(openai_response, selected_model)
        return JSONResponse(content=anthropic_response)

    def create_stream_converter(self, selected_model: str, ctx: dict[str, Any]) -> Any:
        if ctx.get("is_native_passthrough"):
            return None
        return _AnthropicStreamConverterWrapper(AnthropicStreamConverter(selected_model))
```

---

### `controllers/relay/chat.py` (controller, request-response)

**Analog:** `services/router-service/src/controllers/chat.py`

**Complete pattern** (lines 1-36):
```python
"""POST /v1/chat/completions — OpenAI Chat Completions protocol."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api_service.relay.auth import ValidatedApiKey, require_api_key
from api_service.relay.rate_limiter import require_rate_limit
from api_service.relay.schemas.chat import ChatCompletionRequest
from api_service.relay.adapters.openai_chat import OpenAIChatAdapter
from api_service.relay.lifecycle.orchestrator import CallLifecycle

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
```

---

### `controllers/relay/anthropic.py` (controller, request-response)

**Analog:** `services/router-service/src/controllers/messages.py`

**Complete pattern** (lines 42-63):
```python
"""POST /v1/anthropic/messages — Anthropic Messages API compatible endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api_service.relay.auth import ValidatedApiKey, require_api_key
from api_service.relay.rate_limiter import require_rate_limit
from api_service.relay.schemas.anthropic import AnthropicMessagesRequest
from api_service.relay.adapters.anthropic_messages import AnthropicMessagesAdapter
from api_service.relay.lifecycle.orchestrator import CallLifecycle

router = APIRouter()


@router.post("/v1/anthropic/v1/messages")
@router.post("/v1/anthropic/messages")
async def messages(
    request: AnthropicMessagesRequest,
    raw_request: Request,
    principal: ValidatedApiKey = Depends(require_api_key),
    _rate_limit: None = Depends(require_rate_limit),
):
    adapter = AnthropicMessagesAdapter()
    openai_messages, payload, ctx = adapter.parse_request(request)
    lifecycle = CallLifecycle(
        adapter=adapter, principal=principal, raw_request=raw_request,
        openai_messages=openai_messages, forward_payload=payload,
        is_stream=request.stream, requested_model=str(request.model).strip(),
        protocol_context=ctx,
    )
    return await lifecycle.execute()
```

---

### `controllers/relay/models.py` (controller, request-response)

**Analog:** `services/router-service/src/controllers/messages.py` lines 17-39 (list_anthropic_models)

**Core pattern** (adapted for D-19/D-20):
```python
"""GET /v1/models — OpenAI-compatible model list endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api_service.relay.auth import ValidatedApiKey, require_api_key
from api_service.relay.dependencies import get_routing_config_cache

router = APIRouter()


@router.get("/v1/models")
async def list_models(
    principal: ValidatedApiKey = Depends(require_api_key),
):
    config_cache = get_routing_config_cache()
    config = config_cache.load()
    all_models = set(config.get("user_facing_aliases", []))

    allowed = principal.allowed_models
    if allowed:
        allowed_set = set(m.strip() for m in allowed.split(",") if m.strip())
        available = all_models & allowed_set
    else:
        available = all_models

    models = [
        {"id": model_id, "object": "model", "created": 0, "owned_by": "eucal-ai"}
        for model_id in sorted(available)
    ]
    return {"object": "list", "data": models}
```

---

### `relay/schemas/chat.py` (model, request-response)

**Analog:** `services/router-service/src/schemas/requests.py`

**Complete pattern** (lines 1-42):
```python
"""Pydantic request schemas for OpenAI Chat Completions."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(..., min_length=1, max_length=128)
    messages: list[dict[str, Any]] = Field(..., min_length=1, max_length=256)
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None
    # ... other OpenAI-compatible fields ...
    stream_options: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None

    @model_validator(mode="after")
    def _check_total_content_size(self) -> ChatCompletionRequest:
        total = sum(len(str(m.get("content", ""))) for m in self.messages)
        if total > 512_000:
            raise ValueError("total message content exceeds 512KB limit")
        return self
```

---

### `relay/schemas/anthropic.py` (model, request-response)

**Analog:** `services/router-service/src/schemas/anthropic.py` — 原样移植

---

### `relay/schemas/responses.py` (model, request-response)

**Analog:** `services/router-service/src/schemas/responses.py` — 原样移植

---

### `relay/lua/token_bucket.lua` (config, request-response)

**Analog:** `services/router-service/src/services/lua/token_bucket.lua` — 原样移植

**Complete pattern** (27 lines):
```lua
-- Token bucket rate limiter
-- KEYS[1] = hash key (fields: tokens, last_refill)
-- ARGV[1] = capacity (max tokens)
-- ARGV[2] = refill_rate (tokens per second)
-- ARGV[3] = cost (tokens to consume, typically 1)
local now = redis.call('TIME')
local now_s = tonumber(now[1]) + tonumber(now[2]) / 1000000
local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens'))
local last = tonumber(redis.call('HGET', KEYS[1], 'last_refill'))
if not tokens or not last then
    tokens = tonumber(ARGV[1])
    last = now_s
else
    local elapsed = now_s - last
    tokens = math.min(tonumber(ARGV[1]), tokens + elapsed * tonumber(ARGV[2]))
    last = now_s
end
if tokens < tonumber(ARGV[3]) then
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_refill', last)
    redis.call('EXPIRE', KEYS[1], 120)
    return 0
end
tokens = tokens - tonumber(ARGV[3])
redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_refill', last)
redis.call('EXPIRE', KEYS[1], 120)
return 1
```

---

## Shared Patterns

### Authentication (Phase 6 — already implemented)
**Source:** `services/api-service/api_service/relay/auth.py`
**Apply to:** All controller files (via `Depends(require_api_key)`)
```python
from api_service.relay.auth import ValidatedApiKey, require_api_key

# In controller endpoint signature:
principal: ValidatedApiKey = Depends(require_api_key),
```

### Rate Limiting (Phase 7 NEW)
**Source:** `relay/rate_limiter.py` (to be created)
**Apply to:** All relay controller files (via `Depends(require_rate_limit)`)
```python
from api_service.relay.rate_limiter import require_rate_limit

# In controller endpoint signature (AFTER require_api_key):
_rate_limit: None = Depends(require_rate_limit),
```

### Error Handling — Protocol-specific error formatting
**Source:** Each ProtocolAdapter's `format_error()` method
**Apply to:** All lifecycle error paths
```python
# OpenAI format:
{"error": {"message": "...", "type": "server_error", "param": None, "code": "..."}}

# Anthropic format:
{"type": "error", "error": {"type": "api_error", "message": "..."}}
```

### Dependency Injection — Module-level singleton pattern
**Source:** `services/api-service/api_service/relay/dependencies.py` lines 18-84
**Apply to:** `get_sdk_client_pool()`, `get_rate_limiter()` additions
```python
# Module-level singleton (initially None)
_sdk_client_pool: SdkClientPool | None = None

def get_sdk_client_pool() -> SdkClientPool:
    if _sdk_client_pool is None:
        raise RuntimeError("SdkClientPool not initialized — call init_relay_globals first")
    return _sdk_client_pool
```

### Lifespan Registration
**Source:** `services/api-service/api_service/core/lifespan.py` lines 101-171
**Apply to:** SdkClientPool init/shutdown, RateLimiter init
```python
# In register_relay_resources():
sdk_pool = SdkClientPool(max_size=settings.SDK_CLIENT_POOL_MAX_SIZE)
rate_limiter = RateLimiter(redis=cache_redis, settings=settings)
# ... pass to init_relay_globals ...

# Shutdown:
await sdk_pool.close_all()
```

### StreamingResponse pattern
**Source:** `services/router-service/src/services/call_lifecycle.py` lines 273-286
**Apply to:** All stream response paths
```python
from fastapi.responses import StreamingResponse

return StreamingResponse(
    stream_events(lifecycle, converter),
    media_type="text/event-stream",
    headers={"cache-control": "no-cache", "connection": "keep-alive"},
)
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | All files have exact analogs in router-service |

---

## Metadata

**Analog search scope:** `services/router-service/src/`, `services/api-service/api_service/`
**Files scanned:** ~55 (router-service) + ~30 (api-service relay + controllers)
**Pattern extraction date:** 2026-05-19
