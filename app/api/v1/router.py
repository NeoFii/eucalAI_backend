"""
API V1 路由聚合
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth

api_router = APIRouter()

# 注册各模块路由
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
