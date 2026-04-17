"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    messages: List[Dict[str, Any]]
    stream: bool = False


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    prompt: str | List[str]
    stream: bool = False
    suffix: str | None = None
