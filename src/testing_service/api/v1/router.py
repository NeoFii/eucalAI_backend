# -*- coding: utf-8 -*-
"""
Testing 鏈嶅姟 API 璺敱
"""

from fastapi import APIRouter

from testing_service.api.v1.endpoints import benchmark, internal_router, model_providers, models, providers, vendors

api_router = APIRouter(prefix="/api/v1", redirect_slashes=False)

# 娉ㄥ唽妯″瀷绠＄悊绔偣锛堝惈鍒嗙被瀛愯矾鐢?/models/categories锛?
api_router.include_router(models.router)

# 娉ㄥ唽鐮斿彂鍟嗙鐐癸紙渚涘墠绔?VendorFilter 浣跨敤锛?
api_router.include_router(vendors.router)

# 娉ㄥ唽鏈嶅姟鎻愪緵鍟嗙鐞嗙鐐?
api_router.include_router(providers.router)

# 娉ㄥ唽鎬ц兘娴嬭瘯绔偣
api_router.include_router(benchmark.router)

# 娉ㄥ唽妯″瀷鎶ヤ环绠＄悊绔偣锛堣蒋鍒犻櫎 /model-providers/{id}锛?
api_router.include_router(model_providers.router)
api_router.include_router(internal_router.router)
