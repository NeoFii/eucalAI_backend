"""
FastAPI 应用入口
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings


def create_application() -> FastAPI:
    """
    应用工厂函数，创建并配置 FastAPI 实例
    """
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # 配置 CORS - 允许前端跨域访问
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API 路由
    application.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # 健康检查端点
    @application.get("/health", tags=["监控"])
    async def health_check():
        """服务健康检查"""
        return {"status": "healthy", "version": settings.VERSION}

    # 根路由 - API 信息
    @application.get("/", tags=["根"])
    async def root():
        """API 根信息"""
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs": "/docs",
            "api": settings.API_V1_PREFIX,
        }

    return application


app = create_application()
