"""
邀请码服务
处理邀请码的生成、验证、查询等业务逻辑
"""

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import (
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
)
from common.utils.timezone import now
from admin.models import AdminUser, InvitationCode


class InvitationCodeService:
    """邀请码服务类"""

    @staticmethod
    def generate_code(length: int = 16) -> str:
        """生成安全的高熵随机邀请码（Base64URL 编码，16字节=22字符）"""
        return secrets.token_urlsafe(length)

    @staticmethod
    async def generate(
        db: AsyncSession,
        created_by: int,
        quantity: int = 1,
        expires_days: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        max_uses: int = 1,
        remark: Optional[str] = None,
    ) -> list[InvitationCode]:
        """
        生成邀请码

        Args:
            db: 数据库会话
            created_by: 创建者管理员 UID
            quantity: 生成数量
            expires_days: 过期天数（与 expires_at 二选一）
            expires_at: 具体过期时间（与 expires_days 二选一，优先使用）
            max_uses: 最大使用次数
            remark: 备注

        Returns:
            list[InvitationCode]: 生成的邀请码列表
        """
        codes = []

        # 优先使用具体的过期时间，否则根据天数计算
        if expires_at:
            expires_at_value = expires_at
        elif expires_days:
            expires_at_value = now() + timedelta(days=expires_days)
        else:
            # 默认 7 天
            expires_at_value = now() + timedelta(days=7)

        for _ in range(quantity):
            # 确保邀请码唯一
            code_str = InvitationCodeService.generate_code()
            while True:
                result = await db.execute(
                    select(InvitationCode).where(InvitationCode.code == code_str)
                )
                if not result.scalar_one_or_none():
                    break
                code_str = InvitationCodeService.generate_code()

            code = InvitationCode(
                code=code_str,
                status=0,  # 0=未使用
                created_by=created_by,
                expires_at=expires_at_value,
                remark=remark,
            )
            db.add(code)
            codes.append(code)

        await db.commit()

        # 刷新以获取 ID
        for code in codes:
            await db.refresh(code)

        return codes

    @staticmethod
    async def verify_and_use(
        db: AsyncSession,
        code: str,
        used_by: int,
    ) -> InvitationCode:
        """
        验证并使用邀请码

        Args:
            db: 数据库会话
            code: 邀请码
            used_by: 使用者 UID

        Returns:
            InvitationCode: 邀请码对象

        Raises:
            InvitationCodeUsedException: 邀请码已被使用
            InvitationCodeDisabledException: 邀请码已被弃用
            InvitationCodeExpiredException: 邀请码已过期
        """
        result = await db.execute(
            select(InvitationCode).where(InvitationCode.code == code)
        )
        invitation_code = result.scalar_one_or_none()

        if not invitation_code:
            from common.core.exceptions import InvalidInvitationCodeException
            raise InvalidInvitationCodeException()

        if invitation_code.is_used:
            raise InvitationCodeUsedException()

        if invitation_code.is_disabled:
            raise InvitationCodeDisabledException()

        if invitation_code.is_expired:
            raise InvitationCodeExpiredException()

        # 使用邀请码
        invitation_code.status = 1  # 1=已使用
        invitation_code.used_by = used_by
        invitation_code.used_at = now()

        await db.commit()
        await db.refresh(invitation_code)

        return invitation_code

    @staticmethod
    async def enable(db: AsyncSession, code_id: int) -> InvitationCode:
        """启用邀请码"""
        result = await db.execute(
            select(InvitationCode).where(InvitationCode.id == code_id)
        )
        code = result.scalar_one_or_none()

        if not code:
            from common.core.exceptions import InvalidInvitationCodeException
            raise InvalidInvitationCodeException()

        if code.status == 1:
            raise InvitationCodeUsedException()

        code.status = 0  # 0=未使用
        await db.commit()
        await db.refresh(code)

        return code

    @staticmethod
    async def disable(db: AsyncSession, code_id: int) -> InvitationCode:
        """弃用邀请码"""
        result = await db.execute(
            select(InvitationCode).where(InvitationCode.id == code_id)
        )
        code = result.scalar_one_or_none()

        if not code:
            from common.core.exceptions import InvalidInvitationCodeException
            raise InvalidInvitationCodeException()

        code.status = 2  # 2=已弃用
        await db.commit()
        await db.refresh(code)

        return code

    @staticmethod
    async def update(
        db: AsyncSession,
        code_id: int,
        expires_at: Optional[datetime] = None,
        remark: Optional[str] = None,
    ) -> InvitationCode:
        """
        更新邀请码信息

        Args:
            db: 数据库会话
            code_id: 邀请码ID
            expires_at: 过期时间（None 表示不修改）
            remark: 备注（None 表示不修改）

        Returns:
            InvitationCode: 更新后的邀请码
        """
        result = await db.execute(
            select(InvitationCode).where(InvitationCode.id == code_id)
        )
        code = result.scalar_one_or_none()

        if not code:
            from common.core.exceptions import InvalidInvitationCodeException
            raise InvalidInvitationCodeException()

        # 已使用的邀请码不能修改
        if code.status == 1:
            raise InvitationCodeUsedException()

        if expires_at is not None:
            code.expires_at = expires_at
        if remark is not None:
            code.remark = remark

        await db.commit()
        await db.refresh(code)

        return code

    @staticmethod
    async def list(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        status: Optional[int] = None,
    ) -> tuple[list[InvitationCode], int]:
        """
        获取邀请码列表

        Args:
            db: 数据库会话
            page: 页码
            page_size: 每页数量
            status: 状态过滤

        Returns:
            tuple[list[InvitationCode], int]: (邀请码列表, 总数)
        """
        query = select(InvitationCode)

        if status is not None:
            query = query.where(InvitationCode.status == status)

        # 统计总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页查询
        query = query.order_by(InvitationCode.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        codes = result.scalars().all()

        return list(codes), total

    @staticmethod
    async def get_stats(db: AsyncSession) -> dict:
        """
        获取邀请码统计信息

        Returns:
            dict: 统计信息
        """
        # 总数
        result = await db.execute(
            select(func.count(InvitationCode.id))
        )
        total = result.scalar() or 0

        # 已使用 (status=1)
        result = await db.execute(
            select(func.count(InvitationCode.id)).where(InvitationCode.status == 1)
        )
        used = result.scalar() or 0

        # 有效 (status=0)
        result = await db.execute(
            select(func.count(InvitationCode.id)).where(InvitationCode.status == 0)
        )
        valid = result.scalar() or 0

        return {
            "total": total,
            "used": used,
            "valid": valid,
        }
