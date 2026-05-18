"""Admin auth dependencies — extracts JWT from Bearer header or cookie with blacklist check."""

from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api_service.common.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
)
from api_service.common.observability import set_uid
from api_service.common.security.jwt import decode_token, get_token_jti
from api_service.common.security.token_blacklist import is_token_blacklisted
from api_service.core.config import settings
from api_service.core.db import get_db
from api_service.models import AdminUser
from api_service.repositories.admin_user_repository import AdminUserRepository

security = HTTPBearer(auto_error=False)


async def get_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None, alias="admin_access_token"),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """Resolve the current authenticated admin from Bearer token or cookie.

    Includes blacklist check (D-07).
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

    if await is_token_blacklisted(get_token_jti(token)):
        raise InvalidTokenException(detail="令牌已被吊销")

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
        raise InvalidTokenException(detail="令牌中未包含管理员信息")

    admin = await AdminUserRepository(db).get_by_uid(uid)

    if not admin:
        raise AuthenticationException(detail="管理员不存在")

    set_uid(admin.uid)
    return admin


async def get_optional_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None, alias="admin_access_token"),
    db: AsyncSession = Depends(get_db),
) -> AdminUser | None:
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
