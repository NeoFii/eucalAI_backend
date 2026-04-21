"""Admin management endpoints."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.dependencies import get_db_session
from admin_service.models import AdminUser
from admin_service.policies import require_super_admin
from admin_service.schemas import (
    AdminBaseResponse,
    AdminListItem,
    AdminListResponse,
    AdminListResponseData,
    CreateAdminRequest,
    CreateAdminResponse,
    CreateAdminResponseData,
    ResetAdminPasswordRequest,
    UpdateAdminStatusRequest,
)
from admin_service.services.management_service import AdminManagementService

router = APIRouter(prefix="/admin-users", tags=["admin-users"])


def _request_meta(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


@router.get("/", response_model=AdminListResponse, summary="List admin users")
async def list_admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminListResponse:
    del current_admin
    admins, total = await AdminManagementService.list_admins(db, page=page, page_size=page_size)
    return AdminListResponse(
        code=200,
        message="success",
        data=AdminListResponseData(
            items=[
                AdminListItem(
                    uid=str(admin.uid),
                    email=admin.email,
                    name=admin.name,
                    role=admin.role,
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


@router.post("/", response_model=CreateAdminResponse, summary="Create admin user")
async def create_admin_user(
    payload: CreateAdminRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> CreateAdminResponse:
    ip_address, user_agent = _request_meta(request)
    admin = await AdminManagementService.create_admin(
        db,
        actor_admin=current_admin,
        email=payload.email,
        name=payload.name,
        password=payload.password,
        ip_address=ip_address,
        user_agent=user_agent,
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


@router.patch("/{uid}/status", response_model=AdminBaseResponse, summary="Update admin status")
async def update_admin_user_status(
    uid: int,
    payload: UpdateAdminStatusRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminBaseResponse:
    ip_address, user_agent = _request_meta(request)
    await AdminManagementService.update_admin_status(
        db,
        actor_admin=current_admin,
        target_uid=uid,
        status=payload.status,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return AdminBaseResponse(code=200, message="success")


@router.post(
    "/{uid}/reset-password", response_model=AdminBaseResponse, summary="Reset admin password"
)
async def reset_admin_user_password(
    uid: int,
    payload: ResetAdminPasswordRequest,
    request: Request,
    current_admin: AdminUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminBaseResponse:
    ip_address, user_agent = _request_meta(request)
    await AdminManagementService.reset_admin_password(
        db,
        actor_admin=current_admin,
        target_uid=uid,
        new_password=payload.new_password,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return AdminBaseResponse(code=200, message="success")
