"""Pydantic request schema for OpenAI Responses API compatibility."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(..., min_length=1, max_length=128)
    input: str | list[dict[str, Any]] = Field(...)
    instructions: str | None = None
    max_output_tokens: int | None = None
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    reasoning: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    previous_response_id: str | None = None
    parallel_tool_calls: bool | None = None
    text: dict[str, Any] | None = None
    truncation: str | None = None
