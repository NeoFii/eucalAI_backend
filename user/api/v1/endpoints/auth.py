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
    EmailAlreadyExistsException,
    EmailNotVerifiedException,
    InvalidCredentialsException,
    InvalidInvitationCodeException,
    InvalidTokenException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
    ServiceUnavailableException,
    SessionExpiredException,
    SessionNotFoundException,
    SessionRevokedException,
    TokenExpiredException,
    UserDisabledException,
    UserNotFoundException,
    WeakPasswordException,
)
from user.config import settings
from user.dependencies import get_current_user, get_db_session
from user.models import User
from user.schemas import (
    AuthBaseResponse,
    AuthErrorResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    LoginResponseData,
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
    LoginWithCodeRequest,
)
from user.services.auth_service import AuthService
from user.services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["认证"])


@router.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
    description="通过邀请码、邮箱和密码注册新用户",
)
async def register(
    request: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> RegisterResponse:
    """
    用户注册接口

    流程：
    1. 验证邀请码（调用管理服务）
    2. 检查邮箱是否已存在
    3. 验证邮箱验证码
    4. 创建用户
    5. 返回用户信息和 Token
    """
    try:
        # 创建用户（内部会验证邀请码和邮箱验证码）
        user = await AuthService.register(db, request)

        # 自动登录：创建 Token 和会话
        user, access_token, refresh_token = await AuthService.login(
            db, user.email, request.password, user_agent, ip_address
        )

        # 设置 Cookie
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )

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

    except (InvalidInvitationCodeException, InvitationCodeUsedException,
            InvitationCodeDisabledException, InvitationCodeExpiredException) as e:
        raise e
    except EmailAlreadyExistsException as e:
        raise e
    except WeakPasswordException as e:
        raise e
    except ServiceUnavailableException as e:
        raise e
    except Exception as e:
        logger.exception("用户注册失败")
        raise e


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
    """
    用户登录接口

    流程：
    1. 验证邮箱和密码
    2. 检查账户状态
    3. 撤销旧会话
    4. 创建新会话和 Token
    5. 设置 Cookie
    """
    try:
        # 获取请求信息
        user_agent = request_obj.headers.get("user-agent")
        ip_address = request_obj.client.host if request_obj.client else None

        # 执行登录
        user, access_token, refresh_token = await AuthService.login(
            db, request.email, request.password, user_agent, ip_address
        )

        # 设置 Cookie
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )

        return LoginResponse(
            code=200,
            message="登录成功",
            data=LoginResponseData(
                user=UserData(uid=user.uid, email=user.email),
                access_token=access_token,
                expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            ),
        )

    except InvalidCredentialsException as e:
        raise e
    except UserDisabledException as e:
        raise e
    except EmailNotVerifiedException as e:
        raise e
    except Exception as e:
        logger.exception("用户登录失败")
        raise e


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
    """
    邮箱验证码登录接口

    适用于：
    - 忘记密码时的临时登录
    - 快捷登录场景
    """
    try:
        user_agent = request_obj.headers.get("user-agent")
        ip_address = request_obj.client.host if request_obj.client else None

        user, access_token, refresh_token = await AuthService.login_with_code(
            db, request.email, request.code, user_agent, ip_address
        )

        # 设置 Cookie
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )

        return LoginResponse(
            code=200,
            message="登录成功",
            data=LoginResponseData(
                user=UserData(uid=user.uid, email=user.email),
                access_token=access_token,
                expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            ),
        )

    except (InvalidCredentialsException, UserNotFoundException) as e:
        raise e
    except UserDisabledException as e:
        raise e
    except Exception as e:
        logger.exception("验证码登录失败")
        raise e


