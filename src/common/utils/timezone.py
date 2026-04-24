"""Timezone helpers for business datetimes.

Business datetimes are stored as naive values whose wall-clock meaning is
Asia/Shanghai. API payloads include the +08:00 offset so clients do not reinterpret
those values in the browser or server local timezone.
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


def to_shanghai_naive(dt: datetime | None) -> datetime | None:
    """Normalize a datetime to the project's Shanghai-naive storage contract."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(SHANGHAI_TZ).replace(tzinfo=None)


def format_iso(dt: datetime | None) -> str | None:
    """Serialize a business datetime as ISO 8601 with explicit +08:00 offset."""
    if dt is None:
        return None
    shanghai_dt = to_shanghai_naive(dt)
    return shanghai_dt.replace(tzinfo=SHANGHAI_TZ).isoformat(timespec="seconds")
