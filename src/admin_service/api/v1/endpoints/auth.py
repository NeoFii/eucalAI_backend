"""Admin authentication endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.config import settings
from admin_service.dependencies import get_db_session
from admin_service.models import AdminUser
from admin_service.policies import require_active_admin
from admin_service.schemas import (
    AdminChangePasswordRequest,
    AdminChangePasswordResponse,
    AdminInfoResponse,
    AdminInfoResponseData,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminLoginResponseData,
    AdminLogoutResponse,
    AdminRefreshResponse,
    AdminRefreshResponseData,
    AdminUserData,
)
from admin_service.services.auth_service import AdminAuthService
from common.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
)
from common.utils.jwt import create_refresh_token

router = APIRouter(tags=["admin-auth"])
_bearer = HTTPBearer(auto_error=False)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")


@router.post("/auth/login", response_model=AdminLoginResponse, summary="Admin login")
async def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> AdminLoginResponse:
    """Authenticate an admin and issue cookies."""
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    admin, access_token = await AdminAuthService.login(
        db,
        payload.email,
        payload.password,
        user_agent,
        ip_address,
    )
    refresh_token = create_refresh_token(
        data={"uid": admin.uid, "sub": str(admin.uid)},
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        expire_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    )

    _set_auth_cookies(response, access_token, refresh_token)

    return AdminLoginResponse(
        code=200,
        message="登录成功",
        data=AdminLoginResponseData(
            user=AdminUserData(
                uid=str(admin.uid),
                email=admin.email,
                name=admin.name,
                role=admin.role,
            ),
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


@router.post("/auth/logout", response_model=AdminLogoutResponse, summary="Admin logout")
async def logout(
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    access_token: Optional[str] = Cookie(default=None),
    refresh_token_cookie: Optional[str] = Cookie(default=None, alias="refresh_token"),
    current_admin: AdminUser = Depends(require_active_admin),
) -> AdminLogoutResponse:
    """Revoke active tokens and clear cookies."""
    raw_access = credentials.credentials if credentials else access_token
    await AdminAuthService.logout(
        current_admin,
        access_token=raw_access,
        refresh_token=refresh_token_cookie,
    )
    _clear_auth_cookies(response)
    return AdminLogoutResponse(code=200, message="退出成功")


@router.post("/auth/refresh", response_model=AdminRefreshResponse, summary="Refresh token")
async def refresh_token(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db_session),
) -> AdminRefreshResponse:
    """Refresh admin auth cookies."""
    if not isinstance(refresh_token, str) or not refresh_token:
        raise AuthenticationException(detail="未提供刷新令牌")
    try:
        new_access_token, new_refresh_token = await AdminAuthService.refresh_access_token(
            db, refresh_token
        )
    except (InvalidTokenException, AuthenticationException):
        _clear_auth_cookies(response)
        raise

    _set_auth_cookies(response, new_access_token, new_refresh_token)
    return AdminRefreshResponse(
        code=200,
        message="刷新成功",
        data=AdminRefreshResponseData(
            access_token=new_access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


@router.get("/auth/me", response_model=AdminInfoResponse, summary="Current admin")
async def get_me(
    current_admin: AdminUser = Depends(require_active_admin),
) -> AdminInfoResponse:
    """Return the current admin profile."""
    return AdminInfoResponse(
        code=200,
        message="获取成功",
        data=AdminInfoResponseData(
            uid=str(current_admin.uid),
            email=current_admin.email,
            name=current_admin.name,
            role=current_admin.role,
            status=current_admin.status,
            last_login_at=current_admin.last_login_at,
            created_at=current_admin.created_at,
        ),
    )


@router.post(
    "/auth/change-password",
    response_model=AdminChangePasswordResponse,
    summary="Change admin password",
)
async def change_password(
    payload: AdminChangePasswordRequest,
    request: Request,
    response: Response,
    current_admin: AdminUser = Depends(require_active_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminChangePasswordResponse:
    """Change the current admin password and clear cookies."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    await AdminAuthService.change_password(
        db,
        current_admin,
        payload.old_password,
        payload.new_password,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _clear_auth_cookies(response)
    return AdminChangePasswordResponse(code=200, message="密码修改成功，请重新登录")
