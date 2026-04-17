"""News model owned by the content service."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Index, SmallInteger, String, Text, UniqueConstraint

from content_service.db import Base
from common.db.base import SnowflakeIdMixin, TimestampMixin


class News(Base, SnowflakeIdMixin, TimestampMixin):
    """News article."""

    __tablename__ = "news"

    language = None

    __table_args__ = (
        Index("idx_status_published", "status", "published_at"),
        Index("idx_news_deleted_at", "deleted_at"),
        UniqueConstraint("slug", name="uk_news_slug"),
    )

    uid = Column(BigInteger, unique=True, nullable=False, index=True, comment="Public news UID")
    title = Column(String(255), nullable=False, comment="Title")
    slug = Column(String(255), nullable=False, index=True, comment="Slug")
    summary = Column(String(500), nullable=True, comment="Summary")
    cover_image = Column(String(500), nullable=True, comment="Cover image URL")
    content = Column(Text(collation="utf8mb4_unicode_ci"), nullable=False, comment="Markdown content")
    status = Column(SmallInteger, default=0, nullable=False, comment="0=draft 1=published 2=offline 3=deleted")
    published_at = Column(DateTime, nullable=True, comment="Published at")
    author_id = Column(BigInteger, nullable=True, comment="Author admin id")
    deleted_at = Column(DateTime, nullable=True, comment="Soft delete time")
    deleted_by_admin_id = Column(BigInteger, nullable=True, comment="Soft delete operator admin id")

    def __repr__(self) -> str:
        return f"<News(uid={self.uid}, title={self.title}, status={self.status})>"

    @property
    def is_published(self) -> bool:
        return self.status == 1 and self.deleted_at is None

    @property
    def is_draft(self) -> bool:
        return self.status == 0 and self.deleted_at is None

    @property
    def is_offline(self) -> bool:
        return self.status == 2 and self.deleted_at is None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None or self.status == 3