@router.post(
    "/auth/logout",
    response_model=LogoutResponse,
    summary="用户登出",
    description="登出当前用户，使 Token 失效",
)
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    """
    用户登出接口

    流程：
    1. 从 Cookie 获取刷新令牌
    2. 在数据库中标记会话为已撤销
    3. 清除 Cookie
    """
    try:
        if refresh_token:
            try:
                await AuthService.logout(db, refresh_token)
            except SessionNotFoundException:
                # 会话已不存在，忽略错误继续清除 Cookie
                pass

        # 清除 Cookie
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")

        return LogoutResponse(code=200, message="登出成功")

    except Exception as e:
        logger.exception("用户登出失败")
        # 即使失败也清除 Cookie
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")
        return LogoutResponse(code=200, message="登出成功")


@router.post(
    "/auth/refresh",
    response_model=RefreshResponse,
    summary="刷新 Token",
    description="使用刷新令牌获取新的访问令牌",
)
async def refresh_token(
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db_session),
) -> RefreshResponse:
    """
    刷新访问令牌接口

    流程：
    1. 从 Cookie 获取刷新令牌
    2. 验证刷新令牌有效性
    3. 生成新的访问令牌（和新的刷新令牌）
    4. 更新 Cookie
    """
    if not refresh_token:
        raise AuthenticationException(detail="未提供刷新令牌")

    try:
        new_access_token, new_refresh_token = await AuthService.refresh_access_token(
            db, refresh_token
        )

        # 更新 Cookie
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        if new_refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=new_refresh_token,
                httponly=True,
                secure=settings.COOKIE_SECURE,
                samesite=settings.COOKIE_SAMESITE,
                max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            )

        return RefreshResponse(
            code=200,
            message="刷新成功",
            data=RefreshResponseData(
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            ),
        )

    except (InvalidTokenException, TokenExpiredException) as e:
        # Token 无效或过期，清除 Cookie
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")
        raise e
    except (SessionNotFoundException, SessionRevokedException, SessionExpiredException) as e:
        # 会话问题，清除 Cookie
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")
        raise e
    except Exception as e:
        logger.exception("刷新令牌失败")
        raise e


@router.get(
    "/auth/me",
    response_model=UserInfoResponse,
    summary="获取当前用户信息",
    description="获取当前登录用户的详细信息",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserInfoResponse:
    """
    获取当前登录用户信息
    """
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChangePasswordResponse:
    """
    修改密码接口

    修改成功后会使所有现有会话失效，需要重新登录。
    """
    try:
        await AuthService.change_password(
            db, current_user, request.old_password, request.new_password, request.lang
        )

        # 清除 Cookie（需要重新登录）
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")

        return ChangePasswordResponse(code=200, message="密码修改成功，请重新登录")

    except InvalidCredentialsException as e:
        raise e
    except WeakPasswordException as e:
        raise e
    except Exception as e:
        logger.exception("修改密码失败")
        raise e


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
    """
    重置密码接口

    流程：
    1. 验证邮箱验证码
    2. 更新密码
    3. 使所有会话失效
    """
    try:
        await AuthService.reset_password(
            db, request.email, request.code, request.new_password, request.lang
        )

        return AuthBaseResponse(code=200, message="密码重置成功")

    except UserNotFoundException as e:
        raise e
    except WeakPasswordException as e:
        raise e
    except Exception as e:
        logger.exception("重置密码失败")
        raise e


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
    """
    发送邮箱验证码接口

    用途：
    - register: 用户注册
    - reset_password: 重置密码
    - login: 验证码登录
    """
    try:
        await email_service.send_verification_code(db, request.email, request.purpose)

        return AuthBaseResponse(code=200, message="验证码已发送")

    except Exception as e:
        logger.exception("发送验证码失败")
        raise e


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
    """
    验证邮箱接口

    验证成功后标记用户邮箱为已验证。
    """
    try:
        await email_service.verify_code_or_raise(db, request.email, request.code, "verify")

        return AuthBaseResponse(code=200, message="邮箱验证成功")

    except (InvalidCredentialsException, Exception) as e:
        if isinstance(e, InvalidCredentialsException):
            raise
        logger.exception("验证邮箱失败")
        raise e
