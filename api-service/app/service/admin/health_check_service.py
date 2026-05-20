"""Proactive channel health checking service (admin domain).

Ported verbatim from `services/admin-service/src/services/health_check_service.py`
in Plan 05-02 / Task 3.  Rewrites applied:

- `from core.config import settings` →
  `from app.core.config import settings`
- `from core.enums import PoolAccountStatus` →
  `from app.model.enums import PoolAccountStatus`
- `from common.internal import get_internal_client` →
  `from app.common.internal import get_internal_client`
- `from models.pool import Pool, PoolAccount, PoolModel` →
  `from app.model.pool import Pool, PoolAccount, PoolModelConfig`
  (PoolModel→PoolModelConfig rename — Phase 3)
- `from repositories.pool_repository import PoolRepository` →
  `from app.repository.pool_repository import PoolRepository`
- `from services.pool_service import _extract_balance` →
  `from app.service.admin.pool_service import _extract_balance`
- `from common.utils.crypto import decrypt_api_key` →
  `from app.common.security.crypto import decrypt_api_key`
- `from common.redis import get_redis` →
  `from app.common.infra.redis import get_redis`

CONTEXT O-2/O-5 + plan architectural note: this service is invoked by an
ARQ cron job registered in `app/core/jobs.py`. The cron cadence
matches source `services/admin-service/src/core/jobs.py:66` —
`cron(minute={0, 10, 20, 30, 40, 50})` — and runs on the EXISTING api-service
ARQ worker (no separate worker process; 2h4g constraint).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.infra.redis import get_redis
from app.common.internal import get_internal_client
from app.common.security.crypto import decrypt_api_key
from app.core.config import settings
from app.model.enums import PoolAccountStatus
from app.model.pool import Pool, PoolAccount, PoolModelConfig
from app.repository.pool_repository import PoolRepository
from app.service.admin.pool_service import _extract_balance

logger = logging.getLogger(__name__)

HEALTH_KEY_PREFIX = "channel_health:"
HEALTH_TTL_SECONDS = 900


# Concurrency cap (CONTEXT 已解决的开放问题 O-5): keeps in-flight upstream
# probes to <= HEALTH_CHECK_CONCURRENCY at any time, ensuring the health
# check loop is bounded even when many accounts/models are configured.
HEALTH_CHECK_CONCURRENCY = 5


class HealthCheckService:
    """Proactive channel-health probing run by the ARQ cron worker."""

    @staticmethod
    async def run_health_checks(db: AsyncSession) -> None:
        repo = PoolRepository(db)
        pools, _ = await repo.list_pools(page=1, page_size=500)

        semaphore = asyncio.Semaphore(HEALTH_CHECK_CONCURRENCY)
        tasks: list[asyncio.Task] = []

        for pool in pools:
            if not pool.is_enabled:
                continue
            accounts = [
                a for a in (pool.accounts or [])
                if a.status in (PoolAccountStatus.ACTIVE, PoolAccountStatus.ERROR)
            ]
            for account in accounts:
                tasks.append(
                    asyncio.create_task(
                        HealthCheckService._check_with_limit(semaphore, db, pool, account)
                    )
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = sum(1 for r in results if r is False or isinstance(r, BaseException))
        await db.commit()
        logger.info("health check complete: checked=%d errors=%d", len(results), errors)

    @staticmethod
    async def _check_with_limit(
        sem: asyncio.Semaphore, db: AsyncSession, pool: Pool, account: PoolAccount,
    ) -> bool:
        async with sem:
            result = await HealthCheckService._check_account(db, pool, account)
            await asyncio.sleep(settings.HEALTH_CHECK_RATE_LIMIT_DELAY)
            return result

    @staticmethod
    async def _check_account(
        db: AsyncSession, pool: Pool, account: PoolAccount,
    ) -> bool:
        del db  # account/pool mutations stage on the shared session; commit
                # happens once at the top of `run_health_checks`.
        master_key = settings.PROVIDER_SECRET_MASTER_KEY
        enc = account.api_key_enc
        try:
            api_key = decrypt_api_key(
                enc["ciphertext"], enc["iv"], enc["tag"], master_key,
            )
        except Exception:
            logger.warning(
                "failed to decrypt key for %s/%s", pool.slug, account.name,
            )
            account.status = PoolAccountStatus.ERROR
            account.last_checked_at = datetime.now(UTC)
            return False

        balance_ok = True
        if pool.health_check_endpoint:
            balance_ok = await HealthCheckService._check_balance(pool, account, api_key)

        if settings.HEALTH_CHECK_LLM_PROBE_ENABLED and balance_ok:
            enabled_models = [m for m in (pool.models or []) if m.is_enabled]
            for model in enabled_models:
                await HealthCheckService._llm_probe(pool, account, model, api_key)
                await asyncio.sleep(settings.HEALTH_CHECK_RATE_LIMIT_DELAY)

        account.last_checked_at = datetime.now(UTC)
        return balance_ok

    @staticmethod
    async def _check_balance(
        pool: Pool, account: PoolAccount, api_key: str,
    ) -> bool:
        try:
            client = get_internal_client(
                pool.health_check_endpoint,
                timeout=settings.HEALTH_CHECK_TIMEOUT_SECONDS,
            )
            resp = await client.get(
                pool.health_check_endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            account.balance = _extract_balance(resp.json())
            if account.status == PoolAccountStatus.ERROR:
                account.status = PoolAccountStatus.ACTIVE
                logger.info(
                    "account %s/%s recovered via balance check",
                    pool.slug, account.name,
                )
            return True
        except Exception as exc:
            logger.warning(
                "balance check failed for %s/%s: %s",
                pool.slug, account.name, exc,
            )
            account.status = PoolAccountStatus.ERROR
            account.last_health_check_error = str(exc)[:500]
            return False

    @staticmethod
    async def _llm_probe(
        pool: Pool, account: PoolAccount, model: PoolModelConfig, api_key: str,
    ) -> None:
        channel_slug = f"{pool.slug}/{account.id}"
        t_start = asyncio.get_event_loop().time()

        try:
            client = get_internal_client(
                pool.base_url, timeout=settings.HEALTH_CHECK_TIMEOUT_SECONDS,
            )
            resp = await client.post(
                f"{pool.base_url.rstrip('/')}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model.upstream_model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": settings.HEALTH_CHECK_LLM_PROBE_MAX_TOKENS,
                },
            )
            latency_ms = int(
                (asyncio.get_event_loop().time() - t_start) * 1000
            )

            if resp.status_code == 200:
                await HealthCheckService._publish_health(
                    channel_slug, model.model_slug,
                    status="healthy", latency_ms=latency_ms, error=None,
                )
                if account.status == PoolAccountStatus.ERROR:
                    account.status = PoolAccountStatus.ACTIVE
                    account.last_health_check_error = None
                    logger.info(
                        "channel %s re-enabled after successful probe", channel_slug,
                    )
            else:
                error_msg = f"HTTP {resp.status_code}"
                await HealthCheckService._publish_health(
                    channel_slug, model.model_slug,
                    status="unhealthy", latency_ms=latency_ms, error=error_msg,
                )
                if resp.status_code in (401, 403):
                    account.status = PoolAccountStatus.ERROR
                    account.last_health_check_error = error_msg
        except Exception as exc:
            latency_ms = int(
                (asyncio.get_event_loop().time() - t_start) * 1000
            )
            await HealthCheckService._publish_health(
                channel_slug, model.model_slug,
                status="unhealthy",
                latency_ms=latency_ms,
                error=str(exc)[:200],
            )

    @staticmethod
    async def _publish_health(
        channel_slug: str, model_slug: str,
        *, status: str, latency_ms: int, error: str | None,
    ) -> None:
        try:
            redis = get_redis()
            key = f"{HEALTH_KEY_PREFIX}{channel_slug}:{model_slug}"
            value = json.dumps({
                "status": status,
                "last_check_time": datetime.now(UTC).isoformat(),
                "latency_ms": latency_ms,
                "error": error,
            })
            await redis.set(key, value, ex=HEALTH_TTL_SECONDS)
        except Exception:
            logger.debug("failed to publish health data to Redis", exc_info=True)


__all__ = ["HEALTH_CHECK_CONCURRENCY", "HEALTH_KEY_PREFIX", "HealthCheckService"]
