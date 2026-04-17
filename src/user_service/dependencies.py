"""
用户服务依赖注入
提供 FastAPI 依赖函数
"""

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
    TokenExpiredException,
    UserDisabledException,
    UserNotFoundException,
)
from user_service.db import get_db
from common.utils.jwt import decode_token
from user_service.config import settings
from user_service.models import User
from user_service.services.auth_service import AuthService

# HTTP Bearer 安全方案
security = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncSession:
    """
    获取数据库会话依赖

    使用 common.db 提供的异步会话生成器
    """
    async for session in get_db():
        yield session


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """
    获取当前登录用户

    支持从以下位置获取 Token：
    1. Authorization Header (Bearer Token)
    2. Cookie (access_token)

    Args:
        request: FastAPI 请求对象
        credentials: HTTP Bearer 凭证
        access_token: Cookie 中的访问令牌
        db: 数据库会话

    Returns:
        User: 当前登录用户对象

    Raises:
        AuthenticationException: 未提供认证信息
        InvalidTokenException: 令牌无效
        TokenExpiredException: 令牌已过期
        UserNotFoundException: 用户不存在
        UserDisabledException: 用户已被禁用
    """
    token = None

    # 优先从 Authorization Header 获取
    if credentials and credentials.credentials:
        token = credentials.credentials
    # 其次从 Cookie 获取
    elif access_token:
        token = access_token

    if not token:
        raise AuthenticationException(detail="未提供认证信息")

    # 解码令牌
    payload = decode_token(
        token=token,
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    if not payload:
        raise InvalidTokenException()

    # 验证令牌类型
    if payload.get("type") != "access":
        raise InvalidTokenException(detail="无效的令牌类型")

    # 获取用户 UID
    uid = payload.get("uid")
    if not uid:
        raise InvalidTokenException(detail="令牌中未包含用户信息")

    # 查询用户
    user = await AuthService.get_current_user(db, uid)

    if not user:
        raise UserNotFoundException()

    if user.status == 0:
        raise UserDisabledException()

    return user


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    db: AsyncSession = Depends(get_db_session),
) -> Optional[User]:
    """
    可选地获取当前登录用户

    如果未提供认证信息或认证失败，返回 None 而不是抛出异常。
    适用于某些接口既支持认证用户也支持匿名访问的场景。

    Args:
        request: FastAPI 请求对象
        credentials: HTTP Bearer 凭证
        access_token: Cookie 中的访问令牌
        db: 数据库会话

    Returns:
        Optional[User]: 当前登录用户对象，或 None
    """
    try:
        return await get_current_user(request, credentials, access_token, db)
    except Exception:
        return None


async def require_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    要求用户处于正常状态

    在 get_current_user 基础上额外验证用户邮箱是否已验证。

    Args:
        current_user: 当前登录用户

    Returns:
        User: 当前登录用户对象

    Raises:
        HTTPException: 用户邮箱未验证
    """
    if not current_user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先验证邮箱",
        )
    return current_user
