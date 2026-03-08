# -*- coding: utf-8 -*-
"""
Testing 服务主入口
提供模型管理、供应商管理和性能测试 API
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.db import create_engine, init_session_factory, init_db, close_db
from testing.config import get_settings
from testing.api.v1.router import api_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
database_url = settings.get_database_url()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("Starting Testing Service...")

    # 初始化数据库
    try:
        create_engine(database_url)
        init_session_factory()
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    yield

    # 关闭时
    logger.info("Shutting down Testing Service...")
    await close_db()


# 创建 FastAPI 应用
app = FastAPI(
    title="Eucal AI Testing Service",
    description="模型管理、供应商管理和性能测试 API",
    version="1.0.0",
    lifespan=lifespan,
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "testing"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "testing.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
