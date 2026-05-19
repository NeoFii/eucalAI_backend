"""Tests for `services/admin/routing_setting_service.py`.

Plan 05-02 / Task 2 behaviours covered:

- `test_validate_rejects_unavailable`: tier_N_model slug missing from
  pool coverage raises ValidationException.
- `test_validate_rejects_no_routing_slug`: tier_N_model slug exists in
  pools but no model catalog has that `routing_slug` ⇒ ValidationException.
- `test_resolve_for_internal_not_present` (Pitfall 4): the source
  method `resolve_for_internal` is intentionally NOT ported.
- `test_bump_version_increments_redis`: D-06 contract — `_bump_version`
  calls `redis.incr('routing_config:version')`.
- `test_bump_version_fail_open`: D-06 Redis errors are logged but do not
  propagate.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long",
)
os.environ.setdefault(
    "INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long",
)

import pytest  # noqa: E402

from api_service.common.core.exceptions import ValidationException  # noqa: E402
from api_service.services.admin.routing_setting_service import (  # noqa: E402
    ROUTING_CONFIG_VERSION_KEY,
    RoutingSettingService,
)


def test_resolve_for_internal_not_present():
    """Pitfall 4: `resolve_for_internal` must NOT be ported."""
    assert not hasattr(RoutingSettingService, "resolve_for_internal")


@pytest.mark.asyncio
async def test_bump_version_increments_redis():
    """D-06 contract: `_bump_version` runs `INCR routing_config:version`."""
    redis_mock = AsyncMock()
    redis_mock.incr = AsyncMock()

    with patch(
        "api_service.services.admin.routing_setting_service.get_cache_redis",
        return_value=redis_mock,
    ):
        await RoutingSettingService._bump_version()

    redis_mock.incr.assert_awaited_once_with(ROUTING_CONFIG_VERSION_KEY)


@pytest.mark.asyncio
async def test_bump_version_fail_open():
    """D-06 fail-open: Redis errors must be logged but not re-raised."""
    with patch(
        "api_service.services.admin.routing_setting_service.get_cache_redis",
        side_effect=RuntimeError("redis down"),
    ):
        # Must not raise.
        await RoutingSettingService._bump_version()


@pytest.mark.asyncio
async def test_validate_rejects_unavailable():
    """Validator rejects when the tier slug has no pool coverage."""
    db = AsyncMock()

    pool_repo = MagicMock()
    pool_repo.get_available_model_slugs = AsyncMock(return_value=[])

    with patch(
        "api_service.repositories.pool_repository.PoolRepository",
        return_value=pool_repo,
    ):
        with pytest.raises(ValidationException) as exc:
            await RoutingSettingService.validate_tier_model_coverage(
                db, [("tier_1_model", "missing-slug")],
            )
    assert "missing-slug" in str(exc.value)
    assert "号池" in str(exc.value)


@pytest.mark.asyncio
async def test_validate_rejects_no_routing_slug():
    """Validator rejects when the slug is in pools but lacks a catalog routing_slug."""
    db = AsyncMock()

    pool_repo = MagicMock()
    # Pool offers it, so first check passes.
    pool_repo.get_available_model_slugs = AsyncMock(
        return_value=[("pool-slug", "Pool One")],
    )
    catalog_repo = MagicMock()
    catalog_repo.get_routing_slugs_existing = AsyncMock(return_value=set())

    with patch(
        "api_service.repositories.pool_repository.PoolRepository",
        return_value=pool_repo,
    ), patch(
        "api_service.repositories.model_catalog_repository.ModelCatalogRepository",
        return_value=catalog_repo,
    ):
        with pytest.raises(ValidationException) as exc:
            await RoutingSettingService.validate_tier_model_coverage(
                db, [("tier_1_model", "pool-slug")],
            )
    assert "routing_slug" in str(exc.value) or "模型目录" in str(exc.value)


@pytest.mark.asyncio
async def test_validate_passes_when_both_layers_have_slug():
    """Both pool coverage AND catalog routing_slug present => no exception."""
    db = AsyncMock()

    pool_repo = MagicMock()
    pool_repo.get_available_model_slugs = AsyncMock(
        return_value=[("ok-slug", "Pool One")],
    )
    catalog_repo = MagicMock()
    catalog_repo.get_routing_slugs_existing = AsyncMock(return_value={"ok-slug"})

    with patch(
        "api_service.repositories.pool_repository.PoolRepository",
        return_value=pool_repo,
    ), patch(
        "api_service.repositories.model_catalog_repository.ModelCatalogRepository",
        return_value=catalog_repo,
    ):
        # Must not raise.
        await RoutingSettingService.validate_tier_model_coverage(
            db, [("tier_1_model", "ok-slug")],
        )


@pytest.mark.asyncio
async def test_validate_skips_non_tier_keys():
    """Non-tier-model keys are not validated by the tier-coverage check."""
    db = AsyncMock()

    # Repos must not be queried because the input has no tier-model keys.
    pool_repo = MagicMock()
    pool_repo.get_available_model_slugs = AsyncMock(
        side_effect=AssertionError("should not query pools"),
    )

    with patch(
        "api_service.repositories.pool_repository.PoolRepository",
        return_value=pool_repo,
    ):
        # Must not raise.
        await RoutingSettingService.validate_tier_model_coverage(
            db, [("router_alias", "auto"), ("weight_纠错", "1.0")],
        )
