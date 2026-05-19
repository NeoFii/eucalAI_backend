"""Integration tests for `controllers/admin/model_catalog.py`.

Plan 05-02 / Task 2 behaviour:

- `test_create_vendor_invalidates_cache` (T-5-CACHE-1): POST
  `/api/v1/admin/model-catalog/vendors` ultimately triggers a SCAN+DEL of
  `mc:*` keys. The controller-side test verifies the service layer is
  invoked as expected.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long",
)
os.environ.setdefault(
    "INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long",
)

import pytest  # noqa: E402

from api_service.services.admin.model_catalog_service import ModelCatalogService  # noqa: E402


@pytest.mark.asyncio
async def test_create_vendor_invalidates_cache(mock_super_admin):
    """Direct service-layer call: D-05 invalidation runs after commit."""
    from datetime import datetime
    from unittest.mock import MagicMock

    db = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    repo = MagicMock()
    repo.get_by_slug = AsyncMock(return_value=None)

    def _add(v):
        v.id = 1
        v.created_at = datetime(2026, 1, 1)
        v.updated_at = datetime(2026, 1, 1)

    repo.add = MagicMock(side_effect=_add)

    invalidate_mock = AsyncMock()

    with patch(
        "api_service.services.admin.model_catalog_service.ModelVendorRepository",
        return_value=repo,
    ), patch(
        "api_service.services.admin.model_catalog_service.AdminAuditService.record",
        new_callable=AsyncMock,
    ), patch.object(
        ModelCatalogService, "_invalidate_cache", invalidate_mock,
    ):
        from api_service.schemas.admin.model_catalog import ModelVendorCreate
        await ModelCatalogService.create_vendor(
            db, ModelVendorCreate(slug="openai", name="OpenAI"),
            actor_admin_id=mock_super_admin.id,
        )

    invalidate_mock.assert_awaited_once()
    db.commit.assert_awaited_once()
