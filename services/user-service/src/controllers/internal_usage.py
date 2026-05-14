"""Internal usage log and stat endpoints."""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams
from common.utils.timezone import now, to_shanghai_naive
from controllers.internal import verify_internal_secret
from controllers.internal_user_mgmt import _get_user_or_404
from core.dependencies import get_db_session
from schemas.billing import UsageAnalyticsData
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
    user_uid: str | None = None,
    model_name: str | None = None,
    request_id: str | None = None,
    api_key_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> InternalUsageLogListResponse:
    resolved_user_id = user_id
    if resolved_user_id is None and user_uid:
        user = await _get_user_or_404(db, user_uid)
        resolved_user_id = user.id
    params = ListParams(page=page, page_size=page_size, order_by="created_at")
    if start or end:
        params.time_field = "created_at"
        params.start = start
        params.end = end
        params.validate_time_range(default_end=now(), default_days=30)
    result = await UsageStatService.list_usage_logs(
        db, params=params, user_id=resolved_user_id, model_name=model_name,
        request_id=request_id, api_key_id=api_key_id,
    )
    return InternalUsageLogListResponse(
        items=[InternalUsageLogItem.from_orm_instance(log) for log in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/usage/stats", summary="List usage stats")
async def list_usage_stats(
    user_id: int | None = None,
    user_uid: str | None = None,
    model_name: str | None = None,
    api_key_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> list[InternalUsageStatItem]:
    resolved_user_id = user_id
    if resolved_user_id is None and user_uid:
        user = await _get_user_or_404(db, user_uid)
        resolved_user_id = user.id
    params = ListParams(page=1, page_size=1000, order_by="stat_hour")
    if start or end:
        params.time_field = "stat_hour"
        params.start = start
        params.end = end
        params.validate_time_range(default_end=now(), default_days=30)
    if api_key_id is not None:
        items = await UsageStatService.get_user_stats(
            db, user_id=resolved_user_id, start=params.start, end=params.end,
            model_name=model_name, api_key_id=api_key_id,
        )
    else:
        items = await UsageStatService.get_all_stats(
            db, start=params.start, end=params.end, user_id=resolved_user_id, model_name=model_name,
        )
    return [InternalUsageStatItem.model_validate(s) for s in items]


@router.get("/users/{uid}/usage/stats", summary="Get user usage stats by uid")
async def get_user_usage_stats(
    uid: str,
    start: datetime | None = None,
    end: datetime | None = None,
    model_name: str | None = None,
    api_key_id: int | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> list[InternalUsageStatItem]:
    user = await _get_user_or_404(db, uid)
    params = ListParams(page=1, page_size=1000, order_by="stat_hour")
    if start or end:
        params.time_field = "stat_hour"
        params.start = start
        params.end = end
    params.validate_time_range(default_end=now(), default_days=30)
    items = await UsageStatService.get_user_stats(
        db, user_id=user.id, start=params.start, end=params.end,
        model_name=model_name, api_key_id=api_key_id,
    )
    return [InternalUsageStatItem.model_validate(s) for s in items]


@router.get("/users/{uid}/usage/analytics", summary="Get user usage analytics by uid")
async def get_user_usage_analytics(
    uid: str,
    range: Literal["8h", "24h", "7d", "30d"] | None = Query(None, alias="range"),
    start: datetime | None = None,
    end: datetime | None = None,
    api_key_id: int | None = None,
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> UsageAnalyticsData:
    user = await _get_user_or_404(db, uid)
    return await UsageStatService.get_usage_analytics(
        db,
        user_id=user.id,
        range_name=range,
        start=to_shanghai_naive(start),
        end=to_shanghai_naive(end),
        api_key_id=api_key_id,
    )
