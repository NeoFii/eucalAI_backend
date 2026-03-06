"""
管理员仪表盘端点
提供统计数据接口
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from admin.dependencies import get_current_admin, get_db_session
from admin.models import AdminUser
from admin.models.invitation_code import InvitationCode
from user.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["管理员仪表盘"])


@router.get(
    "/dashboard/stats",
    summary="获取仪表盘统计数据",
    description="获取用户总数、邀请码统计等数据",
)
async def get_stats(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """获取仪表盘统计数据"""
    # 用户总数
    user_count_result = await db.execute(select(func.count(User.id)))
    total_users = user_count_result.scalar() or 0

    # 邀请码总数
    invite_count_result = await db.execute(select(func.count(InvitationCode.id)))
    total_invitation_codes = invite_count_result.scalar() or 0

    # 已使用邀请码数量
    used_count_result = await db.execute(
        select(func.count(InvitationCode.id)).where(InvitationCode.status == 1)
    )
    used_invitation_codes = used_count_result.scalar() or 0

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "total_users": total_users,
            "total_invitation_codes": total_invitation_codes,
            "used_invitation_codes": used_invitation_codes,
        },
    }
