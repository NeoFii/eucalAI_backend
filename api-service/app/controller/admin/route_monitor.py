"""Admin route-monitor endpoints — proxy elimination.

Ported from services/admin-service/src/controllers/route_monitor.py.
All RouteMonitorGateway calls replaced with AdminRouteMonitorService direct calls.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import BaseResponse
from app.core.db import get_db
from app.core.policies import require_active_admin, require_super_admin
from app.model import AdminUser
from app.schema.admin.route_monitor import (
    RouteAggregateData,
    RouteAggregateResponse,
    RouteCompareData,
    RouteCompareItem,
    RouteCompareResponse,
    RouteRequestDetail,
    RouteRequestDetailResponse,
    RouteRequestListItem,
    RouteRequestListResponse,
)
from app.service.admin.route_monitor_service import AdminRouteMonitorService

router = APIRouter(prefix="/route-monitor", tags=["admin-route-monitor"])


@router.get(
    "/requests",
    response_model=RouteRequestListResponse,
    summary="List route-monitor requests",
)
async def list_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
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
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> RouteRequestListResponse:
    if score_min is not None and score_max is not None and score_min > score_max:
        raise HTTPException(status_code=400, detail="score_min cannot be greater than score_max")

    items, total = await AdminRouteMonitorService.list_requests(
        db,
        page=page,
        page_size=page_size,
        user_uid=user_uid,
        model_name=model_name,
        selected_model=selected_model,
        provider_slug=provider_slug,
        routing_tier=routing_tier,
        status=status,
        score_min=score_min,
        score_max=score_max,
        request_id=request_id,
        input_hash=input_hash,
        start=start,
        end=end,
    )
    return RouteRequestListResponse(
        data={
            "items": [
                RouteRequestListItem.model_validate(i, from_attributes=True).model_dump(mode="json")
                for i in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get(
    "/requests/{request_id}",
    response_model=RouteRequestDetailResponse,
    summary="Get full detail of a route-monitor request",
)
async def get_request_detail(
    request_id: str = Path(max_length=64),
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> RouteRequestDetailResponse:
    data = await AdminRouteMonitorService.get_request_detail(db, request_id=request_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return RouteRequestDetailResponse(data=RouteRequestDetail.model_validate(data, from_attributes=True))


@router.get(
    "/aggregates",
    response_model=RouteAggregateResponse,
    summary="Aggregate dashboard buckets",
)
async def get_aggregates(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    user_uid: str | None = Query(None),
    model_name: str | None = Query(None, max_length=64),
    provider_slug: str | None = Query(None, max_length=32),
    _current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db),
) -> RouteAggregateResponse:
    data = await AdminRouteMonitorService.get_aggregates(
        db,
        start=start,
        end=end,
        user_uid=user_uid,
        model_name=model_name,
        provider_slug=provider_slug,
    )
    return RouteAggregateResponse(data=RouteAggregateData(**data) if data else None)


@router.get(
    "/compare/{request_id}",
    response_model=RouteCompareResponse,
    summary="Replay/compare view: rows with same input hash",
)
async def get_compare(
    request_id: str = Path(max_length=64),
    limit: int = Query(20, ge=1, le=50),
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> RouteCompareResponse:
    data = await AdminRouteMonitorService.get_compare(db, request_id=request_id, limit=limit)
    target_data = data.get("target")
    siblings_data = data.get("siblings", [])
    return RouteCompareResponse(
        data=RouteCompareData(
            input_hash=data.get("input_hash"),
            target=RouteCompareItem.model_validate(target_data, from_attributes=True) if target_data else None,
            siblings=[RouteCompareItem.model_validate(s, from_attributes=True) for s in siblings_data],
        ),
    )
