"""
JWT 工具模块测试
测试 JWT token 的生成和验证
"""

import pytest
from datetime import timedelta
from app.utils.timezone import now

from app.utils.jwt import (
    create_access_token,
    verify_access_token,
    create_refresh_token,
    verify_refresh_token,
    decode_token,
    get_token_expiry,
    is_token_expired,
)


class TestCreateAccessToken:
    """创建访问令牌测试"""

    def test_create_access_token_returns_string(self):
        """测试创建访问令牌返回字符串"""
        token = create_access_token({"sub": "test@example.com"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_custom_expiry(self):
        """测试创建带自定义过期时间的令牌"""
        custom_delta = timedelta(minutes=30)
        token = create_access_token({"sub": "test@example.com"}, expires_delta=custom_delta)
        assert isinstance(token, str)
        assert len(token) > 0


class TestVerifyAccessToken:
    """验证访问令牌测试"""

    def test_verify_valid_token(self):
        """测试验证有效令牌"""
        payload = {"sub": "test@example.com"}
        token = create_access_token(payload)

        result = verify_access_token(token)
        assert result is not None
        assert result.get("sub") == "test@example.com"

    def test_verify_invalid_token(self):
        """测试验证无效令牌"""
        result = verify_access_token("invalid.token.here")
        assert result is None

    def test_verify_wrong_type_token(self):
        """测试验证错误类型的令牌"""
        payload = {"sub": "test@example.com"}
        token = create_refresh_token(payload)

        result = verify_access_token(token)
        assert result is None


class TestCreateRefreshToken:
    """创建刷新令牌测试"""

    def test_create_refresh_token_returns_string(self):
        """测试创建刷新令牌返回字符串"""
        token = create_refresh_token({"sub": "test@example.com"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token_with_custom_expiry(self):
        """测试创建带自定义过期时间的刷新令牌"""
        custom_delta = timedelta(days=14)
        token = create_refresh_token({"sub": "test@example.com"}, expires_delta=custom_delta)
        assert isinstance(token, str)
        assert len(token) > 0


class TestVerifyRefreshToken:
    """验证刷新令牌测试"""

    def test_verify_valid_refresh_token(self):
        """测试验证有效刷新令牌"""
        payload = {"sub": "test@example.com"}
        token = create_refresh_token(payload)

        result = verify_refresh_token(token)
        assert result is not None
        assert result.get("sub") == "test@example.com"

    def test_verify_invalid_refresh_token(self):
        """测试验证无效刷新令牌"""
        result = verify_refresh_token("invalid.token.here")
        assert result is None

    def test_verify_wrong_type_refresh_token(self):
        """测试验证错误类型的刷新令牌"""
        payload = {"sub": "test@example.com"}
        token = create_access_token(payload)

        result = verify_refresh_token(token)
        assert result is None


class TestDecodeToken:
    """解码令牌测试"""

    def test_decode_valid_token(self):
        """测试解码有效令牌"""
        payload = {"sub": "test@example.com", "uid": 123}
        token = create_access_token(payload)

        result = decode_token(token)
        assert result is not None
        assert result.get("sub") == "test@example.com"

    def test_decode_invalid_token(self):
        """测试解码无效令牌"""
        result = decode_token("not.a.valid.token")
        assert result is None


class TestTokenExpiry:
    """令牌过期测试"""

    def test_get_token_expiry(self):
        """测试获取令牌过期时间"""
        payload = {"sub": "test@example.com"}
        token = create_access_token(payload)

        expiry = get_token_expiry(token)
        assert expiry is not None
        assert expiry > now()

    def test_get_expiry_invalid_token(self):
        """测试获取无效令牌的过期时间"""
        expiry = get_token_expiry("invalid.token")
        assert expiry is None

    def test_is_token_expired_false(self):
        """测试有效令牌未过期"""
        payload = {"sub": "test@example.com"}
        token = create_access_token(payload)

        assert is_token_expired(token) is False

    def test_is_token_expired_true(self):
        """测试无效令牌已过期"""
        assert is_token_expired("invalid.token") is True


class TestTokenType:
    """令牌类型测试"""

    def test_access_token_has_type(self):
        """测试访问令牌包含类型声明"""
        payload = {"sub": "test@example.com"}
        token = create_access_token(payload)

        result = decode_token(token)
        assert result is not None
        assert result.get("type") == "access"

    def test_refresh_token_has_type(self):
        """测试刷新令牌包含类型声明"""
        payload = {"sub": "test@example.com"}
        token = create_refresh_token(payload)

        result = decode_token(token)
        assert result is not None
        assert result.get("type") == "refresh"

    def test_token_has_iat(self):
        """测试令牌包含签发时间"""
        payload = {"sub": "test@example.com"}
        token = create_access_token(payload)

        result = decode_token(token)
        assert result is not None
        assert "iat" in result

    def test_token_has_exp(self):
        """测试令牌包含过期时间"""
        payload = {"sub": "test@example.com"}
        token = create_access_token(payload)

        result = decode_token(token)
        assert result is not None
        assert "exp" in result


class TestTokenIntegration:
    """令牌集成测试"""

    def test_full_token_lifecycle(self):
        """测试完整的令牌生命周期"""
        access_token = create_access_token({"sub": "test@example.com", "uid": 123})

        access_payload = verify_access_token(access_token)
        assert access_payload is not None
        assert access_payload["sub"] == "test@example.com"

        refresh_token = create_refresh_token({"sub": "test@example.com"})

        refresh_payload = verify_refresh_token(refresh_token)
        assert refresh_payload is not None
        assert refresh_payload["sub"] == "test@example.com"

        assert is_token_expired(access_token) is False
        assert is_token_expired(refresh_token) is False

        access_expiry = get_token_expiry(access_token)
        assert access_expiry is not None


class TestSecurity:
    """安全测试"""

    def test_jwt_algorithm_none_rejected(self):
        """验证 alg=none 攻击被拒绝"""
        import base64
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({"uid": 1, "type": "access"}).encode()
        ).rstrip(b"=").decode()
        forged_token = f"{header}.{payload}."

        result = verify_access_token(forged_token)
        assert result is None, "alg=none 的伪造 token 应被拒绝"
