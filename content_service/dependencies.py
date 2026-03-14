"""Content service dependencies."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from content_service.db import get_db


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for request handlers."""
    async for session in get_db():
        yield session
