# -*- coding: utf-8 -*-
"""
Testing 服务性能测试端点
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing.api.dependencies import get_db_session
from testing.schemas import (
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BenchmarkStatsResponse,
    ListResponse,
)
from testing.services import (
    ModelProviderService,
    BenchmarkService,
)

router = APIRouter(prefix="/benchmark", tags=["性能测试"])


@router.get(
    "/stats/{model_provider_id}",
    response_model=BenchmarkStatsResponse,
    summary="获取性能统计",
    description="获取指定模型供应商的性能统计数据",
)
async def get_benchmark_stats(
    model_provider_id: int,
    hours: int = 24,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取性能统计数据"""
    mp = await ModelProviderService.get_by_id(db, model_provider_id)
    if not mp:
        return {"code": 404, "message": "模型供应商不存在"}

    stats = await BenchmarkService.get_stats(db, model_provider_id, hours)

    return stats


@router.post(
    "/run",
    response_model=BenchmarkRunResponse,
    summary="触发性能测试",
    description="触发性能测试任务",
)
async def run_benchmark(
    request: BenchmarkRunRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """触发性能测试"""
    # 获取需要测试的模型供应商
    if request.model_provider_ids:
        model_providers = []
        for mp_id in request.model_provider_ids:
            mp = await ModelProviderService.get_by_id(db, mp_id)
            if mp and mp.is_active:
                model_providers.append(mp)
    else:
        # 测试所有活跃的
        model_providers = await ModelProviderService.list_active(db)

    total = len(model_providers)

    # 生成任务ID
    task_id = str(uuid.uuid4())

    # TODO: 实际执行测试任务（后台异步执行）
    # 这里先返回任务ID，实际测试逻辑在 benchmark/tasks.py 中实现

    return {
        "task_id": task_id,
        "status": "submitted",
        "total": total,
        "submitted": total,
    }
