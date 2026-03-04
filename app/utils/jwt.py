"""JWT 工具模块
提供 JWT 令牌的签发、验证和解码功能

注意：JWT 的 exp 和 iat 字段必须使用 UTC 时间（JWT 国际标准规范）
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt

from app.config import settings
from app.utils.timezone import now


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    创建访问令牌（access_token）

    注意：JWT 的 exp 必须使用 UTC 时间戳（国际标准）

    Args:
        data: 要编码的数据（通常包含用户 uid）
        expires_delta: 自定义过期时间，默认 15 分钟

    Returns:
        str: JWT 令牌字符串
    """
    to_encode = data.copy()

    # JWT exp 必须使用 UTC 时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),  # 签发时间也使用 UTC
        "type": "access",  # 令牌类型
    })

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def get_token_jti(token: str) -> str:
    """
    计算令牌的 JTI（JWT ID）

    使用 SHA256 哈希生成唯一标识符，用于数据库索引和快速查找。
    注意：这是用于查找的标识符，不是用于验证的 bcrypt 哈希。

    Args:
        token: JWT 令牌字符串

    Returns:
        str: SHA256 哈希值（前 64 个字符）
    """
    return hashlib.sha256(token.encode()).hexdigest()


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    创建刷新令牌（refresh_token）

    注意：JWT 的 exp 必须使用 UTC 时间戳（国际标准）

    Args:
        data: 要编码的数据（通常包含 session_id）
        expires_delta: 自定义过期时间，默认 7 天

    Returns:
        str: JWT 令牌字符串
    """
    to_encode = data.copy()

    # JWT exp 必须使用 UTC 时间
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )

    # 先生成基础令牌（不含 jti）
    base_payload = to_encode.copy()
    base_payload.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),  # 签发时间也使用 UTC
        "type": "refresh",
    })

    # 编码获取临时令牌以计算 jti
    temp_token = jwt.encode(
        base_payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    # 计算 jti（令牌的 SHA256 哈希）
    token_jti = get_token_jti(temp_token)

    # 添加 jti 到 payload 并重新编码
    base_payload["jti"] = token_jti

    return jwt.encode(
        base_payload,
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

    注意：JWT 中存储的是 UTC 时间戳，返回时转换为上海时间

    Args:
        token: JWT 令牌字符串

    Returns:
        Optional[datetime]: 过期时间（上海时间，naive），解码失败返回 None
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        exp = payload.get("exp")
        if exp:
            # JWT exp 是 UTC 时间戳，转换为上海时间返回
            from app.utils.timezone import SHANGHAI_TZ
            return datetime.fromtimestamp(exp, tz=timezone.utc).astimezone(SHANGHAI_TZ).replace(tzinfo=None)
        return None
    except JWTError:
        return None


def is_token_expired(token: str) -> bool:
    """
    检查令牌是否已过期

    注意：python-jose 在解码时会自动验证 exp（与 UTC 对比）
    此函数仅用于额外的检查

    Args:
        token: JWT 令牌字符串

    Returns:
        bool: 是否已过期
    """
    try:
        # python-jose 会自动验证 exp，如果过期会抛出 JWTError
        jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return False
    except JWTError:
        return True
