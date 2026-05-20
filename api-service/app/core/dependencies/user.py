"""User auth dependency — extracts JWT from Bearer header or cookie."""

from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
    UserNotFoundException,
)
from app.common.observability import set_uid
from app.common.security.jwt import decode_token
from app.core.config import settings
from app.core.db import get_db
from app.model import User
from app.repository.user_repository import UserRepository

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None, alias="user_access_token"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current authenticated user from Bearer token or cookie.

    No blacklist check is performed (D-08).
    """
    token = None

    # Prefer Authorization header
    if credentials and credentials.credentials:
        token = credentials.credentials
    # Fallback to cookie
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

    user = await UserRepository(db).get_by_uid(uid)

    if not user:
        raise UserNotFoundException()

    set_uid(user.uid)
    return user
