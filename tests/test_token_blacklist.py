"""Tests for token blacklist and refresh-token rotation."""

from __future__ import annotations

import os

os.environ["INTERNAL_SECRET"] = "test_internal_secret_32chars_long!"
os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_32bytes_long!!"

import pytest

from common.utils.jwt import create_access_token, create_refresh_token, get_token_jti


_JWT_SECRET = os.environ["JWT_SECRET_KEY"]


class TestTokenBlacklist:
    """Unit tests for common.token_blacklist using a fake Redis."""

    @pytest.fixture(autouse=True)
    def _patch_redis(self, monkeypatch):
        self._store: dict[str, str] = {}

        class FakeRedis:
            def __init__(self, store):
                self._store = store

            async def set(self, key, value, ex=None):
                self._store[key] = value

            async def exists(self, key):
                return 1 if key in self._store else 0

        fake = FakeRedis(self._store)
        monkeypatch.setattr("common.token_blacklist.get_redis", lambda: fake)

    @pytest.mark.asyncio
    async def test_blacklist_and_check(self):
        from common.token_blacklist import blacklist_token, is_token_blacklisted

        assert not await is_token_blacklisted("abc123")
        await blacklist_token("abc123", 300)
        assert await is_token_blacklisted("abc123")

    @pytest.mark.asyncio
    async def test_zero_ttl_skipped(self):
        from common.token_blacklist import blacklist_token, is_token_blacklisted

        await blacklist_token("expired", 0)
        assert not await is_token_blacklisted("expired")


class TestAuthServiceRevocation:
    """Test logout blacklisting and refresh rotation via monkeypatched Redis."""

    @pytest.fixture(autouse=True)
    def _patch_redis(self, monkeypatch):
        self._store: dict[str, str] = {}

        class FakeRedis:
            def __init__(self, store):
                self._store = store

            async def set(self, key, value, ex=None):
                self._store[key] = value

            async def exists(self, key):
                return 1 if key in self._store else 0

        fake = FakeRedis(self._store)
        monkeypatch.setattr("common.token_blacklist.get_redis", lambda: fake)

    @pytest.mark.asyncio
    async def test_logout_blacklists_tokens(self):
        from types import SimpleNamespace

        from admin_service.services.auth_service import AdminAuthService

        access = create_access_token(
            data={"uid": 1, "sub": "1"},
            secret_key=_JWT_SECRET,
            expire_minutes=15,
        )
        refresh = create_refresh_token(
            data={"uid": 1, "sub": "1"},
            secret_key=_JWT_SECRET,
            expire_days=7,
        )
        admin = SimpleNamespace(email="test@example.com")

        await AdminAuthService.logout(admin, access_token=access, refresh_token=refresh)

        from common.token_blacklist import is_token_blacklisted

        assert await is_token_blacklisted(get_token_jti(access))
        assert await is_token_blacklisted(get_token_jti(refresh))

    @pytest.mark.asyncio
    async def test_refresh_blacklists_old_token(self, monkeypatch):
        from admin_service.services.auth_service import AdminAuthService

        refresh = create_refresh_token(
            data={"uid": 42, "sub": "42"},
            secret_key=_JWT_SECRET,
            expire_days=7,
        )
        old_jti = get_token_jti(refresh)

        fake_admin = type("Admin", (), {"status": 1})()

        async def _fake_get_by_uid(self, uid):
            return fake_admin

        monkeypatch.setattr(
            "admin_service.services.auth_service.AdminUserRepository",
            lambda db: type("Repo", (), {"get_by_uid": _fake_get_by_uid})(),
        )

        new_access, new_refresh = await AdminAuthService.refresh_access_token("db", refresh)

        from common.token_blacklist import is_token_blacklisted

        assert await is_token_blacklisted(old_jti)
        assert new_access is not None
        assert new_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_rejects_blacklisted_token(self, monkeypatch):
        from common.core.exceptions import InvalidTokenException
        from common.token_blacklist import blacklist_token

        from admin_service.services.auth_service import AdminAuthService

        refresh = create_refresh_token(
            data={"uid": 42, "sub": "42"},
            secret_key=_JWT_SECRET,
            expire_days=7,
        )
        await blacklist_token(get_token_jti(refresh), 3600)

        with pytest.raises(InvalidTokenException):
            await AdminAuthService.refresh_access_token("db", refresh)
