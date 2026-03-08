# -*- coding: utf-8 -*-
"""
Testing 服务性能测试任务
负责调度和执行基准测试
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from testing.models import ModelProvider, BenchmarkResult
from testing.benchmark.engine import BenchmarkEngine
from testing.services import ModelProviderService, BenchmarkService, ProviderService, ModelService

logger = logging.getLogger(__name__)


class BenchmarkTask:
    """
    性能测试任务
    负责执行和管理基准测试
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.engine = BenchmarkEngine()

    async def run_single_test(
        self,
        model_provider_id: int,
        api_key: Optional[str] = None,
        test_prompt: Optional[str] = None,
        timeout: int = 60,
    ) -> BenchmarkResult:
        """
        运行单个模型供应商的测试

        Args:
            model_provider_id: 模型供应商ID
            api_key: API 密钥（可选）
            test_prompt: 测试用的 prompt
            timeout: 超时时间

        Returns:
            测试结果
        """
        # 获取模型供应商配置
        mp = await ModelProviderService.get_by_id(self.db, model_provider_id)
        if not mp:
            raise ValueError(f"ModelProvider {model_provider_id} not found")

        # 获取供应商信息
        provider = await ProviderService.get_by_id(self.db, mp.provider_id)
        if not provider:
            raise ValueError(f"Provider {mp.provider_id} not found")

        # 获取模型信息
        model = await ModelService.get_by_id(self.db, mp.model_id)
        if not model:
            raise ValueError(f"Model {mp.model_id} not found")

        # 构建测试配置
        config = {
            "model": mp.api_model_name,
            "api_key": api_key,
            "provider": provider.provider_id,
            "rate_limit_rpm": mp.rate_limit_rpm,
            "prompt": test_prompt or "请用一句话介绍你自己",
            "timeout": timeout,
        }

        # 执行测试
        logger.info(f"Running benchmark for {provider.name}/{model.name}")
        result = await self.engine.run_benchmark(**config)

        # 保存结果
        if result["status"] == "success":
            benchmark_result = await BenchmarkService.create_result(
                db=self.db,
                model_provider_id=model_provider_id,
                latency_ttft=result.get("latency_ttft"),
                latency_total=result.get("latency_total"),
                throughput=result.get("throughput"),
                success_count=1,
                fail_count=0,
                test_prompt=config["prompt"],
            )
        else:
            # 记录失败
            benchmark_result = await BenchmarkService.create_result(
                db=self.db,
                model_provider_id=model_provider_id,
                latency_ttft=None,
                latency_total=result.get("latency_total"),
                throughput=None,
                success_count=0,
                fail_count=1,
                test_prompt=config["prompt"],
            )

        await self.db.commit()
        return benchmark_result

    async def run_batch(
        self,
        model_provider_ids: Optional[List[int]] = None,
        concurrency: int = 10,
        timeout: int = 60,
    ) -> List[BenchmarkResult]:
        """
        批量运行测试

        Args:
            model_provider_ids: 指定要测试的模型供应商ID列表（None 表示全部）
            concurrency: 并发数
            timeout: 超时时间

        Returns:
            测试结果列表
        """
        # 获取要测试的模型供应商
        if model_provider_ids:
            model_providers = []
            for mp_id in model_provider_ids:
                mp = await ModelProviderService.get_by_id(self.db, mp_id)
                if mp and mp.is_active:
                    model_providers.append(mp)
        else:
            model_providers = await ModelProviderService.list_active(self.db)

        if not model_providers:
            logger.warning("No active model providers to test")
            return []

        # 构建测试配置
        configs = []
        for mp in model_providers:
            provider = await ProviderService.get_by_id(self.db, mp.provider_id)
            if provider:
                configs.append({
                    "model_provider_id": mp.id,
                    "model": mp.api_model_name,
                    "provider": provider.provider_id,
                    "rate_limit_rpm": mp.rate_limit_rpm,
                    "timeout": timeout,
                })

        # 使用自适应并发执行
        results = await self.engine.run_adaptive_batch(configs)

        # 保存结果
        benchmark_results = []
        for i, result in enumerate(results):
            if i < len(model_providers):
                mp = model_providers[i]
                if result["status"] == "success":
                    benchmark_result = await BenchmarkService.create_result(
                        db=self.db,
                        model_provider_id=mp.id,
                        latency_ttft=result.get("latency_ttft"),
                        latency_total=result.get("latency_total"),
                        throughput=result.get("throughput"),
                        success_count=1,
                        fail_count=0,
                    )
                else:
                    benchmark_result = await BenchmarkService.create_result(
                        db=self.db,
                        model_provider_id=mp.id,
                        latency_ttft=None,
                        latency_total=result.get("latency_total"),
                        throughput=None,
                        success_count=0,
                        fail_count=1,
                    )
                benchmark_results.append(benchmark_result)

        await self.db.commit()
        return benchmark_results

    async def update_stats(self, model_provider_id: int) -> dict:
        """
        更新指定模型供应商的聚合统计数据

        Args:
            model_provider_id: 模型供应商ID

        Returns:
            更新后的统计数据
        """
        # 触发统计重新计算（实际上 get_stats 会实时计算）
        stats = await BenchmarkService.get_stats(self.db, model_provider_id)
        return stats


class BenchmarkScheduler:
    """
    基准测试调度器
    负责定时执行测试任务
    """

    def __init__(self, db_factory):
        """
        初始化调度器

        Args:
            db_factory: 数据库会话工厂
        """
        self.db_factory = db_factory

    async def run_scheduled_test(self):
        """运行定时测试任务"""
        async with self.db_factory() as db:
            task = BenchmarkTask(db)
            results = await task.run_batch()
            logger.info(f"Scheduled benchmark completed: {len(results)} tests run")
            return results

    async def cleanup_old_results(self, days: int = 7):
        """
        清理旧的测试结果

        Args:
            days: 保留天数
        """
        async with self.db_factory() as db:
            deleted = await BenchmarkService.cleanup_old_results(db, days)
            await db.commit()
            logger.info(f"Cleaned up {deleted} old benchmark results")
            return deleted
