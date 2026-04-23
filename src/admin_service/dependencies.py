"""
管理员服务依赖注入
提供 FastAPI 依赖函数
"""

from typing import Optional

from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from admin_service.config import settings
from admin_service.db import get_db
from admin_service.models import AdminUser
from admin_service.services.auth_service import AdminAuthService
from common.core.exceptions import AuthenticationException, InvalidTokenException
from common.token_blacklist import is_token_blacklisted
from common.utils.jwt import decode_token, get_token_jti

# HTTP Bearer 安全方案
security = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncSession:
    """
    获取数据库会话依赖
    """
    async for session in get_db():
        yield session


async def get_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> AdminUser:
    """
    获取当前登录管理员

    支持从以下位置获取 Token：
    1. Authorization Header (Bearer Token)
    2. Cookie (access_token)
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

    if await is_token_blacklisted(get_token_jti(token)):
        raise InvalidTokenException(detail="令牌已被吊销")

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

    # 获取管理员 UID
    uid = payload.get("uid")
    if not uid:
        raise InvalidTokenException(detail="令牌中未包含管理员信息")

    # 查询管理员
    admin = await AdminAuthService.get_current_admin(db, uid)

    if not admin:
        raise AuthenticationException(detail="管理员不存在")

    return admin


async def get_optional_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> Optional[AdminUser]:
    """Return the current admin when authentication succeeds, else None."""
    try:
        return await get_current_admin(
            request=request,
            credentials=credentials,
            access_token=access_token,
            db=db,
        )
    except (AuthenticationException, InvalidTokenException):
        return None


def get_request_meta(request: Request) -> tuple[str | None, str | None]:
    """Extract IP address and user-agent from a FastAPI request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


__all__ = [
    "get_current_admin",
    "get_db_session",
    "get_optional_current_admin",
    "get_request_meta",
]
