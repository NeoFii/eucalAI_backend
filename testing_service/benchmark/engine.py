# -*- coding: utf-8 -*-
"""Testing service benchmark engine."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

import litellm

from common.utils.openai_compat import normalize_openai_compatible_base_url

DEFAULT_BENCHMARK_PROMPT = "Please introduce yourself in one sentence."
DEFAULT_BENCHMARK_MAX_TOKENS = 96


class BenchmarkEngine:
    """Run streaming probes and normalize performance metrics."""

    def __init__(self):
        self._register_default_pricing()

    def _register_default_pricing(self):
        try:
            litellm.register_model(
                {
                    "default": {
                        "input_cost_per_token": 0.0000001,
                        "output_cost_per_token": 0.0000002,
                        "litellm_provider": "openai",
                        "mode": "chat",
                    }
                }
            )
        except Exception:
            pass

    async def run_benchmark(
        self,
        model: str,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        prompt: str = DEFAULT_BENCHMARK_PROMPT,
        timeout: int = 60,
        max_tokens: int = DEFAULT_BENCHMARK_MAX_TOKENS,
    ) -> Dict:
        start_time = time.time()
        result = {
            "model": model,
            "status": "pending",
            "latency_ttft": 0.0,
            "latency_total": 0.0,
            "throughput": 0.0,
            "cost": 0.0,
            "prompt_tokens": None,
            "output_tokens": 0,
            "timestamp": start_time,
            "error": None,
        }

        try:
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "timeout": timeout,
                "temperature": 0,
                "max_tokens": max_tokens,
                "stream_options": {"include_usage": True},
            }
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                normalized_api_base = normalize_openai_compatible_base_url(api_base)
                kwargs["api_base"] = normalized_api_base
                kwargs["base_url"] = normalized_api_base
                kwargs["custom_llm_provider"] = "openai"

            response = await litellm.acompletion(**kwargs)

            first_content_time: float | None = None
            usage = None
            collected_content: list[str] = []

            async for chunk in response:
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage:
                    usage = chunk_usage

                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue

                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue

                content = getattr(delta, "content", None) or ""
                reasoning_content = getattr(delta, "reasoning_content", None) or ""
                token_text = f"{content}{reasoning_content}"
                if token_text:
                    if first_content_time is None:
                        first_content_time = time.time()
                        result["latency_ttft"] = round(first_content_time - start_time, 4)
                    collected_content.append(token_text)

            end_time = time.time()
            result["latency_total"] = round(end_time - start_time, 4)
            full_response = "".join(collected_content)

            prompt_tokens = None
            output_tokens = None
            if usage:
                if isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens")
                    output_tokens = usage.get("completion_tokens")
                else:
                    prompt_tokens = getattr(usage, "prompt_tokens", None)
                    output_tokens = getattr(usage, "completion_tokens", None)

            if prompt_tokens is None or output_tokens is None:
                try:
                    prompt_tokens = len(litellm.encode(model=model, text=prompt))
                    output_tokens = len(litellm.encode(model=model, text=full_response))
                except Exception:
                    prompt_tokens = len(prompt) // 4
                    output_tokens = len(full_response) // 4

            result["prompt_tokens"] = prompt_tokens
            result["output_tokens"] = output_tokens

            generation_time = result["latency_total"] - result["latency_ttft"]
            if generation_time > 0 and output_tokens:
                result["throughput"] = round(output_tokens / generation_time, 2)

            try:
                cost = litellm.completion_cost(
                    model=model,
                    prompt=prompt,
                    completion=full_response,
                )
                result["cost"] = float(cost)
            except Exception:
                result["cost"] = 0.0

            result["status"] = "success"
            return result
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)
            result["latency_total"] = round(time.time() - start_time, 4)
            return result

    async def run_batch(
        self,
        configs: List[Dict],
        concurrency: int = 10,
    ) -> List[Dict]:
        sem = asyncio.Semaphore(concurrency)

        async def run_with_sem(config: Dict):
            async with sem:
                return await self.run_benchmark(
                    model=config.get("model"),
                    api_key=config.get("api_key"),
                    api_base=config.get("api_base"),
                    prompt=config.get("prompt", DEFAULT_BENCHMARK_PROMPT),
                    timeout=config.get("timeout", 60),
                    max_tokens=config.get("max_tokens", DEFAULT_BENCHMARK_MAX_TOKENS),
                )

        tasks = [run_with_sem(config) for config in configs]
        return await asyncio.gather(*tasks)

    async def run_adaptive_batch(
        self,
        configs: List[Dict],
        default_rate_limit: int = 60,
    ) -> List[Dict]:
        provider_configs: Dict[str, List[Dict]] = {}
        for config in configs:
            provider = config.get("provider", "default")
            provider_configs.setdefault(provider, []).append(config)

        results = []
        for _provider, provider_configs_list in provider_configs.items():
            rate_limit = provider_configs_list[0].get("rate_limit_rpm", default_rate_limit)
            concurrency = max(1, int(rate_limit * 0.8))
            provider_results = await self.run_batch(
                provider_configs_list,
                concurrency=concurrency,
            )
            results.extend(provider_results)
            await asyncio.sleep(1)

        return results
