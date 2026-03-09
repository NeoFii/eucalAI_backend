# -*- coding: utf-8 -*-
"""
Testing 服务基准测试引擎
从 ai_router 移植，用于测试模型性能
"""

import asyncio
import time
from typing import List, Dict, Optional

import litellm
from litellm import completion

from testing.core.cache import get_or_set, long_cache, short_cache


class BenchmarkEngine:
    """
    基准测试引擎
    用于测试各模型供应商的性能指标
    """

    def __init__(self):
        # 注册默认模型价格（可被数据库配置覆盖）
        self._register_default_pricing()

    def _register_default_pricing(self):
        """注册默认模型定价"""
        try:
            litellm.register_model({
                "default": {
                    "input_cost_per_token": 0.0000001,
                    "output_cost_per_token": 0.0000002,
                    "litellm_provider": "openai",
                    "mode": "chat"
                }
            })
        except Exception:
            pass  # 忽略重复注册错误

    async def run_benchmark(
        self,
        model: str,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        prompt: str = "请用一句话介绍你自己",
        timeout: int = 60,
    ) -> Dict:
        """
        运行单个模型的基准测试

        Args:
            model: 模型名称
            api_key: API 密钥
            api_base: API 基础地址
            prompt: 测试用的 prompt
            timeout: 超时时间（秒）

        Returns:
            包含性能指标的字典
        """
        start_time = time.time()
        result = {
            "model": model,
            "status": "pending",
            "latency_ttft": 0,
            "latency_total": 0,
            "throughput": 0,
            "cost": 0,
            "output_tokens": 0,
            "timestamp": start_time,
            "error": None,
        }

        try:
            # 准备参数
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "timeout": timeout,
            }

            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["api_base"] = api_base

            # 发起请求
            response = await litellm.acompletion(**kwargs)

            first_token_received = False
            first_token_time = 0
            collected_content = []

            # 处理流式响应
            async for chunk in response:
                if not first_token_received:
                    first_token_time = time.time()
                    result["latency_ttft"] = round(first_token_time - start_time, 4)
                    first_token_received = True

                content = chunk.choices[0].delta.content or ""
                collected_content.append(content)

            end_time = time.time()
            full_response = "".join(collected_content)

            # 计算指标
            total_duration = end_time - start_time
            result["latency_total"] = round(total_duration, 4)

            # 估算 token
            try:
                input_tokens = len(litellm.encode(model=model, text=prompt))
                output_tokens = len(litellm.encode(model=model, text=full_response))
            except Exception:
                # 如果估算失败，使用字符数除以4
                input_tokens = len(prompt) // 4
                output_tokens = len(full_response) // 4

            result["output_tokens"] = output_tokens

            # 计算吞吐量
            generation_time = total_duration - result["latency_ttft"]
            if generation_time > 0:
                result["throughput"] = round(output_tokens / generation_time, 2)

            # 计算成本
            try:
                cost = litellm.completion_cost(
                    completion_response=full_response,
                    model=model,
                    prompt=prompt,
                )
                result["cost"] = float(cost)
            except Exception:
                result["cost"] = 0

            result["status"] = "success"

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            result["latency_total"] = round(time.time() - start_time, 4)

        return result

    async def run_batch(
        self,
        configs: List[Dict],
        concurrency: int = 10,
    ) -> List[Dict]:
        """
        并行运行多个测试

        Args:
            configs: 测试配置列表，每个配置包含:
                - model: 模型名称
                - api_key: API 密钥（可选）
                - api_base: API 基础地址（可选）
                - prompt: 测试 prompt（可选）
                - timeout: 超时时间（可选）
            concurrency: 并发数

        Returns:
            测试结果列表
        """
        sem = asyncio.Semaphore(concurrency)

        async def run_with_sem(config: Dict):
            async with sem:
                return await self.run_benchmark(
                    model=config.get("model"),
                    api_key=config.get("api_key"),
                    api_base=config.get("api_base"),
                    prompt=config.get("prompt", "请用一句话介绍你自己"),
                    timeout=config.get("timeout", 60),
                )

        tasks = [run_with_sem(config) for config in configs]
        return await asyncio.gather(*tasks)

    async def run_adaptive_batch(
        self,
        configs: List[Dict],
        default_rate_limit: int = 60,
    ) -> List[Dict]:
        """
        自适应限速的批量测试

        根据每个供应商的 rate_limit_rpm 自动调整并发

        Args:
            configs: 测试配置列表
            default_rate_limit: 默认限速（每分钟请求数）

        Returns:
            测试结果列表
        """
        # 按供应商分组
        provider_configs: Dict[str, List[Dict]] = {}
        for config in configs:
            provider = config.get("provider", "default")
            if provider not in provider_configs:
                provider_configs[provider] = []
            provider_configs[provider].append(config)

        results = []

        # 对每个供应商依次执行（避免触发限速）
        for provider, provider_configs_list in provider_configs.items():
            rate_limit = provider_configs_list[0].get("rate_limit_rpm", default_rate_limit)
            # 计算合适的并发数（留20%余量）
            concurrency = max(1, int(rate_limit * 0.8))

            provider_results = await self.run_batch(
                provider_configs_list,
                concurrency=concurrency,
            )
            results.extend(provider_results)

            # 短暂等待，避免过快
            await asyncio.sleep(1)

        return results
