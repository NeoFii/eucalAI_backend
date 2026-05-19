"""Admin-on-admin management endpoints (admin_users).

Ported from `services/admin-service/src/controllers/admin_users.py` in
Plan 05-02 / Task 2.  Standard rewrites + the Pitfall 3 service rename:

- `from services.management_service import AdminManagementService` →
  `from api_service.services.admin.account_service import AdminAccountService`
  (Pitfall 3 — file + class renamed; admin-on-admin operations live in
  `account_service.py` to keep them separate from `AdminEndUserService` in
  Plan 05-03 which manages END users.)

Router prefix is `/admin-users`; final mount: `/api/v1/admin/admin-users/*`.

5 endpoints: list / create / update_status / reset_password / update_role.
"""
# ruff: noqa: B008

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.api.pagination import PaginatedResponse
from api_service.common.schemas import BaseResponse
from api_service.core.db import get_db
from api_service.core.policies import require_super_admin
from api_service.models import AdminUser
from api_service.schemas.admin import (
    AdminListItem,
    AdminListResponse,
    CreateAdminRequest,
    CreateAdminResponse,
    CreateAdminResponseData,
    ResetAdminPasswordRequest,
    UpdateAdminRoleRequest,
    UpdateAdminStatusRequest,
)
from api_service.services.admin.account_service import AdminAccountService

router = APIRouter(prefix="/admin-users", tags=["admin-admin-users"])


@router.get("", response_model=AdminListResponse, summary="List admin users")
async def list_admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminListResponse:
    admins, total = await AdminAccountService.list_admins(
        db, page=page, page_size=page_size,
    )
    return AdminListResponse(
        code=200,
        message="success",
        data=PaginatedResponse[AdminListItem](
            items=[
                AdminListItem(
                    uid=str(admin.uid),
                    email=admin.email,
                    name=admin.name,
                    role=admin.role,
                    is_root=getattr(admin, "is_root", False),
                    status=admin.status,
                    last_login_at=admin.last_login_at,
                    created_at=admin.created_at,
                    updated_at=admin.updated_at,
                )
                for admin in admins
            ],
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.post("", response_model=CreateAdminResponse, summary="Create admin user")
async def create_admin_user(
    payload: CreateAdminRequest,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> CreateAdminResponse:
    admin = await AdminAccountService.create_admin(
        db,
        actor_admin=current_admin,
        email=payload.email,
        name=payload.name,
        password=payload.password,
        role=payload.role,
    )
    return CreateAdminResponse(
        code=200,
        message="success",
        data=CreateAdminResponseData(
            uid=str(admin.uid),
            email=admin.email,
            name=admin.name,
            role=admin.role,
            status=admin.status,
            created_at=admin.created_at,
            updated_at=admin.updated_at,
        ),
    )


@router.patch("/{uid}/status", response_model=BaseResponse, summary="Update admin status")
async def update_admin_user_status(
    uid: str,
    payload: UpdateAdminStatusRequest,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseResponse:
    await AdminAccountService.update_admin_status(
        db, actor_admin=current_admin, target_uid=uid, status=payload.status,
    )
    return BaseResponse(code=200, message="success")


@router.post(
    "/{uid}/reset-password",
    response_model=BaseResponse,
    summary="Reset admin password",
)
async def reset_admin_user_password(
    uid: str,
    payload: ResetAdminPasswordRequest,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseResponse:
    await AdminAccountService.reset_admin_password(
        db,
        actor_admin=current_admin,
        target_uid=uid,
        new_password=payload.new_password,
    )
    return BaseResponse(code=200, message="success")


@router.patch("/{uid}/role", response_model=BaseResponse, summary="Update admin role")
async def update_admin_user_role(
    uid: str,
    payload: UpdateAdminRoleRequest,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseResponse:
    await AdminAccountService.update_admin_role(
        db, actor_admin=current_admin, target_uid=uid, role=payload.role,
    )
    return BaseResponse(code=200, message="success")


__all__ = ["router"]
