"""
数据库引擎和会话管理
提供异步数据库连接和会话管理
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base

# 引擎实例（由各个服务初始化）
_engine: Optional[AsyncEngine] = None
_AsyncSessionLocal: Optional[sessionmaker] = None


def create_engine(
    database_url: str,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
) -> AsyncEngine:
    """
    创建异步数据库引擎

    Args:
        database_url: 数据库连接 URL
        echo: 是否打印 SQL 语句
        pool_size: 连接池大小
        max_overflow: 最大溢出连接数

    Returns:
        AsyncEngine: 异步引擎实例
    """
    global _engine
    _engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,  # 连接前 ping 检查，避免使用断开的连接
    )
    return _engine


def get_engine() -> AsyncEngine:
    """获取已创建的引擎实例"""
    if _engine is None:
        raise RuntimeError("数据库引擎尚未初始化，请先调用 create_engine()")
    return _engine


def init_session_factory() -> sessionmaker:
    """
    初始化会话工厂
    必须在 create_engine 之后调用
    """
    global _AsyncSessionLocal
    if _engine is None:
        raise RuntimeError("数据库引擎尚未初始化，请先调用 create_engine()")
    _AsyncSessionLocal = sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,  # 提交后不过期对象，避免异步问题
        autocommit=False,
        autoflush=False,
    )
    return _AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话
    用于 FastAPI 依赖注入

    Yields:
        AsyncSession: 数据库会话
    """
    if _AsyncSessionLocal is None:
        raise RuntimeError("会话工厂尚未初始化，请先调用 init_session_factory()")
    async with _AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话的上下文管理器
    用于非 FastAPI 依赖注入场景

    Usage:
        async with get_db_context() as db:
            await db.execute(...)
    """
    if _AsyncSessionLocal is None:
        raise RuntimeError("会话工厂尚未初始化，请先调用 init_session_factory()")
    async with _AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    初始化数据库
    创建所有表结构
    注意：生产环境建议使用 Alembic 进行迁移
    """
    if _engine is None:
        raise RuntimeError("数据库引擎尚未初始化，请先调用 create_engine()")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    关闭数据库连接
    应用关闭时调用
    """
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
