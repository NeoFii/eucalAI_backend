# -*- coding: utf-8 -*-
"""
Testing 服务性能探测任务
对 model_provider_offerings 发起真实 API 探测，将结果 append-only 写入 provider_performance_metrics
由 APScheduler 定时触发（或由管理接口手动触发）
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_service.benchmark.engine import BenchmarkEngine
from testing_service.models import ModelProviderOffering
from testing_service.catalog import ModelService
from testing_service.provider_config import OfferingService, PerformanceMetricService, ProviderService
from common.utils.timezone import now

logger = logging.getLogger(__name__)

DEFAULT_PROBE_PROMPT = "请用一句话介绍你自己。"
DEFAULT_PROBE_REGION = "cn-east"


class ProbeTask:
    """
    单次性能探测任务
    对指定 offering 发起探测并 append-only 写入 provider_performance_metrics
    """

    def __init__(self, db: AsyncSession, probe_region: str = DEFAULT_PROBE_REGION):
        self.db = db
        self.probe_region = probe_region
        self.engine = BenchmarkEngine()

    async def probe_offering(
        self,
        offering_id: int,
        api_key: Optional[str] = None,
        prompt: str = DEFAULT_PROBE_PROMPT,
        timeout: int = 60,
    ) -> None:
        """
        对单个报价发起探测，并 append-only 写入探测记录

        Args:
            offering_id: model_provider_offerings.id
            api_key: 探测用 API Key（可选，优先用报价自带配置）
            prompt: 探测用 prompt
            timeout: 超时秒数
        """
        result_row = await self.db.execute(
            select(ModelProviderOffering).where(ModelProviderOffering.id == offering_id)
        )
        offering = result_row.scalar_one_or_none()
        if not offering:
            logger.warning("报价 %d 不存在，跳过探测", offering_id)
            return

        provider = await ProviderService.get_by_id(self.db, offering.provider_id)
        model = await ModelService.get_by_id(self.db, offering.model_id)

        logger.info(
            "开始探测 offering=%d (%s / %s)",
            offering_id,
            provider.name if provider else "?",
            model.name if model else "?",
        )

        probe_result = await self.engine.run_benchmark(
            model=offering.provider_model_id or (model.slug if model else ""),
            api_key=api_key,
            api_base=offering.api_base_url or None,
            prompt=prompt,
            timeout=timeout,
        )

        measured_at = now()

        if probe_result["status"] == "success":
            # engine 返回秒，数据库存毫秒
            ttft_ms = int(probe_result["latency_ttft"] * 1000) if probe_result.get("latency_ttft") else None
            e2e_ms = int(probe_result["latency_total"] * 1000) if probe_result.get("latency_total") else None
            await PerformanceMetricService.record(
                db=self.db,
                offering_id=offering_id,
                success=True,
                measured_at=measured_at,
                throughput_tps=probe_result.get("throughput"),
                ttft_ms=ttft_ms,
                e2e_latency_ms=e2e_ms,
                output_tokens=probe_result.get("output_tokens"),
                probe_region=self.probe_region,
            )
        else:
            # 失败时取 error 前 50 字符作为 error_code
            error_msg = str(probe_result.get("error") or "unknown")
            error_code = error_msg[:50]
            await PerformanceMetricService.record(
                db=self.db,
                offering_id=offering_id,
                success=False,
                measured_at=measured_at,
                error_code=error_code,
                probe_region=self.probe_region,
            )

        await self.db.commit()
        logger.info("探测完成 offering=%d status=%s", offering_id, probe_result["status"])

    async def probe_all_active(self, prompt: str = DEFAULT_PROBE_PROMPT, timeout: int = 60) -> int:
        """
        对所有启用的报价发起探测
        Returns:
            完成探测的报价数量
        """
        offerings = await OfferingService.list_all_active(self.db)
        count = 0
        for offering in offerings:
            try:
                await self.probe_offering(offering.id, prompt=prompt, timeout=timeout)
                count += 1
            except Exception as exc:
                logger.error("探测 offering=%d 失败: %s", offering.id, exc)
        return count


class ProbeScheduler:
    """
    探测任务调度器（由 APScheduler 定时调用）
    """

    def __init__(self, db_factory):
        """
        Args:
            db_factory: 异步数据库会话工厂（async context manager）
        """
        self.db_factory = db_factory

    async def run_scheduled_probe(self, probe_region: str = DEFAULT_PROBE_REGION) -> int:
        """
        定时探测：对所有活跃报价发起探测，写入 provider_performance_metrics
        Returns:
            完成探测的报价数量
        """
        async with self.db_factory() as db:
            task = ProbeTask(db, probe_region=probe_region)
            count = await task.probe_all_active()
            logger.info("定时探测完成，共探测 %d 个报价", count)
            return count
