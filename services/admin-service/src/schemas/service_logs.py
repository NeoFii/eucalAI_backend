"""Schemas for the service-logs monitoring endpoint."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class ServiceLogEntry(BaseModel):
    seq: int
    timestamp: str
    service: str
    level: str
    logger: str
    event: str
    message: Optional[str] = None
    traceId: Optional[str] = None
    spanId: Optional[str] = None
    requestId: Optional[str] = None
    uid: Optional[str] = None
    env: Optional[str] = None
    durationMs: Optional[float] = None
    error: Optional[dict[str, Any]] = None
    exception: Optional[str] = None


class ServiceLogResult(BaseModel):
    service: str
    reachable: bool
    entries: List[ServiceLogEntry] = []
    latest_seq: int = 0
    error: Optional[str] = None


class ServiceLogsResponseData(BaseModel):
    results: List[ServiceLogResult]
    merged: List[ServiceLogEntry] = []
    total: int = 0


class ServiceLogsResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: ServiceLogsResponseData | None = None
