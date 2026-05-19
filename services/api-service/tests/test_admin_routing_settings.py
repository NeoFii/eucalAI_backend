"""Tests for `controllers/admin/routing_settings.py` + D-06 INCR contract.

Plan 05-02 / Task 2 behaviours covered (D-06):

- `test_update_bumps_version`: `update_setting` triggers exactly one
  INCR after the commit.
- `test_version_incremented_on_batch`: `batch_update` triggers exactly
  one INCR (not one per item).
"""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long",
)
os.environ.setdefault(
    "INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long",
)

import pytest  # noqa: E402

from api_service.services.admin.routing_setting_service import (  # noqa: E402
    RoutingSettingService,
)


def _setting(key: str = "router_alias", value: str = "auto", value_type: str = "string"):
    s = MagicMock()
    s.key = key
    s.value = value
    s.value_type = value_type
    s.group_name = "core"
    s.label = "Router alias"
    s.description = None
    s.sort_order = 0
    s.updated_at = datetime(2026, 1, 1)
    return s


@pytest.mark.asyncio
async def test_update_bumps_version(mock_super_admin):
    """D-06: a single `update_setting` call → exactly one INCR after commit."""
    db = AsyncMock()

    repo = MagicMock()
    repo.get_by_key = AsyncMock(return_value=_setting())
    repo.update_value = AsyncMock()

    with patch(
        "api_service.services.admin.routing_setting_service.RoutingSettingRepository",
        return_value=repo,
    ), patch(
        "api_service.services.admin.routing_setting_service.AdminAuditService.record",
        new_callable=AsyncMock,
    ), patch.object(
        RoutingSettingService, "_bump_version", new_callable=AsyncMock,
    ) as bump_mock:
        await RoutingSettingService.update_setting(
            db, "router_alias", "router_v2",
            actor_admin_id=mock_super_admin.id,
        )

    db.commit.assert_awaited_once()
    bump_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_version_incremented_on_batch(mock_super_admin):
    """D-06: `batch_update` runs INCR exactly once per request, not per item."""
    db = AsyncMock()

    settings_by_key = {
        "router_alias": _setting("router_alias", "auto"),
        "weight_纠错": _setting("weight_纠错", "1.0", value_type="float"),
        "tier_1_model": _setting("tier_1_model", "old-slug"),
    }

    async def _get_by_key(k):
        return settings_by_key[k]

    repo = MagicMock()
    repo.get_by_key = AsyncMock(side_effect=_get_by_key)
    repo.batch_update = AsyncMock()

    with patch(
        "api_service.services.admin.routing_setting_service.RoutingSettingRepository",
        return_value=repo,
    ), patch(
        "api_service.services.admin.routing_setting_service.AdminAuditService.record",
        new_callable=AsyncMock,
    ), patch.object(
        RoutingSettingService, "list_all", new_callable=AsyncMock,
        return_value={},
    ), patch.object(
        RoutingSettingService, "_bump_version", new_callable=AsyncMock,
    ) as bump_mock:
        items = [
            ("router_alias", "router_v2"),
            ("weight_纠错", "1.5"),
            ("tier_1_model", "new-slug"),
        ]
        await RoutingSettingService.batch_update(
            db, items, actor_admin_id=mock_super_admin.id,
        )

    db.commit.assert_awaited_once()
    bump_mock.assert_awaited_once()
