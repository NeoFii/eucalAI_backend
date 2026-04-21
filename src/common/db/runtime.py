"""Stateless database runtime helpers for service-local DB modules."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class ServiceDatabaseRuntime:
    """Manage engine/session lifecycle for a single service-local declarative base."""

    def __init__(self, base: type[DeclarativeBase]) -> None:
        self._base = base
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[sessionmaker] = None

    def create_engine(
        self,
        database_url: str,
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 20,
    ) -> AsyncEngine:
        """Create and cache an async engine for this service."""
        self._engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
        )
        return self._engine

    def get_engine(self) -> AsyncEngine:
        """Return the initialized engine."""
        if self._engine is None:
            raise RuntimeError("Database engine has not been initialized")
        return self._engine

    def init_session_factory(self) -> sessionmaker:
        """Initialize the async session factory for this service."""
        if self._engine is None:
            raise RuntimeError("Database engine has not been initialized")
        self._session_factory = sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        return self._session_factory

    async def get_db(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a request-scoped async session."""
        if self._session_factory is None:
            raise RuntimeError("Session factory has not been initialized")
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @asynccontextmanager
    async def get_db_context(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an async session for non-request contexts."""
        if self._session_factory is None:
            raise RuntimeError("Session factory has not been initialized")
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close_db(self) -> None:
        """Dispose the current engine and clear the session factory."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        self._session_factory = None
