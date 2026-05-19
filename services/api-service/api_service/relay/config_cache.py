"""RoutingConfigCache — per-worker singleton with Redis version poll.

Replaces HTTP polling of admin-service for routing configuration.
Admin writes trigger INCR routing_config:version (Phase 5 D-06),
and each worker detects the change on next request via GET.

Decisions: D-09 (version poll), D-10 (full dict), D-11 (normalize_runtime_config),
D-12 (startup must succeed), D-13 (per-worker independent cache).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api_service.common.security.crypto import decrypt_api_key
from api_service.core.config import settings
from api_service.models import (
    ModelCatalog,
    Pool,
    PoolAccount,
    PoolModelConfig,
    RoutingSetting,
)
from api_service.relay.runtime_config import normalize_runtime_config
from api_service.repositories.routing_setting_repository import RoutingSettingRepository

logger = logging.getLogger(__name__)

ROUTING_CONFIG_VERSION_KEY = "routing_config:version"


class RoutingConfigCache:
    """Per-worker singleton. Checks version on every request, reloads on mismatch."""

    def __init__(self, cache_redis: aioredis.Redis) -> None:
        self._redis = cache_redis
        self._cached_config: Dict[str, Any] | None = None
        self._version: int = 0

    async def start(self, db_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Load config from DB on startup. Must succeed or raise RuntimeError (D-12)."""
        config = await self._load_from_db(db_session_factory)
        if not config.get("model_channels") and not config.get("model_providers"):
            raise RuntimeError(
                "RoutingConfigCache: no routing config found in DB — cannot start"
            )
        self._cached_config = config
        # Read initial version from Redis
        try:
            v = await self._redis.get(ROUTING_CONFIG_VERSION_KEY)
            self._version = int(v) if v else 0
        except Exception:
            self._version = 0

    def load(self) -> Dict[str, Any]:
        """Synchronous read — called on every request."""
        if self._cached_config is None:
            raise RuntimeError("RoutingConfigCache not started")
        return self._cached_config

    async def check_and_reload(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Called at request start. GET version, reload if changed (D-09)."""
        try:
            v = await self._redis.get(ROUTING_CONFIG_VERSION_KEY)
            current = int(v) if v else 0
        except Exception:
            # Redis down -> use cached config (D-06 fail-open)
            return
        if current != self._version:
            config = await self._load_from_db(db_session_factory)
            self._cached_config = config
            self._version = current
            logger.info("routing config reloaded, version=%d", current)

    async def _load_from_db(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> Dict[str, Any]:
        """Load routing config from DB and normalize via normalize_runtime_config."""
        async with db_session_factory() as session:
            # 1. Load routing_settings key-value pairs
            repo = RoutingSettingRepository(session)
            all_settings = await repo.get_all()

            raw: Dict[str, Any] = {}
            for s in all_settings:
                if s.value_type == "float":
                    raw[s.key] = float(s.value)
                elif s.value_type == "int":
                    raw[s.key] = int(s.value)
                else:
                    raw[s.key] = s.value

            # 2. Build model_channels from pool/account/model data
            model_channels = await _build_model_channels(session)

            # 3. Build model_prices from model_catalog
            model_prices = await _build_model_prices(session)

        # 4. Construct the structure normalize_runtime_config expects
        config_input: Dict[str, Any] = {
            "router_alias": raw.get("router_alias", "auto"),
            "user_facing_aliases": _parse_aliases(raw.get("user_facing_aliases", "")),
            "route_order": ["纠错", "工具调用", "通用任务", "任务拆解", "编程"],
            "weights": {
                "纠错": raw.get("weight_纠错", 1.0),
                "工具调用": raw.get("weight_工具调用", 1.0),
                "通用任务": raw.get("weight_通用任务", 1.0),
                "任务拆解": raw.get("weight_任务拆解", 1.0),
                "编程": raw.get("weight_编程", 1.0),
            },
            "score_bands": raw.get("score_bands", "0-3:5,3-5:4,5-7:3,7-9:2,9-10:1"),
            "tier_model_map": {
                str(i): raw.get(f"tier_{i}_model", "") for i in range(1, 6)
            },
            "model_channels": model_channels,
            "model_prices": model_prices,
            "model_providers": {},
            "default_user_rpm": raw.get("default_user_rpm"),
            "system_rpm_cap": raw.get("system_rpm_cap"),
        }
        return normalize_runtime_config(config_input)


# ── Helper functions ─────────────────────────────────────────────────────────


def _parse_aliases(value: Any) -> list[str]:
    """Parse user_facing_aliases from DB string to list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [a.strip() for a in value.split(",") if a.strip()]
    return []


async def _build_model_channels(session: AsyncSession) -> Dict[str, list]:
    """Build model_channels dict from pool_model_configs + pool_accounts + pools.

    Groups by model_slug (the logical model name used for routing).
    Each channel entry contains all fields needed by ChannelSelector.
    """
    # Query active pools with their active accounts and enabled model configs
    stmt = (
        select(
            PoolModelConfig.model_slug,
            PoolModelConfig.upstream_model_id,
            PoolModelConfig.cost_input_per_million,
            PoolModelConfig.cost_output_per_million,
            PoolModelConfig.cost_cached_input_per_million,
            Pool.slug.label("pool_slug"),
            Pool.base_url,
            Pool.priority,
            Pool.weight.label("pool_weight"),
            PoolAccount.id.label("pool_account_id"),
            PoolAccount.api_key_enc,
            PoolAccount.rpm_limit,
            PoolAccount.tpm_limit,
            PoolAccount.weight.label("account_weight"),
        )
        .join(Pool, PoolModelConfig.pool_id == Pool.id)
        .join(PoolAccount, PoolAccount.pool_id == Pool.id)
        .where(
            Pool.is_enabled.is_(True),
            PoolModelConfig.is_enabled.is_(True),
            PoolAccount.status == 0,  # PoolAccountStatus.ACTIVE
        )
    )
    result = await session.execute(stmt)
    rows = result.all()

    master_key = settings.PROVIDER_SECRET_MASTER_KEY
    model_channels: Dict[str, list] = {}

    for row in rows:
        model_slug = row.model_slug
        # Decrypt API key from encrypted JSON
        enc = row.api_key_enc
        if isinstance(enc, dict) and master_key:
            try:
                api_key = decrypt_api_key(
                    enc["ciphertext"], enc["iv"], enc["tag"], master_key
                )
            except Exception:
                logger.warning(
                    "failed to decrypt api_key for pool_account %s, skipping",
                    row.pool_account_id,
                )
                continue
        else:
            # Cannot decrypt — skip this account
            continue

        channel_entry = {
            "channel_slug": f"{row.pool_slug}:{row.pool_account_id}",
            "provider_slug": row.pool_slug,
            "api_key": api_key,
            "api_base": row.base_url,
            "upstream_model": row.upstream_model_id,
            "priority": row.priority,
            "weight": row.account_weight or row.pool_weight or 1,
            "cost_input_per_million": row.cost_input_per_million or 0,
            "cost_output_per_million": row.cost_output_per_million or 0,
            "cost_cached_input_per_million": row.cost_cached_input_per_million or 0,
            "pool_account_id": row.pool_account_id,
            "rpm_limit": row.rpm_limit,
            "tpm_limit": row.tpm_limit,
        }

        if model_slug not in model_channels:
            model_channels[model_slug] = []
        model_channels[model_slug].append(channel_entry)

    return model_channels


async def _build_model_prices(session: AsyncSession) -> Dict[str, Dict[str, int]]:
    """Build model_prices dict from model_catalog (user-facing sale prices)."""
    stmt = select(
        ModelCatalog.routing_slug,
        ModelCatalog.sale_input_per_million,
        ModelCatalog.sale_output_per_million,
        ModelCatalog.sale_cached_input_per_million,
    ).where(
        ModelCatalog.is_active.is_(True),
        ModelCatalog.routing_slug.isnot(None),
    )
    result = await session.execute(stmt)
    rows = result.all()

    model_prices: Dict[str, Dict[str, int]] = {}
    for row in rows:
        if row.routing_slug:
            model_prices[row.routing_slug] = {
                "input": int(row.sale_input_per_million or 0),
                "output": int(row.sale_output_per_million or 0),
                "cached_input": int(row.sale_cached_input_per_million or 0),
            }
    return model_prices
