"""OpenAI SDK backend: direct calls to OpenAI-compatible upstreams."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from services.sdk_clients import SdkClientPool


@dataclass
class OpenAIResponse:
    """Wrapper that mimics litellm response interface (.model_dump())."""

    _data: dict[str, Any] = field(repr=False)

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        if not exclude_none:
            return self._data
        return {k: v for k, v in self._data.items() if v is not None}


@dataclass
class OpenAIStreamChunk:
    """Wrapper for a single streaming chunk."""

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
    """Call an OpenAI-compatible upstream directly via the openai SDK.

    Returns OpenAIResponse for non-streaming, or an async iterator for streaming.
    Raises openai.APIStatusError on HTTP errors (has .status_code for retry logic).
    """
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


async def _stream_iter(raw_stream: Any) -> AsyncIterator[OpenAIStreamChunk]:
    async for chunk in raw_stream:
        yield OpenAIStreamChunk(_data=chunk.model_dump(exclude_none=True))
