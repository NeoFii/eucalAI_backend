"""Integration tests: Admin config changes -> Redis version INCR -> RoutingConfigCache reload.

Verifies the full propagation pipeline:
  Admin write -> _bump_version() -> INCR routing_config:version
  -> RoutingConfigCache.check_and_reload() detects mismatch -> reloads from DB
  -> relay sees updated config

These tests use session_factory directly (not the transaction-rollback db_session)
because check_and_reload opens its own session. Data isolation is achieved via
explicit DELETE in finally blocks. Redis cleanup is handled by cache_redis fixture
(flushdb on teardown).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.infra.cache import get_cache_redis
from app.common.security.crypto import encrypt_api_key
from app.model import (
    ModelCatalog,
    ModelVendor,
    Pool,
    PoolAccount,
    PoolModelConfig,
    RoutingSetting,
)
from app.relay.config_cache import ROUTING_CONFIG_VERSION_KEY, RoutingConfigCache
from app.relay.dependencies import get_routing_config_cache
from app.service.admin.routing_setting_service import (
    ROUTING_CONFIG_VERSION_KEY as ADMIN_VERSION_KEY,
    RoutingSettingService,
)

MASTER_KEY_HEX = "a" * 64

pytestmark = pytest.mark.asyncio


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════


async def _seed_base_routing(session: AsyncSession) -> dict:
    """Insert minimal routing config (vendor + model + pool + account + pmc).

    Returns dict of created objects for reference and cleanup.
    """
    vendor = ModelVendor(
        id=9000,
        slug="openai-test",
        name="OpenAI Test",
        is_active=True,
        sort_order=0,
    )
    session.add(vendor)
    await session.flush()

    model = ModelCatalog(
        id=9001,
        slug="gpt-4o-mini-test",
        routing_slug="gpt-4o-mini",
        name="GPT-4o Mini Test",
        vendor_id=vendor.id,
        sale_input_per_million=150_000,
        sale_output_per_million=600_000,
        is_active=True,
        sort_order=0,
    )
    session.add(model)
    await session.flush()

    pool = Pool(
        id=9002,
        slug="test-pool-cache",
        name="Test Pool Cache",
        base_url="https://api.openai.com/v1",
        is_enabled=True,
        priority=10,
        weight=1,
    )
    session.add(pool)
    await session.flush()

    enc = encrypt_api_key("sk-fake-key-for-cache-test", MASTER_KEY_HEX)
    account = PoolAccount(
        id=9003,
        pool_id=pool.id,
        name="cache-test-account",
        api_key_enc=enc,
        mask="sk-f****st",
        balance=999_999_999,
        status=0,
        weight=1,
    )
    session.add(account)
    await session.flush()

    pmc = PoolModelConfig(
        id=9004,
        pool_id=pool.id,
        model_slug="gpt-4o-mini",
        upstream_model_id="gpt-4o-mini",
        cost_input_per_million=75_000,
        cost_output_per_million=300_000,
        is_enabled=True,
    )
    session.add(pmc)
    await session.flush()

    # Also seed a RoutingSetting row so normalize_runtime_config doesn't fail
    # on missing tier_model_map entries
    for tier in range(1, 6):
        rs = RoutingSetting(
            key=f"tier_{tier}_model",
            value="gpt-4o-mini",
            value_type="string",
            group_name="tier_model_map",
            label=f"Tier {tier} Model",
            sort_order=tier,
        )
        session.add(rs)
    await session.flush()
    await session.commit()

    return {
        "vendor": vendor,
        "model": model,
        "pool": pool,
        "account": account,
        "pmc": pmc,
    }


async def _cleanup_base_routing(session: AsyncSession) -> None:
    """Delete seeded routing data. Order matters for FK constraints."""
    from sqlalchemy import delete

    await session.execute(delete(PoolModelConfig).where(PoolModelConfig.id == 9004))
    await session.execute(delete(PoolAccount).where(PoolAccount.id == 9003))
    await session.execute(delete(Pool).where(Pool.id == 9002))
    await session.execute(delete(ModelCatalog).where(ModelCatalog.id == 9001))
    await session.execute(delete(ModelVendor).where(ModelVendor.id == 9000))
    await session.execute(
        delete(RoutingSetting).where(
            RoutingSetting.key.in_([f"tier_{i}_model" for i in range(1, 6)])
        )
    )
    await session.commit()


# ══════════════════════════════════════════════════════════════════════════════
# Test 1: Add model route propagates to cache
# ══════════════════════════════════════════════════════════════════════════════


async def test_add_model_route_propagates(session_factory, cache_redis):
    """D-15 scenario 1: Adding a new model route makes it visible in RoutingConfigCache."""
    config_cache = RoutingConfigCache(cache_redis)

    async with session_factory() as session:
        try:
            # Setup: seed base routing config
            await _seed_base_routing(session)

            # Start config cache — loads initial state
            await config_cache.start(session_factory)
            initial_config = config_cache.load()
            assert "gpt-4o-mini" in initial_config["model_channels"]

            # Action: Insert a new model + pool_model_config for "claude-3-haiku"
            new_model = ModelCatalog(
                id=9010,
                slug="claude-3-haiku-test",
                routing_slug="claude-3-haiku",
                name="Claude 3 Haiku Test",
                vendor_id=9000,
                sale_input_per_million=25_000,
                sale_output_per_million=125_000,
                is_active=True,
                sort_order=1,
            )
            session.add(new_model)
            await session.flush()

            new_pmc = PoolModelConfig(
                id=9011,
                pool_id=9002,
                model_slug="claude-3-haiku",
                upstream_model_id="claude-3-haiku-20240307",
                cost_input_per_million=12_500,
                cost_output_per_million=62_500,
                is_enabled=True,
            )
            session.add(new_pmc)
            await session.flush()
            await session.commit()

            # Bump Redis version (simulates what RoutingSettingService._bump_version does)
            await cache_redis.incr(ROUTING_CONFIG_VERSION_KEY)

            # Verify: check_and_reload detects version change and reloads
            await config_cache.check_and_reload(session_factory)
            updated_config = config_cache.load()
            assert "claude-3-haiku" in updated_config["model_channels"], (
                "New model route should appear in model_channels after cache reload"
            )

        finally:
            # Cleanup
            from sqlalchemy import delete

            await session.execute(delete(PoolModelConfig).where(PoolModelConfig.id == 9011))
            await session.execute(delete(ModelCatalog).where(ModelCatalog.id == 9010))
            await _cleanup_base_routing(session)
            await cache_redis.delete(ROUTING_CONFIG_VERSION_KEY)


# ══════════════════════════════════════════════════════════════════════════════
# Test 2: Disable channel propagates to cache
# ══════════════════════════════════════════════════════════════════════════════


async def test_disable_channel_propagates(session_factory, cache_redis):
    """D-15 scenario 2: Disabling a pool removes its channels from RoutingConfigCache."""
    config_cache = RoutingConfigCache(cache_redis)

    async with session_factory() as session:
        try:
            # Setup: seed base routing config
            await _seed_base_routing(session)

            # Start config cache
            await config_cache.start(session_factory)
            initial_config = config_cache.load()
            assert "gpt-4o-mini" in initial_config["model_channels"]
            assert len(initial_config["model_channels"]["gpt-4o-mini"]) > 0

            # Action: Disable the pool (is_enabled = False)
            pool = await session.get(Pool, 9002)
            pool.is_enabled = False
            await session.flush()
            await session.commit()

            # Bump Redis version
            await cache_redis.incr(ROUTING_CONFIG_VERSION_KEY)

            # Verify: cache reload should no longer include the disabled pool's channels
            await config_cache.check_and_reload(session_factory)
            updated_config = config_cache.load()

            # The model should either be absent from model_channels or have empty list
            gpt_channels = updated_config["model_channels"].get("gpt-4o-mini", [])
            assert len(gpt_channels) == 0, (
                "Disabled pool's channels should not appear in model_channels"
            )

        finally:
            # Restore pool state and cleanup
            pool_restore = await session.get(Pool, 9002)
            if pool_restore:
                pool_restore.is_enabled = True
                await session.flush()
            await _cleanup_base_routing(session)
            await cache_redis.delete(ROUTING_CONFIG_VERSION_KEY)


# ══════════════════════════════════════════════════════════════════════════════
# Test 3: Modify price propagates to cache
# ══════════════════════════════════════════════════════════════════════════════


async def test_modify_price_propagates(session_factory, cache_redis):
    """D-15 scenario 3: Modifying model price is reflected in RoutingConfigCache."""
    config_cache = RoutingConfigCache(cache_redis)

    async with session_factory() as session:
        try:
            # Setup: seed base routing config
            await _seed_base_routing(session)

            # Start config cache
            await config_cache.start(session_factory)
            initial_config = config_cache.load()
            original_price = initial_config["model_prices"]["gpt-4o-mini"]["input"]
            assert original_price == 150_000  # sale_input_per_million from seed

            # Action: Update the model's sale_input_per_million
            model = await session.get(ModelCatalog, 9001)
            model.sale_input_per_million = 200_000
            await session.flush()
            await session.commit()

            # Bump Redis version
            await cache_redis.incr(ROUTING_CONFIG_VERSION_KEY)

            # Verify: cache reload should reflect new price
            await config_cache.check_and_reload(session_factory)
            updated_config = config_cache.load()
            new_price = updated_config["model_prices"]["gpt-4o-mini"]["input"]
            assert new_price == 200_000, (
                f"Expected updated price 200000, got {new_price}"
            )

        finally:
            await _cleanup_base_routing(session)
            await cache_redis.delete(ROUTING_CONFIG_VERSION_KEY)


# ══════════════════════════════════════════════════════════════════════════════
# Test 4: No reload when version unchanged (T-09-05 mitigation)
# ══════════════════════════════════════════════════════════════════════════════


async def test_version_unchanged_no_reload(session_factory, cache_redis):
    """T-09-05: No unnecessary DB reload when Redis version is unchanged."""
    config_cache = RoutingConfigCache(cache_redis)

    async with session_factory() as session:
        try:
            # Setup
            await _seed_base_routing(session)
            await config_cache.start(session_factory)

            # Record version after start
            version_before = config_cache._version

            # Action: Do NOT bump Redis version, just call check_and_reload
            await config_cache.check_and_reload(session_factory)

            # Verify: version should remain the same (no reload triggered)
            assert config_cache._version == version_before, (
                "Version should not change when Redis version key is unchanged"
            )

        finally:
            await _cleanup_base_routing(session)
            await cache_redis.delete(ROUTING_CONFIG_VERSION_KEY)


# ══════════════════════════════════════════════════════════════════════════════
# Test 5: Redis version increment on admin write
# ══════════════════════════════════════════════════════════════════════════════


async def test_redis_version_increment_on_admin_write(cache_redis):
    """Verify RoutingSettingService._bump_version() increments the Redis key."""
    # Setup: ensure clean state
    await cache_redis.delete(ROUTING_CONFIG_VERSION_KEY)

    # Read initial version (should be None/0)
    initial = await cache_redis.get(ROUTING_CONFIG_VERSION_KEY)
    initial_val = int(initial) if initial else 0

    # Action: call _bump_version via module-level cache override
    from app.common.infra import cache as cache_module

    original = cache_module._cache_redis
    cache_module._cache_redis = cache_redis
    try:
        await RoutingSettingService._bump_version()
    finally:
        cache_module._cache_redis = original

    # Verify: version incremented by 1
    after = await cache_redis.get(ROUTING_CONFIG_VERSION_KEY)
    after_val = int(after) if after else 0
    assert after_val == initial_val + 1, (
        f"Expected version {initial_val + 1}, got {after_val}"
    )

    # Call again to verify it keeps incrementing
    cache_module._cache_redis = cache_redis
    try:
        await RoutingSettingService._bump_version()
    finally:
        cache_module._cache_redis = original

    final = await cache_redis.get(ROUTING_CONFIG_VERSION_KEY)
    final_val = int(final) if final else 0
    assert final_val == initial_val + 2, (
        f"Expected version {initial_val + 2}, got {final_val}"
    )

    # Cleanup
    await cache_redis.delete(ROUTING_CONFIG_VERSION_KEY)
