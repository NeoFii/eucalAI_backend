"""
邀请码服务层单元测试
测试 InvitationService 的业务逻辑和异常抛出
"""

import pytest
from datetime import timedelta
from app.utils.timezone import now
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.invitation_service import InvitationService
from app.core.exceptions import (
    InvalidInvitationCodeException,
    InvitationCodeUsedException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    ServiceException,
)
from app.models import InvitationCode


class TestInvitationServiceVerifyAndUse:
    """测试邀请码验证和核销功能"""

    @pytest.mark.asyncio
    async def test_verify_and_use_success(self):
        """测试成功验证并核销邀请码"""
        mock_db = AsyncMock()

        # 创建一个未使用的邀请码
        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.code = "test_invitation_code_123"
        mock_invitation.status = 0  # 未使用
        mock_invitation.is_unused = True
        mock_invitation.is_used = False
        mock_invitation.is_disabled = False
        mock_invitation.is_expired = False
        mock_invitation.expires_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        # 执行验证和核销
        result = await InvitationService.verify_and_use(mock_db, "test_invitation_code_123", 123456789)

        # 验证结果
        assert result.status == 1  # 已使用
        assert result.used_by == 123456789
        assert result.used_at is not None
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_and_use_code_not_found(self):
        """测试邀请码不存在的异常"""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvalidInvitationCodeException):
            await InvitationService.verify_and_use(mock_db, "non_existent_code", 123456789)

    @pytest.mark.asyncio
    async def test_verify_and_use_code_already_used(self):
        """测试邀请码已被使用的异常"""
        mock_db = AsyncMock()

        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.status = 1  # 已使用
        mock_invitation.is_unused = False
        mock_invitation.is_used = True
        mock_invitation.is_disabled = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvitationCodeUsedException):
            await InvitationService.verify_and_use(mock_db, "used_code", 123456789)

    @pytest.mark.asyncio
    async def test_verify_and_use_code_disabled(self):
        """测试邀请码已弃用的异常"""
        mock_db = AsyncMock()

        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.status = 2  # 已弃用
        mock_invitation.is_unused = False
        mock_invitation.is_used = False
        mock_invitation.is_disabled = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvitationCodeDisabledException):
            await InvitationService.verify_and_use(mock_db, "disabled_code", 123456789)

    @pytest.mark.asyncio
    async def test_verify_and_use_code_expired(self):
        """测试邀请码已过期的异常"""
        mock_db = AsyncMock()

        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.status = 0  # 未使用
        mock_invitation.is_unused = True
        mock_invitation.is_used = False
        mock_invitation.is_disabled = False
        mock_invitation.is_expired = True  # 已过期

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvitationCodeExpiredException):
            await InvitationService.verify_and_use(mock_db, "expired_code", 123456789)


class TestInvitationServiceGenerateCodes:
    """测试批量生成邀请码功能"""

    @pytest.mark.asyncio
    async def test_generate_codes_success(self):
        """测试成功生成邀请码"""
        mock_db = AsyncMock()

        # 模拟查询结果：邀请码不存在（不冲突）
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # 生成5个邀请码（默认7天过期）
        from datetime import timedelta
        from app.utils.timezone import now
        expires_at = now() + timedelta(days=7)
        codes = await InvitationService.generate_codes(mock_db, count=5, expires_at=expires_at)

        # 验证结果
        assert len(codes) == 5
        for code in codes:
            assert code.status == 0  # 未使用
            assert len(code.code) > 0

        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_codes_with_expires_at(self):
        """测试生成带过期时间的邀请码"""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        expires_at = now() + timedelta(days=7)
        codes = await InvitationService.generate_codes(
            mock_db, count=1, expires_at=expires_at, remark="测试邀请码"
        )

        assert len(codes) == 1
        assert codes[0].expires_at == expires_at
        assert codes[0].remark == "测试邀请码"

    @pytest.mark.asyncio
    async def test_generate_codes_with_conflict_retry(self):
        """测试邀请码冲突时重新生成"""
        mock_db = AsyncMock()

        # 第一次查询返回已存在的邀请码（冲突）
        # 第二次查询返回 None（不冲突）
        existing_code = MagicMock(spec=InvitationCode)
        mock_result_conflict = MagicMock()
        mock_result_conflict.scalar_one_or_none.return_value = existing_code

        mock_result_ok = MagicMock()
        mock_result_ok.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_result_conflict, mock_result_ok]

        # 添加过期时间参数
        from datetime import timedelta
        from app.utils.timezone import now
        expires_at = now() + timedelta(days=7)
        codes = await InvitationService.generate_codes(mock_db, count=1, expires_at=expires_at)

        assert len(codes) == 1
        assert mock_db.execute.call_count == 2  # 两次查询


