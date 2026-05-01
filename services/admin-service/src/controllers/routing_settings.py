"""Admin routing settings management endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, get_request_meta
from models import AdminUser
from core.policies import require_super_admin
from schemas.routing_setting import (
    RoutingSettingBatchUpdate,
    RoutingSettingGroupResponse,
    RoutingSettingResponse,
    RoutingSettingUpdate,
)
from services.routing_setting_service import RoutingSettingService

router = APIRouter(prefix="/routing-settings", tags=["admin-routing-settings"])


@router.get("", response_model=RoutingSettingGroupResponse, summary="List all routing settings")
async def list_settings(
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingSettingGroupResponse:
    grouped = await RoutingSettingService.list_all(db)
    return RoutingSettingGroupResponse(data=grouped)


@router.put("/batch", response_model=RoutingSettingGroupResponse, summary="Batch update settings")
async def batch_update_settings(
    payload: RoutingSettingBatchUpdate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingSettingGroupResponse:
    ip_address, user_agent = get_request_meta(http_request)
    items_tuples = [(item.key, item.value) for item in payload.items]
    await RoutingSettingService.validate_tier_model_coverage(db, items_tuples)
    grouped = await RoutingSettingService.batch_update(
        db, items_tuples, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return RoutingSettingGroupResponse(data=grouped)


@router.put("/{key}", response_model=RoutingSettingResponse, summary="Update single setting")
async def update_setting(
    key: str,
    payload: RoutingSettingUpdate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingSettingResponse:
    ip_address, user_agent = get_request_meta(http_request)
    await RoutingSettingService.validate_tier_model_coverage(db, [(key, payload.value)])
    item = await RoutingSettingService.update_setting(
        db, key, payload.value, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return RoutingSettingResponse(data=item)
