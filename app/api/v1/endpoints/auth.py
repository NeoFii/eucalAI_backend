"""
认证相关 API 端点
提供注册、登录、登出、刷新令牌等功能
"""

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.models.auth_schemas import (
    AuthErrorResponse,
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
from app.services.auth_service import AuthService
from app.services.email_service import email_service
from app.utils.jwt import verify_access_token

# 创建速率限制器
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(tags=["认证"])


# Cookie 配置常量
COOKIE_KEY_ACCESS_TOKEN = "access_token"
COOKIE_KEY_REFRESH_TOKEN = "refresh_token"


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    secure: bool = True,
    samesite: str = "lax",
) -> None:
    """
    设置认证相关的 Cookie

    Args:
        response: FastAPI 响应对象
        access_token: 访问令牌
        refresh_token: 刷新令牌
        secure: 是否仅 HTTPS 传输
        samesite: SameSite 属性
    """
    # 设置 access_token Cookie
    response.set_cookie(
        key=COOKIE_KEY_ACCESS_TOKEN,
        value=access_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=15 * 60,  # 15 分钟
        path="/",
    )

    # 设置 refresh_token Cookie
    response.set_cookie(
        key=COOKIE_KEY_REFRESH_TOKEN,
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=7 * 24 * 60 * 60,  # 7 天
        path="/",  # 修复：与前端期望一致
    )


