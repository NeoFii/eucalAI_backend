"""
管理服务内部 API 客户端
用于用户服务调用管理服务的内部接口
"""

import logging
from typing import Optional

import httpx

from user.config import settings
from common.core.exceptions import (
    InvalidInvitationCodeException,
    InvitationCodeDisabledException,
    InvitationCodeExpiredException,
    InvitationCodeUsedException,
    ServiceUnavailableException,
)

logger = logging.getLogger(__name__)

# 内部 API 超时（秒）
INTERNAL_API_TIMEOUT = 3.0


async def verify_and_use_invitation_code(code: str, used_by_uid: int) -> None:
    """
    验证并核销邀请码

    调用管理服务内部接口验证邀请码有效性并标记为已使用。

    Args:
        code: 邀请码字符串
        used_by_uid: 使用者用户 UID

    Raises:
        InvalidInvitationCodeException: 邀请码无效
        InvitationCodeUsedException: 邀请码已被使用
        InvitationCodeDisabledException: 邀请码已被弃用
        InvitationCodeExpiredException: 邀请码已过期
        ServiceUnavailableException: 管理服务不可用
    """
    url = f"{settings.ADMIN_SERVICE_URL}/internal/invitation-codes/verify-and-use"
    headers = {
        "X-Internal-Secret": settings.INTERNAL_SECRET,
        "Content-Type": "application/json",
    }
    payload = {
        "code": code,
        "used_by_uid": used_by_uid,
    }

    try:
        async with httpx.AsyncClient(timeout=INTERNAL_API_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        logger.error(f"调用管理服务验证邀请码超时: code={code[:8]}...")
        raise ServiceUnavailableException("服务暂时不可用，请稍后重试")
    except httpx.NetworkError as e:
        logger.error(f"调用管理服务验证邀请码网络错误: {e}")
        raise ServiceUnavailableException("服务暂时不可用，请稍后重试")

    if response.status_code == 403:
        logger.error("内部 API 密钥验证失败")
        raise ServiceUnavailableException("服务配置错误")

    if response.status_code != 200:
        logger.error(f"管理服务返回错误: {response.status_code}")
        raise ServiceUnavailableException("服务暂时不可用，请稍后重试")

    data = response.json()

    if data.get("success"):
        return

    # 根据错误类型抛出对应异常
    error = data.get("error", "unknown")
    error_map = {
        "invalid": InvalidInvitationCodeException,
        "used": InvitationCodeUsedException,
        "disabled": InvitationCodeDisabledException,
        "expired": InvitationCodeExpiredException,
    }

    exception_class = error_map.get(error, InvalidInvitationCodeException)
    raise exception_class()


async def get_invitation_code_stats() -> dict:
    """
    获取邀请码统计信息（用于仪表盘）

    Returns:
        dict: 邀请码统计信息

    Raises:
        ServiceUnavailableException: 管理服务不可用
    """
    url = f"{settings.ADMIN_SERVICE_URL}/internal/invitation-codes/stats"
    headers = {
        "X-Internal-Secret": settings.INTERNAL_SECRET,
    }

    try:
        async with httpx.AsyncClient(timeout=INTERNAL_API_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        logger.error("获取邀请码统计超时")
        raise ServiceUnavailableException("服务暂时不可用")
    except httpx.NetworkError:
        logger.error("获取邀请码统计网络错误")
        raise ServiceUnavailableException("服务暂时不可用")

    if response.status_code != 200:
        logger.error(f"获取邀请码统计失败: {response.status_code}")
        raise ServiceUnavailableException("服务暂时不可用")

    return response.json()
