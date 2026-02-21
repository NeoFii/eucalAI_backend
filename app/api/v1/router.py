"""
API V1 路由聚合
"""

from fastapi import APIRouter

from app.api.v1.endpoints import contact, news, products

api_router = APIRouter()

# 注册各模块路由
api_router.include_router(news.router, prefix="/news", tags=["新闻"])
api_router.include_router(products.router, prefix="/products", tags=["产品"])
api_router.include_router(contact.router, prefix="/contact", tags=["联系"])
