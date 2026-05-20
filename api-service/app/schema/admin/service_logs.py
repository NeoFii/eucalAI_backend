"""Schemas for the service-logs monitoring endpoint.

Ported from services/admin-service/src/schemas/service_logs.py with rewrites:
- Standalone Pydantic models (no BaseResponse wrapper — controller builds ApiResponse)
"""

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
    total: int = 0
    latest_seq: int = 0
    error: Optional[str] = None


class ServiceLogsResponseData(BaseModel):
    results: List[ServiceLogResult]
    items: List[ServiceLogEntry] = []
    total: int = 0
    page: int = 1
    page_size: int = 50
