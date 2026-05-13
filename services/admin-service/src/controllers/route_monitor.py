"""Admin route-monitor endpoints (proxies user-service /internal/route-monitor/*)."""

# ruff: noqa: B008

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from common.api import PaginatedResponse
from common.utils.timezone import format_iso
from core.policies import require_active_admin, require_super_admin
from gateways.route_monitor import RouteMonitorGateway
from models import AdminUser
from schemas.route_monitor import (
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

router = APIRouter(prefix="/route-monitor", tags=["admin-route-monitor"])

_gateway = RouteMonitorGateway()


@router.get(
    "/requests",
    response_model=RouteRequestListResponse,
    summary="List route-monitor requests (paginated, drill-down list)",
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
    status: int | None = Query(None, ge=0, le=4),
    score_min: float | None = Query(None, ge=0.0, le=10.0),
    score_max: float | None = Query(None, ge=0.0, le=10.0),
    request_id: str | None = Query(None, max_length=64),
    input_hash: str | None = Query(None, max_length=32),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    _current_admin: AdminUser = Depends(require_active_admin),
) -> RouteRequestListResponse:
    if score_min is not None and score_max is not None and score_min > score_max:
        raise HTTPException(status_code=400, detail="score_min cannot be greater than score_max")

    data = await _gateway.list_requests(
        page=page,
        page_size=page_size,
        user_id=user_id,
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
        start=format_iso(start) if start else None,
        end=format_iso(end) if end else None,
    )
    return RouteRequestListResponse(
        data=PaginatedResponse[RouteRequestListItem](
            items=[RouteRequestListItem(**item) for item in data["items"]],
            total=data["total"],
            page=data["page"],
            page_size=data["page_size"],
        ),
    )


@router.get(
    "/requests/{request_id}",
    response_model=RouteRequestDetailResponse,
    summary="Get full detail of a route-monitor request (super_admin only — contains user input/response)",
)
async def get_request_detail(
    request_id: str = Path(max_length=64),
    _current_admin: AdminUser = Depends(require_super_admin),
) -> RouteRequestDetailResponse:
    data = await _gateway.get_request_detail(request_id)
    return RouteRequestDetailResponse(data=RouteRequestDetail(**data))


@router.get(
    "/aggregates",
    response_model=RouteAggregateResponse,
    summary="Aggregate dashboard buckets",
)
async def get_aggregates(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    user_id: int | None = Query(None),
    user_uid: str | None = Query(None),
    model_name: str | None = Query(None, max_length=64),
    provider_slug: str | None = Query(None, max_length=32),
    _current_admin: AdminUser = Depends(require_active_admin),
) -> RouteAggregateResponse:
    data = await _gateway.get_aggregates(
        start=format_iso(start) if start else None,
        end=format_iso(end) if end else None,
        user_id=user_id,
        user_uid=user_uid,
        model_name=model_name,
        provider_slug=provider_slug,
    )
    return RouteAggregateResponse(data=RouteAggregateData(**data))


@router.get(
    "/compare/{request_id}",
    response_model=RouteCompareResponse,
    summary="Replay/compare view: rows with same input hash (super_admin only)",
)
async def get_compare(
    request_id: str = Path(max_length=64),
    limit: int = Query(20, ge=1, le=50),
    _current_admin: AdminUser = Depends(require_super_admin),
) -> RouteCompareResponse:
    data = await _gateway.get_compare(request_id, limit=limit)
    target_data = data.get("target")
    return RouteCompareResponse(
        data=RouteCompareData(
            input_hash=data.get("input_hash"),
            target=RouteCompareItem(**target_data) if target_data else None,
            siblings=[RouteCompareItem(**s) for s in data.get("siblings", [])],
        ),
    )
