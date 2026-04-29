"""
用户服务依赖注入
提供 FastAPI 依赖函数
"""

from typing import Optional

from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
    UserNotFoundException,
)
from common.observability import set_uid
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
    """
    token = None

    if credentials and credentials.credentials:
        token = credentials.credentials
    elif access_token:
        token = access_token

    if not token:
        raise AuthenticationException(detail="未提供认证信息")

    payload = decode_token(
        token=token,
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    if not payload:
        raise InvalidTokenException()

    if payload.get("type") != "access":
        raise InvalidTokenException(detail="无效的令牌类型")

    uid = payload.get("uid")
    if not uid:
        raise InvalidTokenException(detail="令牌中未包含用户信息")

    user = await AuthService.get_current_user(db, uid)

    if not user:
        raise UserNotFoundException()

    set_uid(user.uid)
    return user
