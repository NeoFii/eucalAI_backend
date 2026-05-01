"""Internal usage log and stat endpoints."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams
from common.utils.timezone import now
from controllers.internal import verify_internal_secret
from core.dependencies import get_db_session
from schemas.internal_usage import (
    InternalUsageLogItem,
    InternalUsageLogListResponse,
    InternalUsageStatItem,
)
from services.usage_stat_service import UsageStatService

logger = logging.getLogger("user_service.internal.usage")

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get(
    "/usage/logs",
    response_model=InternalUsageLogListResponse,
    summary="List usage logs",
)
async def list_usage_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = None,
    model_name: str | None = None,
    request_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUsageLogListResponse:
    params = ListParams(page=page, page_size=page_size, order_by="created_at")
    if start or end:
        params.time_field = "created_at"
        params.start = start
        params.end = end
        params.validate_time_range(default_end=now(), default_days=30)
    result = await UsageStatService.list_usage_logs(
        db, params=params, user_id=user_id, model_name=model_name, request_id=request_id,
    )
    return InternalUsageLogListResponse(
        items=[InternalUsageLogItem.model_validate(log) for log in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/usage/stats", summary="List usage stats")
async def list_usage_stats(
    user_id: int | None = None,
    model_name: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> list[InternalUsageStatItem]:
    params = ListParams(page=1, page_size=1000, order_by="stat_hour")
    if start or end:
        params.time_field = "stat_hour"
        params.start = start
        params.end = end
        params.validate_time_range(default_end=now(), default_days=30)
    items = await UsageStatService.get_all_stats(
        db, start=params.start, end=params.end, user_id=user_id, model_name=model_name,
    )
    return [InternalUsageStatItem.model_validate(s) for s in items]
