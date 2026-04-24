"""
工具函数模块
提供各种辅助功能
"""

# 时区工具
from common.utils.timezone import now, now_with_tz, utc_to_shanghai, format_iso

# 雪花 ID 生成
from common.utils.snowflake import (
    SnowflakeIDGenerator,
    generate_snowflake_id,
    get_snowflake_generator,
)

# NanoID UID 生成
from common.utils.nanoid_uid import generate_nanoid_uid

# 密码工具
from common.utils.password import (
    hash_password,
    verify_password,
)

# JWT 工具
from common.utils.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_jti,
)

# 加密工具
from common.utils.crypto import (
    encrypt_api_key,
    decrypt_api_key,
    mask_api_key,
)

__all__ = [
    # 时区
    "now",
    "now_with_tz",
    "utc_to_shanghai",
    "format_iso",
    # 雪花 ID
    "SnowflakeIDGenerator",
    "generate_snowflake_id",
    "get_snowflake_generator",
    # NanoID UID
    "generate_nanoid_uid",
    # 密码
    "hash_password",
    "verify_password",
    # JWT
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_token_jti",
    # 加密
    "encrypt_api_key",
    "decrypt_api_key",
    "mask_api_key",
]
