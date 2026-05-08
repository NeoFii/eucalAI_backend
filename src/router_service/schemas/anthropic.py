"""Pydantic request schemas for Anthropic Messages API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnthropicMessagesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = Field(..., min_length=1, max_length=128)
    messages: list[dict[str, Any]] = Field(..., min_length=1, max_length=256)
    max_tokens: int | None = None
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
                        total += len(str(block.get("text", block.get("content", ""))))
                    else:
                        total += len(str(block))
            else:
                total += len(str(content))
        if total > 512_000:
            raise ValueError("total message content exceeds 512KB limit")
        return self