class TestInvitationServiceDisableCode:
    """测试弃用邀请码功能"""

    @pytest.mark.asyncio
    async def test_disable_code_success(self):
        """测试成功弃用邀请码"""
        mock_db = AsyncMock()

        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.status = 0  # 未使用
        mock_invitation.is_used = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        result = await InvitationService.disable_code(mock_db, 1)

        assert result.status == 2  # 已弃用
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_code_not_found(self):
        """测试邀请码不存在的异常"""
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvalidInvitationCodeException):
            await InvitationService.disable_code(mock_db, 999)

    @pytest.mark.asyncio
    async def test_disable_code_already_used(self):
        """测试已使用邀请码不能弃用"""
        mock_db = AsyncMock()

        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.status = 1  # 已使用
        mock_invitation.is_used = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvitationCodeUsedException):
            await InvitationService.disable_code(mock_db, 1)


class TestInvitationServiceEnableCode:
    """测试启用/恢复邀请码功能"""

    @pytest.mark.asyncio
    async def test_enable_code_success(self):
        """测试成功恢复已弃用的邀请码"""
        mock_db = AsyncMock()

        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.status = 2  # 已弃用
        mock_invitation.is_used = False
        mock_invitation.is_disabled = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        result = await InvitationService.enable_code(mock_db, 1)

        assert result.status == 0  # 未使用
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_code_not_disabled(self):
        """测试非弃用状态不能恢复"""
        mock_db = AsyncMock()

        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.status = 0  # 未使用（不是弃用状态）
        mock_invitation.is_used = False
        mock_invitation.is_disabled = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        with pytest.raises(Exception) as exc_info:  # InvitationCodeException
            await InvitationService.enable_code(mock_db, 1)

        # 验证抛出了 InvitationCodeException（基类）
        assert "invitation_code_error" in str(exc_info.value).lower() or "InvitationCodeException" in str(type(exc_info.value))

    @pytest.mark.asyncio
    async def test_enable_code_already_used(self):
        """测试已使用邀请码不能恢复"""
        mock_db = AsyncMock()

        mock_invitation = MagicMock(spec=InvitationCode)
        mock_invitation.id = 1
        mock_invitation.status = 1  # 已使用
        mock_invitation.is_used = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_invitation
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvitationCodeUsedException):
            await InvitationService.enable_code(mock_db, 1)


class TestInvitationCodeProperties:
    """测试邀请码模型属性"""

    def test_is_unused_property(self):
        """测试 is_unused 属性"""
        code = InvitationCode(code="test_code", status=0)
        assert code.is_unused is True

        code.status = 1
        assert code.is_unused is False

    def test_is_used_property(self):
        """测试 is_used 属性"""
        code = InvitationCode(code="test_code", status=1)
        assert code.is_used is True

        code.status = 0
        assert code.is_used is False

    def test_is_disabled_property(self):
        """测试 is_disabled 属性"""
        code = InvitationCode(code="test_code", status=2)
        assert code.is_disabled is True

        code.status = 0
        assert code.is_disabled is False

    def test_is_expired_property_with_no_expires(self):
        """测试无过期时间时的 is_expired 属性"""
        code = InvitationCode(code="test_code", status=0, expires_at=None)
        assert code.is_expired is False

    def test_is_expired_property_with_future_expires(self):
        """测试未来过期时间的 is_expired 属性"""
        code = InvitationCode(
            code="test_code",
            status=0,
            expires_at=now() + timedelta(days=7)
        )
        assert code.is_expired is False

    def test_is_expired_property_with_past_expires(self):
        """测试已过期时间的 is_expired 属性"""
        code = InvitationCode(
            code="test_code",
            status=0,
            expires_at=now() - timedelta(days=1)
        )
        assert code.is_expired is True

    def test_is_valid_property(self):
        """测试 is_valid 属性"""
        # 有效：未使用、未过期、未弃用
        code = InvitationCode(code="test_code", status=0, expires_at=None)
        assert code.is_valid is True

        # 无效：已使用
        code.status = 1
        assert code.is_valid is False

        # 无效：已弃用
        code.status = 2
        assert code.is_valid is False
