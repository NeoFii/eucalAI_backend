"""
内部 API 端点
供用户服务调用的内部接口
"""

import logging

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.exceptions import InvalidInvitationCodeException, ServiceUnavailableException
from admin.dependencies import get_db_session
from admin.services.invitation_service import InvitationCodeService
from admin.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["内部接口"])


async def verify_internal_secret(x_internal_secret: str = Header(...)) -> None:
    """验证内部调用密钥"""
    if x_internal_secret != settings.INTERNAL_SECRET:
        raise ServiceUnavailableException("内部服务密钥验证失败")


class InternalVerifyResponse(BaseModel):
    """内部验证响应"""
    success: bool
    message: str


@router.post(
    "/invitation-codes/verify-and-use",
    response_model=InternalVerifyResponse,
    summary="验证并使用邀请码",
    description="供用户服务内部调用的接口",
)
async def verify_and_use_invitation_code(
    request: Request,
    x_internal_secret: str = Header(...),
    db: AsyncSession = Depends(get_db_session),
) -> InternalVerifyResponse:
    """
    验证并使用邀请码

    内部接口，供用户服务在用户注册时调用
    """
    # 验证内部密钥
    await verify_internal_secret(x_internal_secret)

    body = await request.json()
    code = body.get("code")
    used_by = body.get("used_by")

    if not code or not used_by:
        raise InvalidInvitationCodeException()

    try:
        await InvitationCodeService.verify_and_use(db, code, used_by)
        return InternalVerifyResponse(
            success=True,
            message="邀请码验证成功",
        )
    except Exception as e:
        logger.error(f"验证邀请码失败: {e}")
        raise
