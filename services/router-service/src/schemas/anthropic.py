"""Pydantic request schemas for Anthropic Messages API compatibility."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImageSource(BaseModel):
    type: Literal["base64", "url"] = "base64"
    media_type: str | None = None
    data: str | None = None
    url: str | None = None


class AnthropicMessagesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(..., min_length=1, max_length=128)
    messages: list[dict[str, Any]] = Field(..., min_length=1, max_length=256)
    max_tokens: int = Field(..., ge=1)
    system: str | list[dict[str, Any]] | None = None
    stream: bool = False

    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    thinking: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _check_total_content_size(self) -> AnthropicMessagesRequest:
        total = 0
        for msg in self.messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            total += len(block.get("text", ""))
        if total > 512_000:
            raise ValueError("total message text content exceeds 512KB limit")
        return self
