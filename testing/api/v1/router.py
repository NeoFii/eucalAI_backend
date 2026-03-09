# -*- coding: utf-8 -*-
"""
Testing 服务 API 路由
"""

from fastapi import APIRouter

from testing.api.v1.endpoints import models, vendors, providers, benchmark, model_providers

api_router = APIRouter(prefix="/api/v1", redirect_slashes=False)

# 注册模型管理端点（含分类子路由 /models/categories）
api_router.include_router(models.router)

# 注册研发商端点（供前端 VendorFilter 使用）
api_router.include_router(vendors.router)

# 注册服务提供商管理端点
api_router.include_router(providers.router)

# 注册性能测试端点
api_router.include_router(benchmark.router)

# 注册模型报价管理端点（软删除 /model-providers/{id}）
api_router.include_router(model_providers.router)
