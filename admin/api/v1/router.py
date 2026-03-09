"""
API V1 路由聚合
"""

from fastapi import APIRouter

from admin.api.v1.endpoints import auth, invitation, internal, news

# 创建 API 路由器
api_router = APIRouter(prefix="/api/v1")

# 注册认证端点
api_router.include_router(auth.router)

# 注册邀请码管理端点（包含仪表盘统计）
api_router.include_router(invitation.router)

# 注册新闻管理端点
api_router.include_router(news.router)

# 注册内部接口端点
api_router.include_router(internal.router)
