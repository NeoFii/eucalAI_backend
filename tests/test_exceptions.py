"""
自定义异常单元测试
测试异常类的定义和行为
"""

import pytest
from fastapi import HTTPException, status

from app.core.exceptions import (
    APIException,
    NotFoundException,
    ValidationException,
    ServiceException,
    # 认证异常
    AuthenticationException,
    InvalidCredentialsException,
    UserNotFoundException,
    UserDisabledException,
    EmailNotVerifiedException,
    TokenException,
    InvalidTokenException,
    TokenExpiredException,
    SessionException,
    SessionNotFoundException,
    SessionRevokedException,
    SessionExpiredException,
    # 注册异常
    RegistrationException,
    EmailAlreadyExistsException,
    WeakPasswordException,
    # 验证码异常
    VerificationException,
    InvalidCodeException,
    CodeExpiredException,
    CodeNotFoundException,
    RateLimitExceededException,
)


class TestAPIException:
    """测试基础 API 异常类"""

    def test_api_exception_default(self):
        """测试默认 API 异常"""
        exc = APIException(status_code=400, detail="Error", code="error")
        assert exc.status_code == 400
        assert exc.detail == "Error"
        assert exc.code == "error"

    def test_api_exception_is_http_exception(self):
        """测试 API 异常是 HTTP 异常的子类"""
        exc = APIException(status_code=400, detail="Error")
        assert isinstance(exc, HTTPException)


class TestNotFoundException:
    """测试资源不存在异常"""

    def test_not_found_default_message(self):
        """测试默认消息"""
        exc = NotFoundException()
        assert exc.status_code == status.HTTP_404_NOT_FOUND
        assert "不存在" in exc.detail

    def test_not_found_custom_message(self):
        """测试自定义消息"""
        exc = NotFoundException(detail="用户不存在")
        assert exc.detail == "用户不存在"


class TestValidationException:
    """测试验证异常"""

    def test_validation_default(self):
        """测试默认验证异常"""
        exc = ValidationException()
        assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "验证失败" in exc.detail


class TestServiceException:
    """测试服务异常"""

    def test_service_default(self):
        """测试默认服务异常"""
        exc = ServiceException()
        assert exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "不可用" in exc.detail


# ==================== 认证异常测试 ====================

class TestAuthenticationException:
    """测试认证异常"""

    def test_auth_exception_default(self):
        """测试默认认证异常"""
        exc = AuthenticationException("认证失败")
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.detail == "认证失败"


class TestInvalidCredentialsException:
    """测试凭证无效异常"""

    def test_invalid_credentials_default(self):
        """测试默认消息"""
        exc = InvalidCredentialsException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "邮箱或密码错误" in exc.detail


class TestUserNotFoundException:
    """测试用户不存在异常"""

    def test_user_not_found(self):
        """测试用户不存在异常"""
        exc = UserNotFoundException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "用户不存在" in exc.detail


class TestUserDisabledException:
    """测试用户禁用异常"""

    def test_user_disabled(self):
        """测试用户禁用异常"""
        exc = UserDisabledException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "禁用" in exc.detail


class TestEmailNotVerifiedException:
    """测试邮箱未验证异常"""

    def test_email_not_verified(self):
        """测试邮箱未验证异常"""
        exc = EmailNotVerifiedException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "验证邮箱" in exc.detail


class TestTokenException:
    """测试令牌异常"""

    def test_token_exception_default(self):
        """测试默认令牌异常"""
        exc = TokenException("令牌错误")
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.detail == "令牌错误"


class TestInvalidTokenException:
    """测试无效令牌异常"""

    def test_invalid_token(self):
        """测试无效令牌异常"""
        exc = InvalidTokenException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "无效" in exc.detail


class TestTokenExpiredException:
    """测试令牌过期异常"""

    def test_token_expired(self):
        """测试令牌过期异常"""
        exc = TokenExpiredException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "过期" in exc.detail


class TestSessionException:
    """测试会话异常"""

    def test_session_exception_default(self):
        """测试默认会话异常"""
        exc = SessionException("会话错误")
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED


class TestSessionNotFoundException:
    """测试会话不存在异常"""

    def test_session_not_found(self):
        """测试会话不存在异常"""
        exc = SessionNotFoundException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "会话不存在" in exc.detail


class TestSessionRevokedException:
    """测试会话已注销异常"""

    def test_session_revoked(self):
        """测试会话已注销异常"""
        exc = SessionRevokedException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "注销" in exc.detail


class TestSessionExpiredException:
    """测试会话已过期异常"""

    def test_session_expired(self):
        """测试会话已过期异常"""
        exc = SessionExpiredException()
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert "过期" in exc.detail


# ==================== 注册异常测试 ====================

class TestRegistrationException:
    """测试注册异常"""

    def test_registration_exception(self):
        """测试注册异常"""
        exc = RegistrationException("注册失败")
        assert exc.status_code == status.HTTP_400_BAD_REQUEST


class TestEmailAlreadyExistsException:
    """测试邮箱已存在异常"""

    def test_email_already_exists(self):
        """测试邮箱已存在异常"""
        exc = EmailAlreadyExistsException()
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "已被注册" in exc.detail


class TestWeakPasswordException:
    """测试弱密码异常"""

    def test_weak_password(self):
        """测试弱密码异常"""
        exc = WeakPasswordException()
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "强度" in exc.detail


# ==================== 验证码异常测试 ====================

class TestVerificationException:
    """测试验证码异常"""

    def test_verification_exception(self):
        """测试验证码异常"""
        exc = VerificationException("验证码错误")
        assert exc.status_code == status.HTTP_400_BAD_REQUEST


class TestInvalidCodeException:
    """测试验证码错误异常"""

    def test_invalid_code(self):
        """测试验证码错误异常"""
        exc = InvalidCodeException()
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "验证码错误" in exc.detail


class TestCodeExpiredException:
    """测试验证码过期异常"""

    def test_code_expired(self):
        """测试验证码过期异常"""
        exc = CodeExpiredException()
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "过期" in exc.detail


class TestCodeNotFoundException:
    """测试验证码不存在异常"""

    def test_code_not_found(self):
        """测试验证码不存在异常"""
        exc = CodeNotFoundException()
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert "不存在" in exc.detail


class TestRateLimitExceededException:
    """测试频率限制异常"""

    def test_rate_limit_exceeded(self):
        """测试频率限制异常"""
        exc = RateLimitExceededException()
        assert exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "频繁" in exc.detail


class TestExceptionHierarchy:
    """测试异常继承关系"""

    def test_all_auth_exceptions_inherit_from_auth(self):
        """测试所有认证异常继承自认证基类"""
        exceptions = [
            InvalidCredentialsException(),
            UserNotFoundException(),
            UserDisabledException(),
            EmailNotVerifiedException(),
            InvalidTokenException(),
            TokenExpiredException(),
            SessionNotFoundException(),
            SessionRevokedException(),
            SessionExpiredException(),
        ]
        for exc in exceptions:
            assert isinstance(exc, AuthenticationException)

    def test_all_registration_exceptions_inherit_from_registration(self):
        """测试所有注册异常继承自注册基类"""
        exceptions = [
            EmailAlreadyExistsException(),
            WeakPasswordException(),
        ]
        for exc in exceptions:
            assert isinstance(exc, RegistrationException)

    def test_all_verification_exceptions_inherit_from_verification(self):
        """测试所有验证码异常继承自验证码基类"""
        exceptions = [
            InvalidCodeException(),
            CodeExpiredException(),
            CodeNotFoundException(),
        ]
        for exc in exceptions:
            assert isinstance(exc, VerificationException)
