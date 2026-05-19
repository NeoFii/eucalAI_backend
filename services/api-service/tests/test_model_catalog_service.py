"""Tests for `services/admin/model_catalog_service.py` — D-05 cache hook + soft-delete.

Plan 05-02 / Task 2 behaviours covered here:

- `test_create_vendor_invalidates_cache` (D-05): `create_vendor` triggers
  SCAN+DEL of `mc:*` keys AFTER `db.commit()`.
- `test_invalidates_on_all_writes` (D-05): every documented write method
  (`create_vendor`, `update_vendor`, `create_category`, `update_category`,
  `create_model`, `update_model`, `disable_model`) calls
  `_invalidate_cache` exactly once.
- `test_archive_soft_deletes`: `disable_model` (admin-side
  archive) sets `is_active = False` and never issues a DELETE.
- `test_invalidate_cache_swallows_redis_errors`: D-05 fail-open
  semantics — Redis exceptions are logged but do not propagate.
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

from api_service.services.admin.model_catalog_service import ModelCatalogService  # noqa: E402


def _make_async_iter(keys):
    """Build a factory that ignores its kwargs and returns an async iterator."""

    def _factory(*args, **kwargs):
        async def _gen():
            for key in keys:
                yield key

        return _gen()

    return _factory


def _vendor_record(slug: str = "openai"):
    v = MagicMock()
    v.id = 1
    v.slug = slug
    v.name = "OpenAI"
    v.logo_url = None
    v.is_active = True
    v.sort_order = 0
    v.created_at = datetime(2026, 1, 1)
    v.updated_at = datetime(2026, 1, 1)
    return v


def _category_record(key: str = "text"):
    c = MagicMock()
    c.id = 1
    c.key = key
    c.name = "Text"
    c.sort_order = 0
    c.is_active = True
    c.created_at = datetime(2026, 1, 1)
    c.updated_at = datetime(2026, 1, 1)
    return c


@pytest.mark.asyncio
async def test_invalidate_cache_calls_scan_and_delete():
    """_invalidate_cache SCANs `mc:*` and DELETEs every yielded key."""
    redis_mock = MagicMock()
    fake_keys = ["mc:vendors", "mc:categories", "mc:models:gpt-4o"]
    redis_mock.scan_iter = MagicMock(side_effect=_make_async_iter(fake_keys))
    redis_mock.delete = AsyncMock()

    with patch(
        "api_service.services.admin.model_catalog_service.get_cache_redis",
        return_value=redis_mock,
    ):
        await ModelCatalogService._invalidate_cache()

    redis_mock.scan_iter.assert_called_once_with(match="mc:*")
    assert redis_mock.delete.await_count == 3
    awaited_args = [c.args[0] for c in redis_mock.delete.await_args_list]
    assert awaited_args == fake_keys


@pytest.mark.asyncio
async def test_invalidate_cache_swallows_redis_errors():
    """D-05 fail-open: a Redis exception must be logged, not re-raised."""

    with patch(
        "api_service.services.admin.model_catalog_service.get_cache_redis",
        side_effect=RuntimeError("redis down"),
    ):
        # Must NOT raise.
        await ModelCatalogService._invalidate_cache()


@pytest.mark.asyncio
async def test_create_vendor_invalidates_cache(mock_super_admin):
    """T-5-CACHE-1: `create_vendor` invalidates `mc:*` after commit."""
    db = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    repo_mock = MagicMock()
    repo_mock.get_by_slug = AsyncMock(return_value=None)

    def _add(vendor):
        vendor.id = 10
        vendor.created_at = datetime(2026, 1, 1)
        vendor.updated_at = datetime(2026, 1, 1)

    repo_mock.add = MagicMock(side_effect=_add)

    with patch(
        "api_service.services.admin.model_catalog_service.ModelVendorRepository",
        return_value=repo_mock,
    ), patch(
        "api_service.services.admin.model_catalog_service.AdminAuditService.record",
        new_callable=AsyncMock,
    ), patch.object(
        ModelCatalogService, "_invalidate_cache", new_callable=AsyncMock,
    ) as invalidate_mock:
        from api_service.schemas.admin.model_catalog import ModelVendorCreate
        payload = ModelVendorCreate(slug="openai", name="OpenAI")
        await ModelCatalogService.create_vendor(
            db, payload, actor_admin_id=mock_super_admin.id,
        )

    invalidate_mock.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalidates_on_all_writes(mock_super_admin):
    """Every documented write method calls `_invalidate_cache` exactly once.

    Each scenario constructs minimal mocks for the repo + audit, calls the
    method, and asserts the invalidation hook fired exactly once after the
    commit returns.
    """
    from api_service.schemas.admin.model_catalog import (
        ModelCategoryCreate,
        ModelCategoryUpdate,
        ModelVendorCreate,
        ModelVendorUpdate,
    )

    async def _run_create_vendor():
        db = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        repo = MagicMock()
        repo.get_by_slug = AsyncMock(return_value=None)
        repo.add = MagicMock(side_effect=lambda v: setattr(v, "id", 1) or setattr(v, "created_at", datetime(2026, 1, 1)) or setattr(v, "updated_at", datetime(2026, 1, 1)))
        with patch(
            "api_service.services.admin.model_catalog_service.ModelVendorRepository",
            return_value=repo,
        ), patch(
            "api_service.services.admin.model_catalog_service.AdminAuditService.record",
            new_callable=AsyncMock,
        ), patch.object(
            ModelCatalogService, "_invalidate_cache", new_callable=AsyncMock,
        ) as inv:
            await ModelCatalogService.create_vendor(
                db, ModelVendorCreate(slug="v1", name="V One"),
                actor_admin_id=mock_super_admin.id,
            )
        return inv

    async def _run_update_vendor():
        db = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        repo = MagicMock()
        repo.get_by_slug = AsyncMock(return_value=_vendor_record())
        with patch(
            "api_service.services.admin.model_catalog_service.ModelVendorRepository",
            return_value=repo,
        ), patch(
            "api_service.services.admin.model_catalog_service.AdminAuditService.record",
            new_callable=AsyncMock,
        ), patch.object(
            ModelCatalogService, "_invalidate_cache", new_callable=AsyncMock,
        ) as inv:
            await ModelCatalogService.update_vendor(
                db, "openai", ModelVendorUpdate(name="OpenAI v2"),
                actor_admin_id=mock_super_admin.id,
            )
        return inv

    async def _run_create_category():
        db = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        repo = MagicMock()
        repo.get_by_key = AsyncMock(return_value=None)
        repo.add = MagicMock(side_effect=lambda c: setattr(c, "id", 1) or setattr(c, "created_at", datetime(2026, 1, 1)) or setattr(c, "updated_at", datetime(2026, 1, 1)))
        with patch(
            "api_service.services.admin.model_catalog_service.ModelCategoryRepository",
            return_value=repo,
        ), patch(
            "api_service.services.admin.model_catalog_service.AdminAuditService.record",
            new_callable=AsyncMock,
        ), patch.object(
            ModelCatalogService, "_invalidate_cache", new_callable=AsyncMock,
        ) as inv:
            await ModelCatalogService.create_category(
                db, ModelCategoryCreate(key="text", name="Text"),
                actor_admin_id=mock_super_admin.id,
            )
        return inv

    async def _run_update_category():
        db = AsyncMock()
        db.refresh = AsyncMock(side_effect=lambda obj: None)
        repo = MagicMock()
        repo.get_by_key = AsyncMock(return_value=_category_record())
        with patch(
            "api_service.services.admin.model_catalog_service.ModelCategoryRepository",
            return_value=repo,
        ), patch(
            "api_service.services.admin.model_catalog_service.AdminAuditService.record",
            new_callable=AsyncMock,
        ), patch.object(
            ModelCatalogService, "_invalidate_cache", new_callable=AsyncMock,
        ) as inv:
            await ModelCatalogService.update_category(
                db, "text", ModelCategoryUpdate(name="Text v2"),
                actor_admin_id=mock_super_admin.id,
            )
        return inv

    async def _run_disable_model():
        db = AsyncMock()
        model = MagicMock()
        model.is_active = True
        model.slug = "gpt-4o"
        repo = MagicMock()
        repo.get_by_slug = AsyncMock(return_value=model)
        with patch(
            "api_service.services.admin.model_catalog_service.ModelCatalogRepository",
            return_value=repo,
        ), patch(
            "api_service.services.admin.model_catalog_service.AdminAuditService.record",
            new_callable=AsyncMock,
        ), patch.object(
            ModelCatalogService, "_invalidate_cache", new_callable=AsyncMock,
        ) as inv:
            await ModelCatalogService.disable_model(
                db, "gpt-4o", actor_admin_id=mock_super_admin.id,
            )
        return inv

    scenarios = [
        ("create_vendor", _run_create_vendor),
        ("update_vendor", _run_update_vendor),
        ("create_category", _run_create_category),
        ("update_category", _run_update_category),
        ("disable_model", _run_disable_model),
    ]
    for name, runner in scenarios:
        inv_mock = await runner()
        assert inv_mock.await_count == 1, f"{name} did not invalidate cache exactly once"


@pytest.mark.asyncio
async def test_archive_soft_deletes(mock_super_admin):
    """`disable_model` (admin archive) sets is_active=False — soft delete."""
    db = AsyncMock()

    model = MagicMock()
    model.is_active = True
    model.slug = "gpt-4o"

    repo = MagicMock()
    repo.get_by_slug = AsyncMock(return_value=model)

    with patch(
        "api_service.services.admin.model_catalog_service.ModelCatalogRepository",
        return_value=repo,
    ), patch(
        "api_service.services.admin.model_catalog_service.AdminAuditService.record",
        new_callable=AsyncMock,
    ), patch.object(
        ModelCatalogService, "_invalidate_cache", new_callable=AsyncMock,
    ):
        await ModelCatalogService.disable_model(
            db, "gpt-4o", actor_admin_id=mock_super_admin.id,
        )

    # SOFT delete — is_active flipped, no DB.delete called.
    assert model.is_active is False
    db.delete.assert_not_called()
