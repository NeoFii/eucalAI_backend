# -*- coding: utf-8 -*-
"""Testing service API dependencies."""

from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import AuthenticationException, InvalidTokenException
from testing_service.db import get_db
from common.utils.jwt import decode_token
from testing_service.config import get_settings
from testing_service.gateway import AdminIdentityGateway

security = HTTPBearer(auto_error=False)
settings = get_settings()


@dataclass(slots=True)
class AdminPrincipal:
    """Testing-local admin contract."""

    id: int
    uid: int
    email: str
    name: str
    role: str
    status: int


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for request handlers."""
    async for session in get_db():
        yield session


async def get_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> AdminPrincipal:
    """Validate an admin access token and return a testing-local principal."""
    del request
    del db

    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif access_token:
        token = access_token

    if not token:
        raise AuthenticationException(detail="Missing admin access token")

    payload = decode_token(
        token=token,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    if not payload or payload.get("type") != "access":
        raise InvalidTokenException()

    uid = payload.get("uid")
    if not uid:
        raise InvalidTokenException(detail="Token payload missing admin uid")

    admin = await AdminIdentityGateway.fetch_admin_by_uid(uid)
    if not admin:
        raise AuthenticationException(detail="Admin identity not found")
    if admin.status == 0:
        raise AuthenticationException(detail="Admin account is disabled")

    return AdminPrincipal(
        id=admin.id,
        uid=admin.uid,
        email=admin.email,
        name=admin.name,
        role=admin.role,
        status=admin.status,
    )
