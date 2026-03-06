"""
用户服务 FastAPI 入口点
运行在端口 8000
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

from common.core.exceptions import (
    AuthenticationException,
    EmailAlreadyExistsException,
    EmailNotVerifiedException,
    InvalidCredentialsException,
    InvalidInvitationCodeException,
    InvalidTokenException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
    ServiceUnavailableException,
    SessionExpiredException,
    SessionNotFoundException,
    SessionRevokedException,
    TokenExpiredException,
    UserDisabledException,
    UserNotFoundException,
    WeakPasswordException,
)
from common.db import close_db, create_engine, init_db, init_session_factory
from common.utils.snowflake import configure_snowflake
from user.api import api_router
from user.config import settings

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

    启动时：
    1. 初始化雪花 ID 生成器
    2. 创建数据库引擎
    3. 初始化数据库表

    关闭时：
    1. 关闭数据库连接
    """
    # 启动
    logger.info("用户服务启动中...")

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

    logger.info(f"用户服务启动完成: http://0.0.0.0:{settings.PORT}")

    yield

    # 关闭
    logger.info("用户服务关闭中...")
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

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_hosts,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 异常处理器 ====================

@app.exception_handler(AuthenticationException)
async def authentication_exception_handler(request: Request, exc: AuthenticationException):
    """认证异常处理"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": 401, "message": exc.detail or "认证失败"},
    )


@app.exception_handler(InvalidCredentialsException)
async def invalid_credentials_exception_handler(request: Request, exc: InvalidCredentialsException):
    """无效凭证异常处理"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": 401, "message": exc.detail or "邮箱或密码错误"},
    )


@app.exception_handler(InvalidTokenException)
async def invalid_token_exception_handler(request: Request, exc: InvalidTokenException):
    """无效令牌异常处理"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": 401, "message": exc.detail or "无效的令牌"},
    )


@app.exception_handler(TokenExpiredException)
async def token_expired_exception_handler(request: Request, exc: TokenExpiredException):
    """令牌过期异常处理"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": 401, "message": exc.detail or "令牌已过期"},
    )


@app.exception_handler(SessionNotFoundException)
async def session_not_found_exception_handler(request: Request, exc: SessionNotFoundException):
    """会话不存在异常处理"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": 401, "message": exc.detail or "会话不存在"},
    )


@app.exception_handler(SessionExpiredException)
async def session_expired_exception_handler(request: Request, exc: SessionExpiredException):
    """会话过期异常处理"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": 401, "message": exc.detail or "会话已过期"},
    )


@app.exception_handler(SessionRevokedException)
async def session_revoked_exception_handler(request: Request, exc: SessionRevokedException):
    """会话已撤销异常处理"""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"code": 401, "message": exc.detail or "会话已被撤销"},
    )


@app.exception_handler(UserNotFoundException)
async def user_not_found_exception_handler(request: Request, exc: UserNotFoundException):
    """用户不存在异常处理"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"code": 404, "message": exc.detail or "用户不存在"},
    )


@app.exception_handler(UserDisabledException)
async def user_disabled_exception_handler(request: Request, exc: UserDisabledException):
    """用户被禁用异常处理"""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"code": 403, "message": exc.detail or "用户已被禁用"},
    )


@app.exception_handler(EmailNotVerifiedException)
async def email_not_verified_exception_handler(request: Request, exc: EmailNotVerifiedException):
    """邮箱未验证异常处理"""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"code": 403, "message": exc.detail or "邮箱未验证"},
    )


@app.exception_handler(EmailAlreadyExistsException)
async def email_already_exists_exception_handler(request: Request, exc: EmailAlreadyExistsException):
    """邮箱已存在异常处理"""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"code": 409, "message": exc.detail or "邮箱已被注册"},
    )


@app.exception_handler(WeakPasswordException)
async def weak_password_exception_handler(request: Request, exc: WeakPasswordException):
    """密码强度不足异常处理"""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"code": 400, "message": exc.detail or "密码强度不足"},
    )


@app.exception_handler(InvalidInvitationCodeException)
async def invalid_invitation_code_exception_handler(request: Request, exc: InvalidInvitationCodeException):
    """无效邀请码异常处理"""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"code": 400, "message": exc.detail or "无效的邀请码"},
    )


@app.exception_handler(InvitationCodeUsedException)
async def invitation_code_used_exception_handler(request: Request, exc: InvitationCodeUsedException):
    """邀请码已使用异常处理"""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"code": 400, "message": exc.detail or "邀请码已被使用"},
    )


@app.exception_handler(InvitationCodeDisabledException)
async def invitation_code_disabled_exception_handler(request: Request, exc: InvitationCodeDisabledException):
    """邀请码已禁用异常处理"""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"code": 400, "message": exc.detail or "邀请码已被禁用"},
    )


@app.exception_handler(InvitationCodeExpiredException)
async def invitation_code_expired_exception_handler(request: Request, exc: InvitationCodeExpiredException):
    """邀请码已过期异常处理"""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"code": 400, "message": exc.detail or "邀请码已过期"},
    )


@app.exception_handler(ServiceUnavailableException)
async def service_unavailable_exception_handler(request: Request, exc: ServiceUnavailableException):
    """服务不可用异常处理"""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"code": 503, "message": exc.detail or "服务暂时不可用"},
    )


# 注册 API 路由
app.include_router(api_router)


@app.get("/health", tags=["健康检查"])
async def health_check():
    """
    健康检查端点

    用于监控和负载均衡检查
    """
    return {"status": "healthy", "service": "user", "version": settings.VERSION}


@app.get("/", tags=["根路径"])
async def root():
    """
    根路径重定向到文档
    """
    return {
        "message": "Eucal AI 用户服务",
        "version": settings.VERSION,
        "docs": "/docs" if settings.DEBUG else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "user.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
