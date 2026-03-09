"""
管理员服务 FastAPI 入口点
运行在端口 8001
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 将 backend 目录添加到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from common.core.exception_handlers import register_exception_handlers
from common.db import close_db, create_engine, init_db, init_session_factory
from common.utils.snowflake import configure_snowflake
from admin.api import api_router
from admin.config import settings
import admin.models  # noqa: F401 — 显式注册所有模型到 Base.metadata

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    """
    # 启动
    logger.info("管理员服务启动中...")

    # 配置雪花 ID
    configure_snowflake(
        worker_id=settings.SNOWFLAKE_WORKER_ID,
        datacenter_id=settings.SNOWFLAKE_DATACENTER_ID,
    )
    logger.info(f"雪花 ID 配置完成: worker={settings.SNOWFLAKE_WORKER_ID}, datacenter={settings.SNOWFLAKE_DATACENTER_ID}")

    # 创建数据库引擎
    create_engine(
        database_url=settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DATABASE_ECHO,
    )
    logger.info("数据库引擎创建完成")

    # 初始化会话工厂
    try:
        init_session_factory()
        logger.info("会话工厂初始化完成")
    except Exception as e:
        logger.error(f"会话工厂初始化失败: {e}")
        raise

    # 初始化数据库（创建表）
    try:
        await init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise

    logger.info(f"管理员服务启动完成: http://0.0.0.0:{settings.PORT}")

    yield

    # 关闭
    logger.info("管理员服务关闭中...")
    await close_db()
    logger.info("数据库连接已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# 配置 CORS - 使用配置文件中的允许域名列表
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_hosts,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册统一异常处理器
register_exception_handlers(app)

# 注册 API 路由
app.include_router(api_router)


@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "admin", "version": settings.VERSION}


@app.get("/", tags=["根路径"])
async def root():
    """根路径"""
    return {
        "message": "Eucal AI 管理员服务",
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "admin.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
