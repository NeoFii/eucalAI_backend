"""Internal route-monitor endpoints (admin-service -> user-service).

Read-only queries that back the admin "路由监控" panel. All endpoints use the
shared internal-secret auth (admin-service is the only consumer).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import ListParams
from common.utils.timezone import now
from controllers.internal import verify_internal_secret
from controllers.internal_user_mgmt import _get_user_or_404
from core.dependencies import get_db_session
from repositories.route_monitor_repository import RouteMonitorRepository
from schemas.internal_route_monitor import (
    RouteAggregateData,
    RouteCompareItem,
    RouteCompareResponse,
    RouteRequestDetail,
    RouteRequestListItem,
    RouteRequestListResponse,
)

logger = logging.getLogger("user_service.internal.route_monitor")

router = APIRouter(prefix="/internal/route-monitor", tags=["internal"])

DEFAULT_LOOKBACK_DAYS = 7
MAX_LOOKBACK_DAYS = 90
DEFAULT_AGGREGATE_LOOKBACK_HOURS = 24
MAX_COMPARE_LIMIT = 50


@router.get(
    "/requests",
    response_model=RouteRequestListResponse,
    summary="List route-monitor request rows (paginated)",
)
async def list_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = Query(None),
    user_uid: str | None = Query(None),
    model_name: str | None = Query(None, max_length=64),
    selected_model: str | None = Query(None, max_length=64),
    provider_slug: str | None = Query(None, max_length=32),
    routing_tier: int | None = Query(None, ge=1, le=5),
    status: int | None = Query(None, ge=200, le=599),
    score_min: float | None = Query(None, ge=0.0, le=10.0),
    score_max: float | None = Query(None, ge=0.0, le=10.0),
    request_id: str | None = Query(None, max_length=64),
    input_hash: str | None = Query(None, max_length=32),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> RouteRequestListResponse:
    resolved_user_id = user_id
    if resolved_user_id is None and user_uid:
        user = await _get_user_or_404(db, user_uid)
        resolved_user_id = user.id
    if score_min is not None and score_max is not None and score_min > score_max:
        raise HTTPException(status_code=400, detail="score_min cannot be greater than score_max")

    params = ListParams(
        page=page,
        page_size=page_size,
        order_by="created_at",
        order_dir="desc",
        time_field="created_at" if (start or end) else None,
        start=start,
        end=end,
        max_span_days=MAX_LOOKBACK_DAYS,
    )
    if start or end:
        params.validate_time_range(default_end=now(), default_days=DEFAULT_LOOKBACK_DAYS)

    repo = RouteMonitorRepository(db)
    result = await repo.list_requests(
        params=params,
        user_id=resolved_user_id,
        model_name=model_name,
        selected_model=selected_model,
        provider_slug=provider_slug,
        routing_tier=routing_tier,
        status=status,
        score_min=score_min,
        score_max=score_max,
        request_id=request_id,
        input_hash=input_hash,
    )
    return RouteRequestListResponse(
        items=[RouteRequestListItem.model_validate(row) for row in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/requests/{request_id}",
    response_model=RouteRequestDetail,
    summary="Get full detail of a route-monitor request (incl. preview)",
)
async def get_request_detail(
    request_id: str = Path(max_length=64),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> RouteRequestDetail:
    repo = RouteMonitorRepository(db)
    row = await repo.get_request_detail(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="route request not found")
    return RouteRequestDetail.model_validate(row)


@router.get(
    "/aggregates",
    response_model=RouteAggregateData,
    summary="Aggregate dashboard buckets for the route-monitor view",
)
async def get_aggregates(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    user_id: int | None = Query(None),
    user_uid: str | None = Query(None),
    model_name: str | None = Query(None, max_length=64),
    provider_slug: str | None = Query(None, max_length=32),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> RouteAggregateData:
    resolved_user_id = user_id
    if resolved_user_id is None and user_uid:
        user = await _get_user_or_404(db, user_uid)
        resolved_user_id = user.id
    end_eff = end or now()
    start_eff = start or end_eff - timedelta(hours=DEFAULT_AGGREGATE_LOOKBACK_HOURS)
    if start_eff >= end_eff:
        raise HTTPException(status_code=400, detail="start must be earlier than end")
    if (end_eff - start_eff).days > MAX_LOOKBACK_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"aggregate range cannot exceed {MAX_LOOKBACK_DAYS} days",
        )
    repo = RouteMonitorRepository(db)
    data = await repo.aggregate_metrics(
        start=start_eff,
        end=end_eff,
        user_id=resolved_user_id,
        model_name=model_name,
        provider_slug=provider_slug,
    )
    return RouteAggregateData(**data)


@router.get(
    "/compare/{request_id}",
    response_model=RouteCompareResponse,
    summary="Find historical rows that share the same input hash",
)
async def get_compare(
    request_id: str = Path(max_length=64),
    limit: int = Query(20, ge=1, le=MAX_COMPARE_LIMIT),
    _: None = Depends(verify_internal_secret),
    db: AsyncSession = Depends(get_db_session),
) -> RouteCompareResponse:
    repo = RouteMonitorRepository(db)
    target, siblings = await repo.find_same_input_siblings(
        request_id=request_id, limit=limit,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="route request not found")
    return RouteCompareResponse(
        input_hash=target.input_hash,
        target=RouteCompareItem.model_validate(target),
        siblings=[RouteCompareItem.model_validate(s) for s in siblings],
    )
