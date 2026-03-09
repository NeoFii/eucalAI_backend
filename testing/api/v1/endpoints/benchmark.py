# -*- coding: utf-8 -*-
"""
Testing 服务性能探测摘要端点
提供所有活跃报价的性能统计汇总，供前端性能对比页使用
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from testing.api.dependencies import get_db_session
from testing.services import OfferingService, ModelService

router = APIRouter(prefix="/benchmark", tags=["性能统计"])


@router.get(
    "/stats/summary",
    summary="获取所有报价的性能统计汇总",
    description="按模型分组，返回每个活跃报价近 N 次探测的性能均值",
)
async def get_benchmark_stats_summary(
    n: int = Query(5, description="取最近 N 次成功探测计算均值"),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    返回结构：
    {
      "items": [
        {
          "model_slug": "gpt-4o",
          "model_name": "GPT-4o",
          "vendor_name": "OpenAI",
          "offerings": [
            {
              "offering_id": 1,
              "provider_name": "OpenRouter",
              "provider_slug": "openrouter",
              "metrics": { "avg_throughput_tps": ..., "avg_ttft_ms": ..., "sample_count": ... }
            }
          ]
        }
      ],
      "total": 3
    }
    """
    offerings = await OfferingService.list_all_active(db)

    # 按 model_id 分组
    model_map: dict = {}
    for offering in offerings:
        model_id = offering.model_id
        if model_id not in model_map:
            model = await ModelService.get_by_id(db, model_id)
            if not model:
                continue
            model_map[model_id] = {
                "model_slug": model.slug,
                "model_name": model.name,
                "vendor_name": model.vendor.name if model.vendor else "",
                "offerings": [],
            }

        # 获取该报价近 N 次探测的性能均值
        metrics_list = await OfferingService.get_metrics(db, offering.id, n=n)
        metrics_data = None
        if metrics_list:
            m = metrics_list[0]
            metrics_data = {
                "avg_throughput_tps": m.avg_throughput_tps,
                "avg_ttft_ms": m.avg_ttft_ms,
                "avg_e2e_latency_ms": m.avg_e2e_latency_ms,
                "sample_count": m.sample_count,
                "last_measured_at": m.last_measured_at.isoformat() if m.last_measured_at else None,
            }

        provider = offering.provider
        model_map[model_id]["offerings"].append({
            "offering_id": offering.id,
            "provider_name": provider.name if provider else "Unknown",
            "provider_slug": provider.slug if provider else "",
            "metrics": metrics_data,
        })

    items = list(model_map.values())
    return {"items": items, "total": len(items)}
