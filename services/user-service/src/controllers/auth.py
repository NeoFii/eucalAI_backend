"""
用户认证端点
提供注册、登录、登出等接口
"""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import (
    AuthenticationException,
    SessionNotFoundException,
    ServiceUnavailableException,
)
from core.config import settings
from core.dependencies import get_db_session
from models import User
from core.policies import require_active_user
from schemas import (
    AuthBaseResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    LoginResponseData,
    LoginWithCodeRequest,
    LogoutResponse,
    RefreshResponse,
    RefreshResponseData,
    RegisterRequest,
    RegisterResponse,
    RegisterResponseData,
    ResetPasswordRequest,
    SendEmailCodeRequest,
    UserData,
    UserInfoResponse,
    UserInfoResponseData,
    VerifyEmailRequest,
)
from services.auth_service import AuthService
from services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["认证"])

# Cookie names are namespaced to "user_*" so the user and admin front-ends can
# coexist on the same domain without overwriting each other's tokens. Path stays
# "/" because Next.js page-level middleware (which gates /console) needs to see
# the cookie when the browser navigates to a page route, not just /api requests.
USER_ACCESS_COOKIE = "user_access_token"
USER_REFRESH_COOKIE = "user_refresh_token"
USER_COOKIE_PATH = "/"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        key=USER_ACCESS_COOKIE,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=USER_COOKIE_PATH,
    )
    response.set_cookie(
        key=USER_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=USER_COOKIE_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    for key in (USER_ACCESS_COOKIE, USER_REFRESH_COOKIE):
        response.delete_cookie(
            key=key,
            path=USER_COOKIE_PATH,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
        )


@router.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
    description="通过邮箱和密码注册新用户",
)
async def register(
    request: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    request_obj: Request = None,
) -> RegisterResponse:
    user_agent = request_obj.headers.get("user-agent") if request_obj else None
    ip_address = request_obj.client.host if request_obj and request_obj.client else None

    try:
        user = await AuthService.register(db, request)
        user, access_token, refresh_token = await AuthService.login(
            db, user.email, request.password, user_agent, ip_address
        )
    except Exception:
        logger.exception("用户注册失败")
        raise

    _set_auth_cookies(response, access_token, refresh_token)

    return RegisterResponse(
        code=201,
        message="注册成功",
        data=RegisterResponseData(
            uid=user.uid,
            email=user.email,
            created_at=user.created_at,
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="用户登录",
    description="使用邮箱和密码登录",
)
async def login(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    request_obj: Request = None,
) -> LoginResponse:
    user_agent = request_obj.headers.get("user-agent") if request_obj else None
    ip_address = request_obj.client.host if request_obj and request_obj.client else None

    try:
        user, access_token, refresh_token = await AuthService.login(
            db, request.email, request.password, user_agent, ip_address
        )
    except Exception:
        logger.exception("用户登录失败")
        raise

    _set_auth_cookies(response, access_token, refresh_token)

    return LoginResponse(
        code=200,
        message="登录成功",
        data=LoginResponseData(
            user=UserData(
                uid=user.uid,
                email=user.email,
                status=user.status,
                email_verified_at=user.email_verified_at,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
            ),
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


@router.post(
    "/auth/login-with-code",
    response_model=LoginResponse,
    summary="验证码登录",
    description="使用邮箱验证码登录（无需密码）",
)
async def login_with_code(
    request: LoginWithCodeRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    request_obj: Request = None,
) -> LoginResponse:
    user_agent = request_obj.headers.get("user-agent") if request_obj else None
    ip_address = request_obj.client.host if request_obj and request_obj.client else None

    try:
        user, access_token, refresh_token = await AuthService.login_with_code(
            db, request.email, request.code, user_agent, ip_address
        )
    except Exception:
        logger.exception("验证码登录失败")
        raise

    _set_auth_cookies(response, access_token, refresh_token)

    return LoginResponse(
        code=200,
        message="登录成功",
        data=LoginResponseData(
            user=UserData(
                uid=user.uid,
                email=user.email,
                status=user.status,
                email_verified_at=user.email_verified_at,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
            ),
            access_token=access_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    summary="用户登出",
    description="登出当前用户，使 Token 失效",
)
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias=USER_REFRESH_COOKIE),
    db: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    try:
        if refresh_token:
            try:
                await AuthService.logout(db, refresh_token)
            except SessionNotFoundException:
                pass
    except Exception:
        logger.exception("用户登出失败")

    _clear_auth_cookies(response)
    return LogoutResponse(code=200, message="登出成功")


@router.post(
    "/auth/refresh",
    response_model=RefreshResponse,
    summary="刷新 Token",
    description="使用刷新令牌获取新的访问令牌",
)
async def refresh_token(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias=USER_REFRESH_COOKIE),
    db: AsyncSession = Depends(get_db_session),
) -> RefreshResponse:
    if not refresh_token:
        raise AuthenticationException(detail="未提供刷新令牌")

    try:
        new_access_token, new_refresh_token = await AuthService.refresh_access_token(
            db, refresh_token
        )
    except Exception:
        _clear_auth_cookies(response)
        raise

    _set_auth_cookies(response, new_access_token, new_refresh_token)

    return RefreshResponse(
        code=200,
        message="刷新成功",
        data=RefreshResponseData(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


@router.get(
    "/auth/me",
    response_model=UserInfoResponse,
    summary="获取当前用户信息",
    description="获取当前登录用户的详细信息",
)
async def get_me(
    current_user: User = Depends(require_active_user),
) -> UserInfoResponse:
    return UserInfoResponse(
        code=200,
        message="获取成功",
        data=UserInfoResponseData(
            uid=current_user.uid,
            email=current_user.email,
            status=current_user.status,
            email_verified_at=current_user.email_verified_at,
            last_login_at=current_user.last_login_at,
            created_at=current_user.created_at,
        ),
    )


@router.post(
    "/auth/change-password",
    response_model=ChangePasswordResponse,
    summary="修改密码",
    description="修改当前登录用户的密码",
)
async def change_password(
    request: ChangePasswordRequest,
    response: Response,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChangePasswordResponse:
    try:
        await AuthService.change_password(
            db, current_user, request.old_password, request.new_password, request.lang
        )
    except Exception:
        logger.exception("修改密码失败")
        raise

    _clear_auth_cookies(response)
    return ChangePasswordResponse(code=200, message="密码修改成功，请重新登录")


@router.post(
    "/auth/reset-password",
    response_model=AuthBaseResponse,
    summary="重置密码",
    description="通过邮箱验证码重置密码",
)
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthBaseResponse:
    try:
        await AuthService.reset_password(
            db, request.email, request.code, request.new_password, request.lang
        )
    except Exception:
        logger.exception("重置密码失败")
        raise

    return AuthBaseResponse(code=200, message="密码重置成功")


@router.post(
    "/auth/send-email-code",
    response_model=AuthBaseResponse,
    summary="发送邮箱验证码",
    description="发送邮箱验证码用于注册或重置密码",
)
async def send_email_code(
    request: SendEmailCodeRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthBaseResponse:
    try:
        sent, message = await email_service.send_verification_code(db, request.email, request.purpose)
    except Exception:
        logger.exception("发送验证码失败")
        raise

    if not sent:
        raise ServiceUnavailableException(detail=message)

    return AuthBaseResponse(code=200, message="验证码已发送")


@router.post(
    "/auth/verify-email",
    response_model=AuthBaseResponse,
    summary="验证邮箱",
    description="验证邮箱验证码（用于确认邮箱所有权）",
)
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthBaseResponse:
    try:
        await AuthService.verify_email(db, request.email, request.code)
    except Exception:
        logger.exception("验证邮箱失败")
        raise

    return AuthBaseResponse(code=200, message="邮箱验证成功")
