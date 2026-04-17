# -*- coding: utf-8 -*-
"""Low-level probe execution that can write to different sinks."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils.crypto import decrypt_api_key
from common.utils.timezone import now
from testing_service.benchmark.engine import (
    DEFAULT_BENCHMARK_MAX_TOKENS,
    DEFAULT_BENCHMARK_PROMPT,
    BenchmarkEngine,
)
from testing_service.benchmark.jobs import ProbeExecutionResult
from testing_service.config import get_settings
from testing_service.models import ModelProviderOffering
from testing_service.provider_config import PerformanceMetricService, ProviderService

logger = logging.getLogger(__name__)


class ProbeRunner:
    """Run one offering probe and return a normalized result."""

    def __init__(self, db: AsyncSession, probe_region: str):
        self.db = db
        self.probe_region = probe_region
        self.engine = BenchmarkEngine()

    async def execute(
        self,
        offering_id: int,
        prompt: str = DEFAULT_BENCHMARK_PROMPT,
        timeout: int = 60,
    ) -> ProbeExecutionResult:
        started_at = now()
        result = await self.db.execute(
            select(ModelProviderOffering).where(ModelProviderOffering.id == offering_id)
        )
        offering = result.scalar_one_or_none()
        if offering is None:
            return ProbeExecutionResult(
                offering_id=offering_id,
                model_id=None,
                provider_id=None,
                success=False,
                error_code="offering_not_found",
                throughput_tps=None,
                ttft_ms=None,
                e2e_latency_ms=None,
                prompt_tokens=None,
                output_tokens=None,
                probe_region=self.probe_region,
                started_at=started_at,
                finished_at=now(),
            )

        provider = await ProviderService.get_by_id(self.db, offering.provider_id)
        validation_error = self._validate_inputs(offering, provider)
        if validation_error:
            return ProbeExecutionResult(
                offering_id=offering.id,
                model_id=offering.model_id,
                provider_id=offering.provider_id,
                success=False,
                error_code=validation_error,
                throughput_tps=None,
                ttft_ms=None,
                e2e_latency_ms=None,
                prompt_tokens=None,
                output_tokens=None,
                probe_region=self.probe_region,
                started_at=started_at,
                finished_at=now(),
            )

        api_base = provider.probe_api_base_url if provider and provider.probe_api_base_url else offering.api_base_url
        try:
            api_key = decrypt_api_key(
                provider.probe_api_key_ciphertext,
                provider.probe_api_key_iv,
                provider.probe_api_key_tag,
                get_settings().testing_secret_master_key,
            )
        except Exception:
            logger.error("Failed to decrypt probe API key for offering=%s", offering_id)
            return ProbeExecutionResult(
                offering_id=offering.id,
                model_id=offering.model_id,
                provider_id=offering.provider_id,
                success=False,
                error_code="key_decrypt_error",
                throughput_tps=None,
                ttft_ms=None,
                e2e_latency_ms=None,
                prompt_tokens=None,
                output_tokens=None,
                probe_region=self.probe_region,
                started_at=started_at,
                finished_at=now(),
            )

        benchmark_result = await self.engine.run_benchmark(
            model=offering.provider_model_name,
            api_key=api_key,
            api_base=api_base,
            prompt=prompt,
            timeout=timeout,
            max_tokens=DEFAULT_BENCHMARK_MAX_TOKENS,
        )
        finished_at = now()
        if benchmark_result["status"] == "success":
            return ProbeExecutionResult(
                offering_id=offering.id,
                model_id=offering.model_id,
                provider_id=offering.provider_id,
                success=True,
                error_code=None,
                throughput_tps=benchmark_result.get("throughput"),
                ttft_ms=int(benchmark_result["latency_ttft"] * 1000) if benchmark_result.get("latency_ttft") else None,
                e2e_latency_ms=int(benchmark_result["latency_total"] * 1000) if benchmark_result.get("latency_total") else None,
                prompt_tokens=benchmark_result.get("prompt_tokens"),
                output_tokens=benchmark_result.get("output_tokens"),
                probe_region=self.probe_region,
                started_at=started_at,
                finished_at=finished_at,
            )

        error_text = str(benchmark_result.get("error") or "unknown")
        return ProbeExecutionResult(
            offering_id=offering.id,
            model_id=offering.model_id,
            provider_id=offering.provider_id,
            success=False,
            error_code=error_text[:128],
            throughput_tps=None,
            ttft_ms=None,
            e2e_latency_ms=None,
            prompt_tokens=benchmark_result.get("prompt_tokens"),
            output_tokens=benchmark_result.get("output_tokens"),
            probe_region=self.probe_region,
            started_at=started_at,
            finished_at=finished_at,
        )

    async def persist_performance_metric(self, result: ProbeExecutionResult):
        metric = await PerformanceMetricService.record(
            db=self.db,
            offering_id=result.offering_id,
            success=result.success,
            measured_at=result.finished_at or now(),
            throughput_tps=result.throughput_tps,
            ttft_ms=result.ttft_ms,
            e2e_latency_ms=result.e2e_latency_ms,
            error_code=result.error_code,
            prompt_tokens=result.prompt_tokens,
            output_tokens=result.output_tokens,
            probe_region=result.probe_region,
        )
        await self.db.commit()
        return metric

    @staticmethod
    def _validate_inputs(offering: ModelProviderOffering, provider) -> Optional[str]:
        if not offering.provider_model_name:
            return "model_mapping_missing"
        api_base = provider.probe_api_base_url if provider else None
        if not api_base and not offering.api_base_url:
            return "base_url_missing"
        if not provider or not provider.probe_api_key_ciphertext:
            return "missing_api_key"
        if not get_settings().testing_secret_master_key:
            return "secret_key_missing"
        return None
