"""Pydantic schemas for the /internal/v1/classify endpoint."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    messages: list[Dict[str, Any]] = Field(..., min_length=1)
    request_id: Optional[str] = None


class ClassifyResponse(BaseModel):
    request_id: str
    scores_0_2: Dict[str, float]
    proto_weighted_0_2: Optional[float] = None
    total_score_0_10: float
    score_source: str
    routing_tier: int
    selected_model: str
    tier_model_map: Dict[int, str]
    score_bands_raw: str
