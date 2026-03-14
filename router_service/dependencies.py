"""Router service dependencies."""

from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from router_service.db import get_db
from common.utils.jwt import decode_token
from router_service.config import settings
from router_service.services import RouterKeyAuthService, RouterKeyContext
from router_service.services.identity_client import IdentityClientService, IdentityUser

router_key_security = HTTPBearer(auto_error=False)
user_jwt_security = HTTPBearer(auto_error=False)
RouterCurrentUser = IdentityUser


async def get_db_session() -> AsyncSession:
    """Yield a shared async DB session."""
    async for session in get_db():
        yield session


async def get_router_key_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(router_key_security),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db_session),
) -> RouterKeyContext:
    """Resolve the router API key from bearer or X-API-Key headers."""
    raw_key = None
    if credentials and credentials.credentials:
        raw_key = credentials.credentials
    elif x_api_key:
        raw_key = x_api_key

    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Router API key is required",
        )

    context = await RouterKeyAuthService.verify_key(db, raw_key)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid router API key",
        )
    return context


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(user_jwt_security),
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    db: AsyncSession = Depends(get_db_session),
) -> RouterCurrentUser:
    """Resolve a user from the shared JWT contract and identity internal API."""
    del request
    del db

    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_token(
        token=token,
        secret_key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")

    uid = payload.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")

    try:
        user = await IdentityClientService.fetch_user_by_uid(int(uid))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity service unavailable",
        ) from exc
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
    return user