def clear_auth_cookies(response: Response) -> None:
    """清除认证相关的 Cookie"""
    # 必须传入与 set_cookie 相同的参数（从 settings 读取），否则浏览器不会清除
    from app.config import settings
    response.delete_cookie(
        key=COOKIE_KEY_ACCESS_TOKEN,
        path="/",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=COOKIE_KEY_REFRESH_TOKEN,
        path="/",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


async def get_current_user_uid(
    access_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> int:
    """
    获取当前用户 UID

    Args:
        access_token: Cookie 中的 access_token
        db: 数据库会话

    Returns:
        int: 用户 UID

    Raises:
        HTTPException: 认证失败
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
        )

    payload = verify_access_token(access_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期",
        )

    uid = payload.get("uid")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌",
        )

    # 校验用户存在性和状态
    result = await db.execute(
        select(User).where(User.uid == int(uid))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if user.status != 1:  # 0=禁用, 1=正常, 2=待验证
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号已被禁用",
        )

    return int(uid)


@router.post(
    "/send-code",
    response_model=AuthErrorResponse,
    summary="发送邮箱验证码",
    responses={
        400: {"model": AuthErrorResponse, "description": "发送失败"},
        200: {"model": AuthErrorResponse, "description": "发送成功"},
    },
)
async def send_verification_code(
    request: SendEmailCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthErrorResponse:
    """
    发送邮箱验证码

    - **email**: 邮箱地址
    - **purpose**: 用途（register/reset_password）

    注册流程：
    1. 先调用此接口发送验证码（会检查邮箱是否已注册）
    2. 用户输入验证码和密码后调用注册接口完成注册
    """
    # 注册时检查邮箱是否已被注册
    if request.purpose == "register":
        result = await db.execute(
            select(User).where(User.email == request.email)
        )
        if result.scalar_one_or_none():
            return AuthErrorResponse(code=400, message="该邮箱已被注册")

    # 登录时检查用户是否存在
    if request.purpose == "login":

        result = await db.execute(
            select(User).where(User.email == request.email)
        )
        user = result.scalar_one_or_none()
        if not user:
            return AuthErrorResponse(code=400, message="该邮箱未注册")
        # 检查用户状态
        if user.status == 0:
            return AuthErrorResponse(code=400, message="账户已被禁用，请联系管理员")

    # 重置密码时检查用户是否存在
    if request.purpose == "reset_password":
        result = await db.execute(
            select(User).where(User.email == request.email)
        )
        user = result.scalar_one_or_none()
        if not user:
            return AuthErrorResponse(code=400, message="该邮箱未注册")

    success, error = await email_service.send_verification_code(
        db, request.email, request.purpose
    )

    if not success:
        return AuthErrorResponse(code=400, message=error)

    return AuthErrorResponse(code=200, message="验证码已发送")


@router.post(
    "/verify-email",
    response_model=AuthErrorResponse,
    summary="验证邮箱",
    responses={
        400: {"model": AuthErrorResponse, "description": "验证失败"},
        200: {"model": AuthErrorResponse, "description": "验证成功"},
    },
)
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthErrorResponse:
    """
    验证邮箱验证码

    - **email**: 邮箱地址
    - **code**: 6位验证码
    """
    await AuthService.verify_email(db, request.email, request.code)
    return AuthErrorResponse(code=200, message="邮箱验证成功")


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
    responses={
        400: {"model": AuthErrorResponse, "description": "注册失败"},
        201: {"model": RegisterResponse, "description": "注册成功"},
    },
)
@limiter.limit("5/minute")  # 限制每分钟5次注册
async def register(
    request: Request,
    response: Response,
    register_request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """
    用户注册

    - 注册成功后返回 access_token 和 refresh_token（同时自动登录）
    - **email**: 登录邮箱（唯一）
    - **password**: 密码（至少8位，包含大小写+数字+特殊字符）
    - **nickname**: 显示昵称（可选）
    - **verification_code**: 邮箱验证码（预留字段，暂不校验）
    """
    user = await AuthService.register(db, register_request)

    # 注册成功后自动登录，生成 Token
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    _, access_token, refresh_token = await AuthService.login(
        db,
        email=user.email,
        password=register_request.password,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    # 获取 Token 过期时间
    from app.config import settings
    access_token_expire_seconds = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # 设置 Cookie（保留，用于 CSRF 防护）
    set_auth_cookies(
        response,
        access_token,
        refresh_token,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    return RegisterResponse(
        code=201,
        message="注册成功",
        data=RegisterResponseData(
            uid=user.uid,
            email=user.email,
            nickname=user.nickname,
            created_at=user.created_at,
            access_token=access_token,
            # refresh_token 已通过 Set-Cookie 写入，此处不返回
            expires_in=access_token_expire_seconds,
        ),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="用户登录",
    responses={
        400: {"model": AuthErrorResponse, "description": "登录失败"},
        200: {"model": LoginResponse, "description": "登录成功"},
    },
)
@limiter.limit("10/minute")  # 限制每分钟10次登录尝试
async def login(
    request: Request,
    response: Response,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    用户登录

    - 成功后返回 access_token 和 refresh_token（同时设置 Cookie）
    - 采用互踢模式，新登录会注销其他设备的会话

    - **email**: 登录邮箱
    - **password**: 密码
    """
    # 获取客户端信息
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    user, access_token, refresh_token = await AuthService.login(
        db,
        email=data.email,
        password=data.password,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    # 获取 Token 过期时间
    from app.config import settings
    access_token_expire_seconds = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # 设置 Cookie（保留，用于 CSRF 防护）
    set_auth_cookies(
        response,
        access_token,
        refresh_token,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    return LoginResponse(
        code=200,
        message="登录成功",
        data=LoginResponseData(
            user=UserData(
                uid=user.uid,
                email=user.email,
                nickname=user.nickname,
                avatar_url=user.avatar_url,
            ),
            access_token=access_token,
            # refresh_token 已通过 Set-Cookie 写入，此处不返回
            expires_in=access_token_expire_seconds,
        ),
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="用户登出",
)
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    """
    用户登出

    - 清除 Cookie
    - 注销当前会话（如果会话存在）
    注意：即使会话不存在，也要清除 Cookie，确保用户能成功登出
    """
    if refresh_token:
        try:
            await AuthService.logout(db, refresh_token)
        except Exception:
            # 即使会话不存在或已注销，也要清除 Cookie
            # 不影响用户登出流程
            pass

    clear_auth_cookies(response)

    return LogoutResponse(code=200, message="登出成功")


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="刷新访问令牌",
)
async def refresh(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    """
    刷新 access_token

    - 仅支持从 Cookie 读取 refresh_token（与前端契约一致）
    - 成功后返回新的 access_token 和 refresh_token（同时更新 Cookie）
    """
    # 只从 Cookie 获取 token
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供刷新令牌",
        )

    new_access_token, new_refresh_token = await AuthService.refresh_access_token(db, refresh_token)

    # 获取 Token 过期时间
    from app.config import settings
    access_token_expire_seconds = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # 更新 Cookie（保留）
    response.set_cookie(
        key=COOKIE_KEY_ACCESS_TOKEN,
        value=new_access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    return RefreshResponse(
        code=200,
        message="刷新成功",
        data=RefreshResponseData(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=access_token_expire_seconds,
        ),
    )


@router.get(
    "/me",
    response_model=UserInfoResponse,
    summary="获取当前用户信息",
)
async def get_me(
    uid: int = Depends(get_current_user_uid),
    db: AsyncSession = Depends(get_db),
) -> UserInfoResponse:
    """
    获取当前登录用户信息

    - 需要登录（自动验证 access_token Cookie）
    """
    user = await AuthService.get_current_user(db, uid)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    return UserInfoResponse(
        code=200,
        message="获取成功",
        data=UserInfoResponseData(
            uid=user.uid,
            email=user.email,
            nickname=user.nickname,
            avatar_url=user.avatar_url,
            status=user.status,
            email_verified_at=user.email_verified_at,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        ),
    )


@router.post(
    "/password/change",
    response_model=ChangePasswordResponse,
    summary="修改密码",
)
async def change_password(
    request: ChangePasswordRequest,
    uid: int = Depends(get_current_user_uid),
    db: AsyncSession = Depends(get_db),
) -> ChangePasswordResponse:
    """
    修改当前用户密码

    - 需要登录
    - 修改成功后，所有设备需要重新登录

    - **old_password**: 旧密码
    - **new_password**: 新密码（需符合强度要求）
    """
    user = await AuthService.get_current_user(db, uid)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    await AuthService.change_password(
        db, user, request.old_password, request.new_password
    )

    return ChangePasswordResponse(code=200, message="密码修改成功，请重新登录")


@router.post(
    "/login-with-code",
    response_model=LoginResponse,
    summary="邮箱验证码登录",
    responses={
        400: {"model": AuthErrorResponse, "description": "登录失败"},
        200: {"model": LoginResponse, "description": "登录成功"},
    },
)
async def login_with_code(
    request: Request,
    response: Response,
    data: LoginWithCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    邮箱验证码登录

    - 使用邮箱收到的6位验证码登录
    - 成功后设置 access_token 和 refresh_token Cookie

    - **email**: 登录邮箱
    - **code**: 6位验证码
    """
    # 获取客户端信息
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    user, access_token, refresh_token = await AuthService.login_with_code(
        db,
        email=data.email,
        code=data.code,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    # 获取 Token 过期时间
    from app.config import settings
    access_token_expire_seconds = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # 设置 Cookie（保留，用于 CSRF 防护）
    set_auth_cookies(
        response,
        access_token,
        refresh_token,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    return LoginResponse(
        code=200,
        message="登录成功",
        data=LoginResponseData(
            user=UserData(
                uid=user.uid,
                email=user.email,
                nickname=user.nickname,
                avatar_url=user.avatar_url,
            ),
            access_token=access_token,
            # refresh_token 已通过 Set-Cookie 写入，此处不返回
            expires_in=access_token_expire_seconds,
        ),
    )


@router.post(
    "/reset-password",
    response_model=ChangePasswordResponse,
    summary="重置密码",
    responses={
        400: {"model": ChangePasswordResponse, "description": "重置失败"},
        200: {"model": ChangePasswordResponse, "description": "重置成功"},
    },
)
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ChangePasswordResponse:
    """
    重置密码

    - 通过邮箱验证码验证后重置密码
    - 重置成功后所有设备需要重新登录

    - **email**: 邮箱地址
    - **code**: 6位验证码
    - **new_password**: 新密码（需符合强度要求）
    """
    await AuthService.reset_password(
        db,
        email=request.email,
        code=request.code,
        new_password=request.new_password,
    )

    return ChangePasswordResponse(code=200, message="密码重置成功，请使用新密码登录")
