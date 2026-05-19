"""Tests for admin voucher endpoints (Plan 05-03 Task 2).

Validates:
- test_generate_batch: POST generates codes via VoucherService.generate_codes
- test_disable: DELETE disables via VoucherService.disable + audit
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api_service.main import app


@pytest.fixture
def mock_super_admin_obj():
    from api_service.models.enums import AdminRole, AdminStatus

    admin = MagicMock()
    admin.id = 2
    admin.uid = "adm_super1"
    admin.role = AdminRole.SUPER_ADMIN
    admin.status = AdminStatus.ACTIVE
    admin.is_root = True
    return admin


@pytest.mark.asyncio
async def test_generate_batch(mock_super_admin_obj):
    """POST /api/v1/admin/vouchers generates codes via VoucherService.generate_codes."""
    from api_service.core.policies import require_super_admin
    from api_service.core.db import get_db

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    app.dependency_overrides[require_super_admin] = lambda: mock_super_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock generated code objects
    mock_code = MagicMock()
    mock_code.code = "ABCD1234EFGH"
    mock_code.record = MagicMock()
    mock_code.record.id = 1

    with patch(
        "api_service.services.admin.voucher_service.VoucherService"
    ) as MockVoucher, patch(
        "api_service.controllers.admin.vouchers.AdminAuditService"
    ) as MockAudit:
        MockVoucher.generate_codes = AsyncMock(return_value=[mock_code])
        MockAudit.record = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/admin/vouchers",
                json={
                    "amount": 1000000,
                    "count": 1,
                    "starts_at": "2026-06-01T00:00:00+08:00",
                    "expires_at": "2026-12-31T23:59:59+08:00",
                    "remark": "test batch",
                },
            )

        assert resp.status_code == 200
        # VoucherService.generate_codes was called
        MockVoucher.generate_codes.assert_awaited_once()
        # Audit was recorded with correct action
        MockAudit.record.assert_awaited_once()
        audit_kwargs = MockAudit.record.call_args[1]
        assert audit_kwargs["action"] == "generate_voucher_codes"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_disable(mock_super_admin_obj):
    """DELETE /api/v1/admin/vouchers/{code_id} disables via VoucherService.disable."""
    from api_service.core.policies import require_super_admin
    from api_service.core.db import get_db

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    app.dependency_overrides[require_super_admin] = lambda: mock_super_admin_obj
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_disabled_code = MagicMock()
    mock_disabled_code.id = 42
    mock_disabled_code.status = 2

    with patch(
        "api_service.services.admin.voucher_service.VoucherService"
    ) as MockVoucher, patch(
        "api_service.controllers.admin.vouchers.AdminAuditService"
    ) as MockAudit:
        MockVoucher.disable = AsyncMock(return_value=mock_disabled_code)
        MockAudit.record = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/api/v1/admin/vouchers/42")

        assert resp.status_code == 200
        # VoucherService.disable was called
        MockVoucher.disable.assert_awaited_once()
        # Audit was recorded
        MockAudit.record.assert_awaited_once()
        audit_kwargs = MockAudit.record.call_args[1]
        assert audit_kwargs["action"] == "disable_voucher_code"
        assert audit_kwargs["resource_id"] == "42"

    app.dependency_overrides.clear()
