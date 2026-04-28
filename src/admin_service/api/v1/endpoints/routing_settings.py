"""Admin routing settings management endpoints."""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_db_session, get_request_meta
from admin_service.models import AdminUser
from admin_service.policies import require_super_admin
from admin_service.schemas.routing_setting import (
    RoutingSettingBatchUpdate,
    RoutingSettingGroupResponse,
    RoutingSettingResponse,
    RoutingSettingUpdate,
)
from admin_service.services.routing_setting_service import RoutingSettingService

router = APIRouter(prefix="/routing-settings", tags=["admin-routing-settings"])


@router.get("", response_model=RoutingSettingGroupResponse, summary="List all routing settings")
async def list_settings(
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingSettingGroupResponse:
    grouped = await RoutingSettingService.list_all(db)
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
    item = await RoutingSettingService.update_setting(
        db, key, payload.value, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return RoutingSettingResponse(data=item)


@router.put("/batch", response_model=RoutingSettingGroupResponse, summary="Batch update settings")
async def batch_update_settings(
    payload: RoutingSettingBatchUpdate,
    http_request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoutingSettingGroupResponse:
    ip_address, user_agent = get_request_meta(http_request)
    items_tuples = [(item.key, item.value) for item in payload.items]
    grouped = await RoutingSettingService.batch_update(
        db, items_tuples, actor_admin_id=current_admin.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return RoutingSettingGroupResponse(data=grouped)
