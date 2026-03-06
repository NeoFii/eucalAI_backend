"""
SQLAlchemy 基础模型
提供 declarative base 和通用字段
"""

from sqlalchemy import Column, BigInteger, DateTime
from sqlalchemy.orm import declarative_base

from common.utils.timezone import now

# 创建声明性基类
Base = declarative_base()


class TimestampMixin:
    """
    时间戳混入类
    提供 created_at 和 updated_at 字段
    使用上海时区 (UTC+8)
    """

    created_at = Column(
        DateTime,
        default=now,
        nullable=False,
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        default=now,
        onupdate=now,
        nullable=False,
        comment="更新时间",
    )


class SnowflakeIdMixin:
    """
    雪花 ID 混入类
    提供 id 主键字段（使用自增 ID）
    注意：对外使用 uid（雪花 ID），内部关联使用自增 id
    """

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        index=True,
        comment="内部主键",
    )
