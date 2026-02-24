"""
JWT 工具模块
提供 JWT 令牌的签发、验证和解码功能
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt

from app.config import settings


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    创建访问令牌（access_token）

    Args:
        data: 要编码的数据（通常包含用户 uid）
        expires_delta: 自定义过期时间，默认 15 分钟

    Returns:
        str: JWT 令牌字符串
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),  # 签发时间
        "type": "access",  # 令牌类型
    })

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    创建刷新令牌（refresh_token）

    Args:
        data: 要编码的数据（通常包含 session_id）
        expires_delta: 自定义过期时间，默认 7 天

    Returns:
        str: JWT 令牌字符串
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    })

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> Optional[dict]:
    """
    解码并验证 JWT 令牌

    Args:
        token: JWT 令牌字符串

    Returns:
        Optional[dict]: 解码后的数据，验证失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        return None


def verify_access_token(token: str) -> Optional[dict]:
    """
    验证访问令牌

    检查：
    1. 令牌是否有效
    2. 令牌类型是否为 access

    Args:
        token: JWT 令牌字符串

    Returns:
        Optional[dict]: 解码后的数据，验证失败返回 None
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # 检查令牌类型
    if payload.get("type") != "access":
        return None

    return payload


def verify_refresh_token(token: str) -> Optional[dict]:
    """
    验证刷新令牌

    检查：
    1. 令牌是否有效
    2. 令牌类型是否为 refresh

    Args:
        token: JWT 令牌字符串

    Returns:
        Optional[dict]: 解码后的数据，验证失败返回 None
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # 检查令牌类型
    if payload.get("type") != "refresh":
        return None

    return payload


def get_token_expiry(token: str) -> Optional[datetime]:
    """
    获取令牌过期时间

    Args:
        token: JWT 令牌字符串

    Returns:
        Optional[datetime]: 过期时间，解码失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(exp, tz=timezone.utc)
        return None
    except JWTError:
        return None


def is_token_expired(token: str) -> bool:
    """
    检查令牌是否已过期

    Args:
        token: JWT 令牌字符串

    Returns:
        bool: 是否已过期
    """
    expiry = get_token_expiry(token)
    if expiry is None:
        return True
    return datetime.now(timezone.utc) > expiry
