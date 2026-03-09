"""
新闻数据模型
定义 news 表结构
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, BigInteger, DateTime, SmallInteger, String, Text, Index

from common.db.base import Base, SnowflakeIdMixin, TimestampMixin

if TYPE_CHECKING:
    from admin.models.admin_user import AdminUser


class News(Base, SnowflakeIdMixin, TimestampMixin):
    """
    新闻表
    存储官网新闻内容，支持 Markdown 和双语
    """

    __tablename__ = "news"
    __table_args__ = (
        # 复合索引：语言 + 状态 + 发布时间
        Index("idx_language_status_published", "language", "status", "published_at"),
        # 复合索引：语言 + slug（确保同一语言下 slug 唯一）
        Index("idx_language_slug", "language", "slug", unique=True),
    )

    # 对外新闻 ID（雪花 ID）
    uid = Column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
        comment="对外新闻ID（雪花ID）",
    )

    # 语言：zh=中文 en=英文
    language = Column(
        String(10),
        default="zh",
        nullable=False,
        index=True,
        comment="语言: zh=中文 en=英文",
    )

    # 新闻标题
    title = Column(
        String(255),
        nullable=False,
        comment="新闻标题",
    )

    # URL 路径标识（同一语言内唯一，由 idx_language_slug 复合唯一索引保证）
    slug = Column(
        String(255),
        nullable=False,
        index=True,
        comment="URL路径标识",
    )

    # 摘要
    summary = Column(
        String(500),
        nullable=True,
        comment="摘要",
    )

    # 封面图 URL
    cover_image = Column(
        String(500),
        nullable=True,
        comment="封面图URL",
    )

    # Markdown 正文内容
    content = Column(
        Text(collation="utf8mb4_unicode_ci"),
        nullable=False,
        comment="Markdown正文内容",
    )

    # 新闻状态：0=草稿 1=已发布 2=已下线
    status = Column(
        SmallInteger,
        default=0,
        nullable=False,
        comment="状态：0=草稿 1=已发布 2=已下线",
    )

    # 发布时间
    published_at = Column(
        DateTime,
        nullable=True,
        comment="发布时间",
    )

    # 作者 ID（关联 admin_users.id）
    author_id = Column(
        BigInteger,
        nullable=True,
        comment="作者ID（关联admin_users.id）",
    )

    def __repr__(self) -> str:
        return f"<News(uid={self.uid}, title={self.title}, status={self.status})>"

    @property
    def is_published(self) -> bool:
        """检查新闻是否已发布"""
        return self.status == 1

    @property
    def is_draft(self) -> bool:
        """检查新闻是否为草稿"""
        return self.status == 0

    @property
    def is_offline(self) -> bool:
        """检查新闻是否已下线"""
        return self.status == 2
