"""
API V1 路由聚合
"""

from fastapi import APIRouter

from user.api.v1.endpoints import auth, news

# 创建 API 路由器
api_router = APIRouter(prefix="/api/v1")

# 注册认证端点
api_router.include_router(auth.router)

# 注册新闻端点
api_router.include_router(news.router)

# 后续可以在这里注册其他端点
# api_router.include_router(user.router, prefix="/users")
# api_router.include_router(session.router, prefix="/sessions")
