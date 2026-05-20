"""Unit tests for auth dependency functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.common.core.exceptions import (
    AuthenticationException,
    InvalidTokenException,
    UserNotFoundException,
)
from app.core.dependencies import (
    get_current_admin,
    get_current_user,
    get_optional_current_admin,
    get_request_meta,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


def _make_request(client_host: str = "127.0.0.1", user_agent: str = "TestAgent/1.0"):
    """Create a minimal mock Request."""
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = client_host
    request.headers = {"user-agent": user_agent}
    return request


def _make_credentials(token: str | None):
    """Create a mock HTTPAuthorizationCredentials."""
    if token is None:
        return None
    cred = MagicMock()
    cred.credentials = token
    return cred


# ──────────────────────────────────────────────
# Import tests
# ──────────────────────────────────────────────


def test_all_dependencies_importable():
    """All 4 dependency functions can be imported from the package."""
    from app.core.dependencies import (
        get_current_admin,
        get_current_user,
        get_optional_current_admin,
        get_request_meta,
    )

    assert callable(get_current_user)
    assert callable(get_current_admin)
    assert callable(get_optional_current_admin)
    assert callable(get_request_meta)


# ──────────────────────────────────────────────
# get_current_user tests
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_user_no_token():
    """Raises AuthenticationException when no token is provided."""
    request = _make_request()
    db = AsyncMock()

    with pytest.raises(AuthenticationException, match="未提供认证信息"):
        await get_current_user(request=request, credentials=None, access_token=None, db=db)


@pytest.mark.asyncio
@patch("app.core.dependencies.user.decode_token", return_value=None)
async def test_get_current_user_invalid_token(mock_decode):
    """Raises InvalidTokenException when token cannot be decoded."""
    request = _make_request()
    db = AsyncMock()

    with pytest.raises(InvalidTokenException):
        await get_current_user(
            request=request, credentials=_make_credentials("bad-token"), access_token=None, db=db
        )


@pytest.mark.asyncio
@patch("app.core.dependencies.user.decode_token", return_value={"type": "refresh", "uid": "u1"})
async def test_get_current_user_wrong_token_type(mock_decode):
    """Raises InvalidTokenException when token type is not 'access'."""
    request = _make_request()
    db = AsyncMock()

    with pytest.raises(InvalidTokenException, match="无效的令牌类型"):
        await get_current_user(
            request=request, credentials=_make_credentials("some-token"), access_token=None, db=db
        )


@pytest.mark.asyncio
@patch("app.core.dependencies.user.decode_token", return_value={"type": "access"})
async def test_get_current_user_no_uid_in_payload(mock_decode):
    """Raises InvalidTokenException when uid is missing from payload."""
    request = _make_request()
    db = AsyncMock()

    with pytest.raises(InvalidTokenException, match="令牌中未包含用户信息"):
        await get_current_user(
            request=request, credentials=_make_credentials("some-token"), access_token=None, db=db
        )


@pytest.mark.asyncio
@patch("app.core.dependencies.user.UserRepository")
@patch("app.core.dependencies.user.decode_token", return_value={"type": "access", "uid": "u_abc"})
async def test_get_current_user_user_not_found(mock_decode, mock_repo_cls):
    """Raises UserNotFoundException when user does not exist."""
    request = _make_request()
    db = AsyncMock()
    mock_repo_cls.return_value.get_by_uid = AsyncMock(return_value=None)

    with pytest.raises(UserNotFoundException):
        await get_current_user(
            request=request, credentials=_make_credentials("valid-token"), access_token=None, db=db
        )


@pytest.mark.asyncio
@patch("app.core.dependencies.user.set_uid")
@patch("app.core.dependencies.user.UserRepository")
@patch("app.core.dependencies.user.decode_token", return_value={"type": "access", "uid": "u_abc"})
async def test_get_current_user_success(mock_decode, mock_repo_cls, mock_set_uid):
    """Returns User instance on successful auth and calls set_uid."""
    request = _make_request()
    db = AsyncMock()
    mock_user = MagicMock()
    mock_user.uid = "u_abc"
    mock_repo_cls.return_value.get_by_uid = AsyncMock(return_value=mock_user)

    result = await get_current_user(
        request=request, credentials=_make_credentials("valid-token"), access_token=None, db=db
    )

    assert result is mock_user
    mock_set_uid.assert_called_once_with("u_abc")


@pytest.mark.asyncio
@patch("app.core.dependencies.user.set_uid")
@patch("app.core.dependencies.user.UserRepository")
@patch("app.core.dependencies.user.decode_token", return_value={"type": "access", "uid": "u_cookie"})
async def test_get_current_user_from_cookie(mock_decode, mock_repo_cls, mock_set_uid):
    """Extracts token from cookie when no Bearer header is present."""
    request = _make_request()
    db = AsyncMock()
    mock_user = MagicMock()
    mock_user.uid = "u_cookie"
    mock_repo_cls.return_value.get_by_uid = AsyncMock(return_value=mock_user)

    result = await get_current_user(
        request=request, credentials=None, access_token="cookie-token", db=db
    )

    assert result is mock_user


@pytest.mark.asyncio
@patch("app.core.dependencies.user.set_uid")
@patch("app.core.dependencies.user.UserRepository")
@patch("app.core.dependencies.user.decode_token", return_value={"type": "access", "uid": "u1"})
async def test_get_current_user_no_blacklist_check(mock_decode, mock_repo_cls, mock_set_uid):
    """User auth does NOT call is_token_blacklisted (D-08)."""
    import app.core.dependencies.user as user_mod

    # Verify the module does not even reference is_token_blacklisted
    assert not hasattr(user_mod, "is_token_blacklisted"), (
        "user.py should not import is_token_blacklisted"
    )

    request = _make_request()
    db = AsyncMock()
    mock_user = MagicMock()
    mock_user.uid = "u1"
    mock_repo_cls.return_value.get_by_uid = AsyncMock(return_value=mock_user)

    result = await get_current_user(
        request=request, credentials=_make_credentials("token"), access_token=None, db=db
    )
    assert result is mock_user


# ──────────────────────────────────────────────
# get_current_admin tests
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_admin_no_token():
    """Raises AuthenticationException when no token is provided."""
    request = _make_request()
    db = AsyncMock()

    with pytest.raises(AuthenticationException, match="未提供认证信息"):
        await get_current_admin(request=request, credentials=None, access_token=None, db=db)


@pytest.mark.asyncio
@patch("app.core.dependencies.admin.is_token_blacklisted", new_callable=AsyncMock, return_value=True)
async def test_get_current_admin_blacklisted(mock_bl):
    """Raises InvalidTokenException when token is blacklisted (D-07)."""
    request = _make_request()
    db = AsyncMock()

    with pytest.raises(InvalidTokenException, match="令牌已被吊销"):
        await get_current_admin(
            request=request, credentials=_make_credentials("revoked-token"), access_token=None, db=db
        )

    mock_bl.assert_called_once()


@pytest.mark.asyncio
@patch("app.core.dependencies.admin.AdminUserRepository")
@patch("app.core.dependencies.admin.decode_token", return_value={"type": "access", "uid": "a_xyz"})
@patch("app.core.dependencies.admin.is_token_blacklisted", new_callable=AsyncMock, return_value=False)
async def test_get_current_admin_not_found(mock_bl, mock_decode, mock_repo_cls):
    """Raises AuthenticationException when admin does not exist."""
    request = _make_request()
    db = AsyncMock()
    mock_repo_cls.return_value.get_by_uid = AsyncMock(return_value=None)

    with pytest.raises(AuthenticationException, match="管理员不存在"):
        await get_current_admin(
            request=request, credentials=_make_credentials("valid-token"), access_token=None, db=db
        )


@pytest.mark.asyncio
@patch("app.core.dependencies.admin.set_uid")
@patch("app.core.dependencies.admin.AdminUserRepository")
@patch("app.core.dependencies.admin.decode_token", return_value={"type": "access", "uid": "a_xyz"})
@patch("app.core.dependencies.admin.is_token_blacklisted", new_callable=AsyncMock, return_value=False)
async def test_get_current_admin_success(mock_bl, mock_decode, mock_repo_cls, mock_set_uid):
    """Returns AdminUser instance on successful auth and calls set_uid."""
    request = _make_request()
    db = AsyncMock()
    mock_admin = MagicMock()
    mock_admin.uid = "a_xyz"
    mock_repo_cls.return_value.get_by_uid = AsyncMock(return_value=mock_admin)

    result = await get_current_admin(
        request=request, credentials=_make_credentials("valid-token"), access_token=None, db=db
    )

    assert result is mock_admin
    mock_set_uid.assert_called_once_with("a_xyz")
    mock_bl.assert_called_once()


# ──────────────────────────────────────────────
# get_optional_current_admin tests
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_optional_current_admin_returns_none_on_failure():
    """Returns None when authentication fails instead of raising."""
    request = _make_request()
    db = AsyncMock()

    result = await get_optional_current_admin(
        request=request, credentials=None, access_token=None, db=db
    )

    assert result is None


@pytest.mark.asyncio
@patch("app.core.dependencies.admin.set_uid")
@patch("app.core.dependencies.admin.AdminUserRepository")
@patch("app.core.dependencies.admin.decode_token", return_value={"type": "access", "uid": "a_opt"})
@patch("app.core.dependencies.admin.is_token_blacklisted", new_callable=AsyncMock, return_value=False)
async def test_get_optional_current_admin_returns_admin_on_success(mock_bl, mock_decode, mock_repo_cls, mock_set_uid):
    """Returns AdminUser when authentication succeeds."""
    request = _make_request()
    db = AsyncMock()
    mock_admin = MagicMock()
    mock_admin.uid = "a_opt"
    mock_repo_cls.return_value.get_by_uid = AsyncMock(return_value=mock_admin)

    result = await get_optional_current_admin(
        request=request, credentials=_make_credentials("token"), access_token=None, db=db
    )

    assert result is mock_admin


# ──────────────────────────────────────────────
# get_request_meta tests
# ──────────────────────────────────────────────


def test_get_request_meta_extracts_ip_and_ua():
    """Correctly extracts IP and User-Agent from request."""
    request = _make_request(client_host="192.168.1.1", user_agent="Mozilla/5.0")

    ip, ua = get_request_meta(request)

    assert ip == "192.168.1.1"
    assert ua == "Mozilla/5.0"


def test_get_request_meta_no_client():
    """Returns None for IP when request.client is None."""
    request = MagicMock()
    request.client = None
    request.headers = {"user-agent": "Bot/1.0"}

    ip, ua = get_request_meta(request)

    assert ip is None
    assert ua == "Bot/1.0"


def test_get_request_meta_no_user_agent():
    """Returns None for user-agent when header is missing."""
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {}

    ip, ua = get_request_meta(request)

    assert ip == "10.0.0.1"
    assert ua is None
