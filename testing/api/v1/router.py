# -*- coding: utf-8 -*-
"""
Testing 服务 API 路由
"""

from fastapi import APIRouter

from testing.api.v1.endpoints import models, providers, benchmark

api_router = APIRouter(prefix="/api/v1")

# 注册模型管理端点
api_router.include_router(models.router)

# 注册供应商管理端点
api_router.include_router(providers.router)

# 注册性能测试端点
api_router.include_router(benchmark.router)
