"""Integration tests for `services/admin/pool_service.py`.

Plan 05-02 / Task 1 behaviours covered:

- `test_create_encrypts_key` (T-5-05): `add_pool_account` calls
  `encrypt_api_key` with the plaintext and never persists the plaintext to
  `PoolAccount.api_key_enc`.
- `test_add_model`: `add_pool_model` calls `PoolRepository.model_config_add`
  with the correct fields.
- `test_check_balances`: `check_balances` decrypts the stored ciphertext for
  each active account, awaits `get_internal_client(...).get(...)`, and
  returns micro-yuan integers via `_extract_balance`.

These exercise the service layer directly (not via FastAPI). Mocking strategy
mirrors Plan 05-01 `test_admin_auth.py`: AsyncMock the DB session + repository
class so we never touch a real engine.
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
# 64-hex master key for AES-256-GCM (32 bytes). Plain-text dummy is fine for
# tests because we patch `encrypt_api_key` to assert call shape, not crypto.
os.environ.setdefault(
    "PROVIDER_SECRET_MASTER_KEY", "0" * 64,
)

import pytest  # noqa: E402

from api_service.models.enums import PoolAccountStatus  # noqa: E402
from api_service.schemas.admin.pool import (  # noqa: E402
    PoolAccountCreate,
    PoolModelCreate,
)
from api_service.services.admin.pool_service import PoolService  # noqa: E402


def _make_pool(slug: str = "p1", *, accounts=None, models=None, health_endpoint=None):
    """Build a stand-in `Pool` ORM-like object for the service tests."""
    pool = MagicMock()
    pool.id = 100
    pool.slug = slug
    pool.name = "Pool One"
    pool.base_url = "https://upstream.example.com"
    pool.is_enabled = True
    pool.priority = 0
    pool.weight = 1
    pool.health_check_endpoint = health_endpoint
    pool.remark = None
    pool.models = models or []
    pool.accounts = accounts or []
    pool.created_at = datetime(2026, 1, 1)
    pool.updated_at = datetime(2026, 1, 1)
    return pool


@pytest.mark.asyncio
async def test_create_encrypts_key(mock_super_admin):
    """T-5-05: `add_pool_account` encrypts the plaintext API key and
    persists ONLY the ciphertext to `PoolAccount.api_key_enc`."""
    db = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    pool = _make_pool()
    repo_mock = MagicMock()
    repo_mock.get_by_slug = AsyncMock(return_value=pool)
    captured_account = {}

    def _account_add(account):
        # Stash the ORM instance so we can assert what got persisted.
        captured_account["obj"] = account
        # Mimic SnowflakeId allocation + column defaults (DB-side defaults
        # are not applied until flush; tests need explicit values so the
        # response serializer can populate non-nullable fields).
        account.id = 999
        account.created_at = datetime(2026, 1, 1)
        account.updated_at = datetime(2026, 1, 1)
        account.last_checked_at = None
        if account.status is None:
            account.status = int(PoolAccountStatus.ACTIVE)
        if account.balance is None:
            account.balance = 0
        if account.weight is None:
            account.weight = 1

    repo_mock.account_add = MagicMock(side_effect=_account_add)

    # Patch encrypt_api_key to assert call shape AND return a sentinel that
    # is provably NOT the plaintext.
    sentinel_ciphertext = {
        "ciphertext": "BASE64_CT",
        "iv": "BASE64_IV",
        "tag": "BASE64_TAG",
        "key_version": 1,
    }

    with patch(
        "api_service.services.admin.pool_service.PoolRepository",
        return_value=repo_mock,
    ), patch(
        "api_service.services.admin.pool_service.encrypt_api_key",
        return_value=sentinel_ciphertext,
    ) as enc_mock, patch(
        "api_service.services.admin.pool_service.mask_api_key",
        return_value="sk-l****-key",
    ), patch(
        "api_service.services.admin.pool_service.AdminAuditService.record_auto",
        new_callable=AsyncMock,
    ):
        payload = PoolAccountCreate(
            name="acct1",
            api_key="sk-live-secret-key-123",
            balance=0,
        )
        await PoolService.add_pool_account(
            db, "p1", payload, actor_admin_id=mock_super_admin.id,
        )

    # encrypt_api_key was called with the PLAINTEXT (T-5-05a).
    enc_mock.assert_called_once()
    args, _kwargs = enc_mock.call_args
    assert args[0] == "sk-live-secret-key-123"

    # The PoolAccount that hit the repo carries the CIPHERTEXT, never the plaintext.
    account = captured_account["obj"]
    assert account.api_key_enc == sentinel_ciphertext
    # Defensive: serialise the persisted value and assert no leakage of the plaintext.
    assert "sk-live-secret-key-123" not in str(account.api_key_enc)
    assert account.mask == "sk-l****-key"


@pytest.mark.asyncio
async def test_add_model(mock_super_admin):
    """`add_pool_model` calls `PoolRepository.model_config_add` with the right fields."""
    db = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    pool = _make_pool()
    repo_mock = MagicMock()
    repo_mock.get_by_slug = AsyncMock(return_value=pool)
    repo_mock.model_config_get_by_pool_and_model = AsyncMock(return_value=None)

    captured = {}

    def _config_add(pm):
        captured["pm"] = pm
        pm.id = 555
        pm.is_enabled = True

    repo_mock.model_config_add = MagicMock(side_effect=_config_add)

    with patch(
        "api_service.services.admin.pool_service.PoolRepository",
        return_value=repo_mock,
    ), patch(
        "api_service.services.admin.pool_service.AdminAuditService.record_auto",
        new_callable=AsyncMock,
    ):
        payload = PoolModelCreate(
            model_slug="gpt-4o-mini",
            upstream_model_id="gpt-4o-mini-2024-07-18",
            cost_input_per_million=150_000,
            cost_output_per_million=600_000,
        )
        item = await PoolService.add_pool_model(
            db, "p1", payload, actor_admin_id=mock_super_admin.id,
        )

    repo_mock.model_config_add.assert_called_once()
    pm = captured["pm"]
    assert pm.pool_id == pool.id
    assert pm.model_slug == "gpt-4o-mini"
    assert pm.upstream_model_id == "gpt-4o-mini-2024-07-18"
    assert pm.cost_input_per_million == 150_000
    assert pm.cost_output_per_million == 600_000
    assert item.model_slug == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_check_balances(mock_super_admin):
    """`check_balances` decrypts api_key_enc, awaits internal client, returns balance."""
    db = AsyncMock()

    account = MagicMock()
    account.id = 1
    account.name = "acct-1"
    account.status = PoolAccountStatus.ACTIVE
    account.balance = 0
    account.api_key_enc = {
        "ciphertext": "CT_B64", "iv": "IV_B64", "tag": "TAG_B64", "key_version": 1,
    }
    account.last_checked_at = None

    pool = _make_pool(
        accounts=[account], health_endpoint="https://upstream.example.com/v1/balance",
    )

    repo_mock = MagicMock()
    repo_mock.get_by_slug = AsyncMock(return_value=pool)

    # Fake response carrying total_remain=12.34 -> 12_340_000 micro-yuan.
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"data": {"total_remain": 12.34}})

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=fake_resp)

    with patch(
        "api_service.services.admin.pool_service.PoolRepository",
        return_value=repo_mock,
    ), patch(
        "api_service.services.admin.pool_service.decrypt_api_key",
        return_value="sk-decrypted-key",
    ) as dec_mock, patch(
        "api_service.services.admin.pool_service.get_internal_client",
        return_value=fake_client,
    ) as client_mock, patch(
        "api_service.services.admin.pool_service.AdminAuditService.record_auto",
        new_callable=AsyncMock,
    ):
        result = await PoolService.check_balances(
            db, "p1", actor_admin_id=mock_super_admin.id,
        )

    dec_mock.assert_called_once()
    # Decrypt called with (ciphertext, iv, tag, master_key); we only assert
    # the ciphertext triple — the master key reads from settings which may
    # already be cached by lru_cache when this test runs in a full-suite
    # sweep, so we don't pin the exact value here.
    dec_args, _dec_kwargs = dec_mock.call_args
    assert dec_args[0] == "CT_B64"
    assert dec_args[1] == "IV_B64"
    assert dec_args[2] == "TAG_B64"
    client_mock.assert_called_once_with(
        "https://upstream.example.com/v1/balance", timeout=30,
    )
    fake_client.get.assert_awaited_once()
    # The Authorization header must carry the decrypted key (not the encrypted blob).
    _args, kwargs = fake_client.get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer sk-decrypted-key"

    assert len(result.results) == 1
    r = result.results[0]
    assert r.account_id == 1
    assert r.balance == 12_340_000
    assert r.error is None
    # And the account's persistent balance was updated in place.
    assert account.balance == 12_340_000
