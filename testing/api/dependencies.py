# -*- coding: utf-8 -*-
"""Testing 服务 API 依赖"""

from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.db import get_db


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话依赖
    """
    async for session in get_db():
        yield session
