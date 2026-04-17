"""时区工具模块 - 统一使用上海时区 (UTC+8)

本模块提供统一的时间获取和转换函数，确保全系统使用上海时区（北京时间）。
数据库存储为不带时区的 naive datetime，但值本身代表上海时间。
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# 上海时区常量
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    """获取当前上海时区时间（不带时区信息的 naive datetime）

    返回的 datetime 对象没有 tzinfo，但值本身代表上海时间。
    这种格式可以直接存入数据库，无需额外转换。

    Returns:
        datetime: 当前上海时间（naive datetime）
    """
    return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)


def now_with_tz() -> datetime:
    """获取当前上海时区时间（带时区信息的 aware datetime）

    返回的 datetime 对象包含时区信息，用于需要时区感知的计算。

    Returns:
        datetime: 当前上海时间（aware datetime）
    """
    return datetime.now(SHANGHAI_TZ)


def utc_to_shanghai(dt: datetime) -> datetime:
    """将 UTC 时间转换为上海时间（不带时区信息）

    用于将外部 UTC 时间转换为内部使用的上海时间。

    Args:
        dt: 输入的时间（可以是 UTC 或其他时区）

    Returns:
        datetime: 上海时间（naive datetime）
    """
    if dt.tzinfo is None:
        # 假设输入是 UTC 时间，先添加 UTC 时区
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SHANGHAI_TZ).replace(tzinfo=None)


def format_iso(dt: datetime | None) -> str | None:
    """将 datetime 格式化为 ISO 8601 字符串（不带时区后缀）

    用于 API 响应中的时间字段序列化。

    Args:
        dt: datetime 对象，可为 None

    Returns:
        ISO 8601 格式字符串（如 "2026-03-04T13:43:20"），或 None
    """
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S")
