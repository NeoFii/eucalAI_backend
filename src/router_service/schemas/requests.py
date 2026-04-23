"""Pydantic request schemas for router-service endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(..., min_length=1, max_length=128)
    messages: list[dict[str, Any]] = Field(..., min_length=1, max_length=256)
    stream: bool = False

    # Safe litellm passthrough fields (OpenAI-compatible)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None
    n: int | None = None
    seed: int | None = None
    user: str | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    logprobs: bool | None = None
    top_logprobs: int | None = None
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    stream_options: dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None

    @model_validator(mode="after")
    def _check_total_content_size(self) -> ChatCompletionRequest:
        total = sum(len(str(m.get("content", ""))) for m in self.messages)
        if total > 512_000:
            raise ValueError("total message content exceeds 512KB limit")
        return self


_MAX_PROMPT_CHARS = 512_000


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(..., min_length=1, max_length=128)
    prompt: str | list[str]
    stream: bool = False
    suffix: str | None = None

    # Safe litellm passthrough fields
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None
    n: int | None = None
    seed: int | None = None
    user: str | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None

    @model_validator(mode="after")
    def _check_prompt_size(self) -> CompletionRequest:
        if isinstance(self.prompt, list):
            total = sum(len(str(p)) for p in self.prompt)
        else:
            total = len(self.prompt)
        if total > _MAX_PROMPT_CHARS:
            raise ValueError("prompt exceeds 512KB limit")
        return self
