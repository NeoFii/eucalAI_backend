"""
管理员认证端点
提供管理员登录、登出等接口
"""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import (
    AuthenticationException,
    InvalidCredentialsException,
    InvalidTokenException,
    TokenExpiredException,
)
from admin.config import settings
from admin.dependencies import get_current_admin, get_db_session
from admin.models import AdminUser
from admin.schemas import (
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
from admin.services.auth_service import AdminAuthService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["管理员认证"])


@router.post(
    "/auth/login",
    response_model=AdminLoginResponse,
    summary="管理员登录",
    description="使用邮箱和密码登录",
)
async def login(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> AdminLoginResponse:
    """管理员登录接口"""
    try:
        # 解析请求体
        body = await request.json()
        email = body.get("email")
        password = body.get("password")

        if not email or not password:
            raise InvalidCredentialsException()

        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

        admin, access_token = await AdminAuthService.login(
            db, email, password, user_agent, ip_address
        )

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )

        return AdminLoginResponse(
            code=200,
            message="登录成功",
            data=AdminLoginResponseData(
                user=AdminUserData(
                    uid=admin.uid,
                    email=admin.email,
                    name=admin.name,
                    role=admin.role,
                ),
                access_token=access_token,
                expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            ),
        )

    except InvalidCredentialsException as e:
        raise e
    except Exception as e:
        logger.exception("管理员登录失败")
        raise e


@router.post(
    "/auth/logout",
    response_model=AdminLogoutResponse,
    summary="管理员登出",
    description="登出当前管理员",
)
async def logout(
    response: Response,
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminLogoutResponse:
    """管理员登出接口"""
    await AdminAuthService.logout(current_admin)

    response.delete_cookie(key="access_token")

    return AdminLogoutResponse(code=200, message="登出成功")


@router.post(
    "/auth/refresh",
    response_model=AdminRefreshResponse,
    summary="刷新 Token",
    description="刷新访问令牌",
)
async def refresh_token(
    response: Response,
    access_token: Optional[str] = Cookie(None, alias="access_token"),
) -> AdminRefreshResponse:
    """刷新访问令牌接口"""
    if not access_token:
        raise AuthenticationException(detail="未提供令牌")

    try:
        # 验证当前令牌，获取 uid
        from common.utils.jwt import decode_token
        payload = decode_token(
            access_token,
            settings.JWT_SECRET_KEY,
            settings.JWT_ALGORITHM,
        )
        if not payload:
            raise InvalidTokenException()

        uid = payload.get("uid")
        if not uid:
            raise InvalidTokenException()

        # 生成新令牌
        new_access_token = await AdminAuthService.refresh_access_token(access_token)

        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

        return AdminRefreshResponse(
            code=200,
            message="刷新成功",
            data=AdminRefreshResponseData(
                access_token=new_access_token,
                expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            ),
        )

    except (InvalidTokenException, TokenExpiredException) as e:
        response.delete_cookie(key="access_token")
        raise e
    except Exception as e:
        logger.exception("刷新令牌失败")
        raise e


@router.get(
    "/auth/me",
    response_model=AdminInfoResponse,
    summary="获取当前管理员信息",
    description="获取当前登录管理员的详细信息",
)
async def get_me(
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminInfoResponse:
    """获取当前管理员信息"""
    return AdminInfoResponse(
        code=200,
        message="获取成功",
        data=AdminInfoResponseData(
            uid=current_admin.uid,
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
    summary="修改密码",
    description="修改当前登录管理员的密码",
)
async def change_password(
    request: Request,
    response: Response,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminChangePasswordResponse:
    """修改密码接口"""
    try:
        body = await request.json()
        old_password = body.get("old_password")
        new_password = body.get("new_password")

        await AdminAuthService.change_password(
            db, current_admin, old_password, new_password
        )

        response.delete_cookie(key="access_token")

        return AdminChangePasswordResponse(code=200, message="密码修改成功，请重新登录")

    except InvalidCredentialsException as e:
        raise e
    except Exception as e:
        logger.exception("修改密码失败")
        raise e
