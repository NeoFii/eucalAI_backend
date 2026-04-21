"""Pydantic request schemas for router-service endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    messages: list[dict[str, Any]]
    stream: bool = False


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    prompt: str | list[str]
    stream: bool = False
    suffix: str | None = None
