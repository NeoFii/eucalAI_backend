"""
邀请码服务层
处理邀请码的生成、验证、核销等业务逻辑
"""

import logging
import secrets
from datetime import datetime
from typing import Optional

from app.utils.timezone import now, utc_to_shanghai

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    InvalidInvitationCodeException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
    ServiceException,
)
from app.models import InvitationCode
from app.utils.snowflake import generate_snowflake_id

# 获取日志记录器
logger = logging.getLogger(__name__)


class InvitationService:
    """
    邀请码服务类
    封装邀请码相关的业务逻辑
    """

    @staticmethod
    async def verify_and_use(
        db: AsyncSession,
        code: str,
        used_by_uid: int,
    ) -> InvitationCode:
        """
        验证并核销邀请码

        使用 SELECT ... FOR UPDATE 进行行级锁定，确保并发安全

        Args:
            db: 数据库会话
            code: 邀请码字符串
            used_by_uid: 使用者 uid

        Returns:
            InvitationCode: 更新后的邀请码对象

        Raises:
            InvalidInvitationCodeException: 邀请码不存在
            InvitationCodeUsedException: 邀请码已被使用
            InvitationCodeDisabledException: 邀请码已被弃用
            InvitationCodeExpiredException: 邀请码已过期
        """
        # 使用 FOR UPDATE 锁定行，防止并发问题
        result = await db.execute(
            select(InvitationCode)
            .where(InvitationCode.code == code)
            .with_for_update()
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            logger.warning(f"邀请码验证失败：邀请码不存在 ({code[:8]}...)")
            raise InvalidInvitationCodeException()

        # 检查邀请码状态
        if invitation.is_used:
            logger.warning(f"邀请码验证失败：邀请码已被使用 (id={invitation.id})")
            raise InvitationCodeUsedException()

        if invitation.is_disabled:
            logger.warning(f"邀请码验证失败：邀请码已弃用 (id={invitation.id})")
            raise InvitationCodeDisabledException()

        if invitation.is_expired:
            logger.warning(f"邀请码验证失败：邀请码已过期 (id={invitation.id})")
            raise InvitationCodeExpiredException()

        # 核销邀请码
        invitation.status = 1  # 已使用
        invitation.used_by = used_by_uid
        invitation.used_at = now()

        await db.flush()  #  flush 到数据库，但不提交事务（由调用方控制）

        logger.info(f"邀请码核销成功：id={invitation.id}, used_by={used_by_uid}")
        return invitation

    @staticmethod
    async def generate_codes(
        db: AsyncSession,
        count: int,
        expires_at: datetime,
        created_by: Optional[int] = None,
        remark: Optional[str] = None,
    ) -> list[InvitationCode]:
        """
        批量生成邀请码

        使用 secrets.token_urlsafe(16) 生成高熵随机字符串（22位，128bit熵）

        Args:
            db: 数据库会话
            count: 生成数量
            created_by: 创建者 uid（可选）
            expires_at: 过期时间（必须，默认7天后）
            remark: 管理备注（可选）

        Returns:
            list[InvitationCode]: 生成的邀请码对象列表

        Raises:
            ServiceException: 生成过程中发生错误
        """
        codes_to_insert = []
        attempts = 0
        max_attempts = count * 3  # 最多尝试次数，防止无限循环

        while len(codes_to_insert) < count and attempts < max_attempts:
            attempts += 1

            # 生成高熵随机邀请码（22位字符串，128bit熵）
            code_str = secrets.token_urlsafe(16)

            # 检查是否已存在
            existing = await db.execute(
                select(InvitationCode).where(InvitationCode.code == code_str)
            )
            if existing.scalar_one_or_none():
                # 冲突则重新生成（概率极低但需处理）
                logger.debug(f"邀请码冲突，重新生成: {code_str[:8]}...")
                continue

            # 处理过期时间：确保使用上海时间（UTC+8）
            # 如果前端传了带时区的时间，转换为上海时间；否则直接使用
            if expires_at.tzinfo is not None:
                processed_expires_at = utc_to_shanghai(expires_at)
            else:
                # 假设前端传的 naive datetime 已经是上海时间
                processed_expires_at = expires_at

            # 创建邀请码对象
            invitation_code = InvitationCode(
                code=code_str,
                status=0,  # 未使用
                created_by=created_by,
                expires_at=processed_expires_at,
                remark=remark,
            )
            codes_to_insert.append(invitation_code)

        if len(codes_to_insert) < count:
            raise ServiceException(detail=f"邀请码生成失败：仅生成 {len(codes_to_insert)}/{count} 个")

        # 批量插入
        for code in codes_to_insert:
            db.add(code)

        await db.flush()

        logger.info(f"批量生成邀请码成功：{count} 个，created_by={created_by}")
        return codes_to_insert

    @staticmethod
    async def get_code_list(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        status: Optional[int] = None,
    ) -> tuple[list[InvitationCode], int]:
        """
        分页查询邀请码列表

        Args:
            db: 数据库会话
            page: 页码（从1开始）
            page_size: 每页数量
            status: 状态过滤（可选）

        Returns:
            tuple[list[InvitationCode], int]: (邀请码列表, 总数)
        """
        # 构建查询
        query = select(InvitationCode)
        count_query = select(func.count()).select_from(InvitationCode)

        if status is not None:
            query = query.where(InvitationCode.status == status)
            count_query = count_query.where(InvitationCode.status == status)

        # 按创建时间倒序
        query = query.order_by(InvitationCode.created_at.desc())

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        # 执行查询
        result = await db.execute(query)
        codes = result.scalars().all()

        # 查询总数
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        return list(codes), total

    @staticmethod
    async def disable_code(
        db: AsyncSession,
        code_id: int,
    ) -> InvitationCode:
        """
        弃用邀请码

        将邀请码状态设为 2（已弃用）
        已使用的邀请码不能弃用

        Args:
            db: 数据库会话
            code_id: 邀请码 ID

        Returns:
            InvitationCode: 更新后的邀请码对象

        Raises:
            InvalidInvitationCodeException: 邀请码不存在
            InvitationCodeUsedException: 邀请码已被使用，不能弃用
        """
        result = await db.execute(
            select(InvitationCode).where(InvitationCode.id == code_id)
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            raise InvalidInvitationCodeException(detail="邀请码不存在")

        if invitation.is_used:
            raise InvitationCodeUsedException(detail="邀请码已被使用，无法弃用")

        invitation.status = 2  # 已弃用
        await db.flush()

        logger.info(f"邀请码弃用成功：id={code_id}")
        return invitation

    @staticmethod
    async def enable_code(
        db: AsyncSession,
        code_id: int,
    ) -> InvitationCode:
        """
        启用/恢复邀请码

        将已弃用的邀请码状态重置为 0（未使用）
        已使用的邀请码不能恢复

        Args:
            db: 数据库会话
            code_id: 邀请码 ID

        Returns:
            InvitationCode: 更新后的邀请码对象

        Raises:
            InvalidInvitationCodeException: 邀请码不存在
            InvitationCodeUsedException: 邀请码已被使用，不能恢复
            InvitationCodeException: 邀请码不是弃用状态
        """
        from app.core.exceptions import InvitationCodeException

        result = await db.execute(
            select(InvitationCode).where(InvitationCode.id == code_id)
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            raise InvalidInvitationCodeException(detail="邀请码不存在")

        if invitation.is_used:
            raise InvitationCodeUsedException(detail="邀请码已被使用，无法恢复")

        if not invitation.is_disabled:
            raise InvitationCodeException(detail="邀请码不是弃用状态")

        invitation.status = 0  # 未使用
        await db.flush()

        logger.info(f"邀请码恢复成功：id={code_id}")
        return invitation

    @staticmethod
    async def get_code_by_id(
        db: AsyncSession,
        code_id: int,
    ) -> Optional[InvitationCode]:
        """
        通过 ID 获取邀请码

        Args:
            db: 数据库会话
            code_id: 邀请码 ID

        Returns:
            Optional[InvitationCode]: 邀请码对象，不存在返回 None
        """
        result = await db.execute(
            select(InvitationCode).where(InvitationCode.id == code_id)
        )
        return result.scalar_one_or_none()


# 导出单例
invitation_service = InvitationService()
