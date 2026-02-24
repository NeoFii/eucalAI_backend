"""
FastAPI 应用入口
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.db import close_db, init_db
from app.utils.logger import (
    setup_logger,
    log_access,
    get_logger,
    app_logger,
    access_logger,
    error_logger,
)

# 配置日志 - 使用统一的日志模块
# 应用日志（文件和控制台）
app_log = setup_logger(
    name="app",
    log_file=f"{settings.LOG_FILE_PREFIX}.log",
    console=True,
)
# 访问日志（仅文件）
access_log = setup_logger(
    name="access",
    log_file="access.log",
    console=False,
)
# 错误日志（仅文件）
error_log = setup_logger(
    name="error",
    log_file="error.log",
    console=False,
)

# 统一使用 app_logger，避免重复输出
logger = app_logger


# 统一响应格式
class ApiResponse:
    """统一响应工具类"""

    @staticmethod
    def success(data: Any = None, message: str = "success", code: int = 200):
        """成功响应"""
        return {"code": code, "message": message, "data": data}

    @staticmethod
    def error(message: str = "error", code: int = 400):
        """错误响应"""
        return {"code": code, "message": message, "data": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    - 启动时初始化数据库
    - 关闭时释放资源
    """
    # 启动时初始化数据库
    await init_db()
    logger.info("数据库初始化完成")
    yield
    # 关闭时释放资源
    await close_db()
    logger.info("数据库连接已关闭")


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
        lifespan=lifespan,
    )

    # 配置 CORS - 允许前端跨域访问
    # 使用环境感知的 CORS 配置
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_hosts,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求体大小限制中间件（16MB）
    MAX_REQUEST_SIZE = 16 * 1024 * 1024  # 16MB

    @application.middleware("http")
    async def limit_request_size(request: Request, call_next):
        """限制请求体大小，防止大文件上传攻击"""
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_REQUEST_SIZE:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content=ApiResponse.error(
                        message=f"请求体过大，最大支持 {MAX_REQUEST_SIZE // (1024*1024)}MB"
                    ),
                )
        return await call_next(request)

    # 请求日志中间件
    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        """记录每个请求的日志"""
        start_time = time.time()
        request_id = str(uuid.uuid4())[:8]

        # 获取客户端信息
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")

        # 记录请求信息
        logger.info(
            f"[{request_id}] 请求开始: {request.method} {request.url.path} "
            f"- 客户端: {client_ip}"
        )

        # 处理请求
        response = await call_next(request)

        # 计算处理时间
        process_time = (time.time() - start_time) * 1000  # 转换为毫秒

        # 记录响应信息
        logger.info(
            f"[{request_id}] 请求完成: {request.method} {request.url.path} "
            f"- 状态: {response.status_code} - 耗时: {process_time:.2f}ms"
        )

        # 记录访问日志（包含结构化数据）
        log_access(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=process_time,
            ip=client_ip,
            user_agent=user_agent,
        )

        # 添加处理时间到响应头
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        response.headers["X-Request-ID"] = request_id

        return response

    # 注册全局异常处理器 - 统一错误响应格式
    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """HTTP 异常处理器 - 统一返回 message 字段"""
        # 认证类异常返回 401，其他返回原来的状态码
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.error(message=exc.detail, code=exc.status_code),
        )

    @application.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """全局异常处理器"""
        logger.error(f"未处理的异常: {exc}")
        error_log.error(
            f"未处理的异常 | 请求: {request.method} {request.url.path} | 异常: {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ApiResponse.error(message=str(exc) if settings.DEBUG else "服务器内部错误"),
        )

    @application.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """值错误处理器"""
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ApiResponse.error(message=str(exc)),
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
