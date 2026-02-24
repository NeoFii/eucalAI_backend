"""
认证服务层单元测试
测试 AuthService 的业务逻辑和异常抛出
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.auth_service import AuthService
from app.core.exceptions import (
    EmailAlreadyExistsException,
    WeakPasswordException,
    InvalidCredentialsException,
    UserDisabledException,
    EmailNotVerifiedException,
    UserNotFoundException,
    InvalidTokenException,
    TokenExpiredException,
    SessionNotFoundException,
    SessionRevokedException,
    SessionExpiredException,
)
from app.models.auth_schemas import RegisterRequest


class TestAuthServiceRegister:
    """测试用户注册功能"""

    @pytest.mark.asyncio
    async def test_register_email_already_exists(self):
        """测试邮箱已被注册的异常"""
        # 模拟数据库查询返回已存在的用户
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # 用户已存在
        mock_db.execute.return_value = mock_result

        # 构建注册请求
        register_request = RegisterRequest(
            email="test@example.com",
            password="Test1234!",
            confirm_password="Test1234!",
            verification_code="123456",
        )

        # 应该抛出 EmailAlreadyExistsException
        with pytest.raises(EmailAlreadyExistsException):
            await AuthService.register(mock_db, register_request)

    @pytest.mark.asyncio
    async def test_register_weak_password(self):
        """测试密码强度不足的异常"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # 用户不存在
        mock_db.execute.return_value = mock_result

        register_request = RegisterRequest(
            email="test@example.com",
            password="weak",
            confirm_password="weak",
            verification_code="123456",
        )

        # 应该抛出 WeakPasswordException
        with pytest.raises(WeakPasswordException):
            await AuthService.register(mock_db, register_request)


class TestAuthServiceLogin:
    """测试用户登录功能"""

    @pytest.mark.asyncio
    async def test_login_user_not_found(self):
        """测试用户不存在的异常"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # 应该抛出 InvalidCredentialsException
        with pytest.raises(InvalidCredentialsException):
            await AuthService.login(mock_db, "notexist@example.com", "Test1234!")

    @pytest.mark.asyncio
    async def test_login_invalid_password(self):
        """测试密码错误的异常"""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.password_hash = "$2b$12$hashed_password"  # 模拟哈希后的密码

        # 模拟 verify_password 返回 False
        with patch("app.services.auth_service.verify_password", return_value=False):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute.return_value = mock_result

            with pytest.raises(InvalidCredentialsException):
                await AuthService.login(mock_db, "test@example.com", "WrongPassword")

    @pytest.mark.asyncio
    async def test_login_user_disabled(self):
        """测试用户已被禁用的异常"""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.status = 0  # 禁用状态
        mock_user.password_hash = "$2b$12$hashed_password"

        with patch("app.services.auth_service.verify_password", return_value=True):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute.return_value = mock_result

            with pytest.raises(UserDisabledException):
                await AuthService.login(mock_db, "test@example.com", "Test1234!")

    @pytest.mark.asyncio
    async def test_login_email_not_verified(self):
        """测试邮箱未验证的异常"""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.status = 2  # 待验证状态
        mock_user.password_hash = "$2b$12$hashed_password"

        with patch("app.services.auth_service.verify_password", return_value=True):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_db.execute.return_value = mock_result

            with pytest.raises(EmailNotVerifiedException):
                await AuthService.login(mock_db, "test@example.com", "Test1234!")


class TestAuthServiceRefreshToken:
    """测试刷新令牌功能"""

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self):
        """测试无效令牌的异常"""
        mock_db = AsyncMock()

        with patch("app.services.auth_service.decode_token", return_value=None):
            with pytest.raises(InvalidTokenException):
                await AuthService.refresh_access_token(mock_db, "invalid_token")

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_type(self):
        """测试无效令牌类型的异常"""
        mock_db = Mock()

        with patch("app.services.auth_service.decode_token", return_value={"type": "access"}):
            with pytest.raises(TokenExpiredException):
                await AuthService.refresh_access_token(mock_db, "some_token")


class TestAuthServiceChangePassword:
    """测试修改密码功能"""

    @pytest.mark.asyncio
    async def test_change_password_wrong_old(self):
        """测试旧密码错误的异常"""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.password_hash = "$2b$12$hashed_password"

        with patch("app.services.auth_service.verify_password", return_value=False):
            with pytest.raises(InvalidCredentialsException):
                await AuthService.change_password(
                    mock_db, mock_user, "WrongPassword", "NewPassword123!"
                )

    @pytest.mark.asyncio
    async def test_change_password_weak_new(self):
        """测试新密码强度不足的异常"""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.password_hash = "$2b$12$hashed_password"

        with patch("app.services.auth_service.verify_password", return_value=True):
            with pytest.raises(WeakPasswordException):
                await AuthService.change_password(
                    mock_db, mock_user, "CorrectPassword", "weak"
                )


class TestAuthServiceVerifyEmail:
    """测试邮箱验证功能"""

    @pytest.mark.asyncio
    async def test_verify_email_user_not_found(self):
        """测试用户不存在的异常"""
        mock_db = AsyncMock()

        # 模拟 email_service.verify_code_or_raise 不抛出异常
        with patch("app.services.auth_service.email_service.verify_code_or_raise", new_callable=AsyncMock):
            # 但数据库查询返回空
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            with pytest.raises(UserNotFoundException):
                await AuthService.verify_email(mock_db, "test@example.com", "123456")
