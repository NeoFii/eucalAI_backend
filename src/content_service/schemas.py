"""Schemas for content-service public and internal APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_serializer

from common.utils.timezone import format_iso


class DateTimeModel(BaseModel):
    """Serialize datetimes as ISO strings."""

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = format_iso(value)
        return data


class BaseResponse(BaseModel):
    """Common API response wrapper."""

    code: int = Field(default=200)
    message: str = Field(default="success")


class CreateNewsRequest(BaseModel):
    """Create news request."""

    title: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    summary: Optional[str] = Field(default=None, max_length=500)
    cover_image: Optional[str] = Field(default=None, max_length=500)
    content: str
    status: int = Field(default=0, ge=0, le=3)
    published_at: Optional[datetime] = None
    author_id: Optional[int] = None


class UpdateNewsRequest(BaseModel):
    """Update news request."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=255)
    summary: Optional[str] = Field(default=None, max_length=500)
    cover_image: Optional[str] = Field(default=None, max_length=500)
    content: Optional[str] = None
    status: Optional[int] = Field(default=None, ge=0, le=3)
    published_at: Optional[datetime] = None


class DestroyNewsRequest(BaseModel):
    """Destroy news request."""

    deleted_by_admin_id: Optional[int] = None


class NewsData(DateTimeModel):
    """News payload."""

    uid: str
    language: Optional[str] = None
    title: str
    slug: str
    summary: Optional[str] = None
    cover_image: Optional[str] = None
    content: Optional[str] = None
    status: int
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class NewsListItem(DateTimeModel):
    """News list item."""

    uid: str
    language: Optional[str] = None
    title: str
    slug: str
    summary: Optional[str] = None
    cover_image: Optional[str] = None
    status: int
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class NewsListResponseData(BaseModel):
    """News list payload."""

    items: list[NewsListItem]
    total: int
    page: int
    page_size: int


class NewsResponse(BaseResponse):
    """Single news response."""

    data: Optional[NewsData] = None


class NewsListResponse(BaseResponse):
    """News list response."""

    data: Optional[NewsListResponseData] = None


class PublicNewsListItem(DateTimeModel):
    """Public news list item."""

    uid: int
    title: str
    slug: str
    summary: Optional[str] = None
    cover_image: Optional[str] = None
    published_at: Optional[datetime] = None


class PublicNewsListResponseData(BaseModel):
    """Public news list payload."""

    items: list[PublicNewsListItem]
    total: int
    page: int
    page_size: int


class PublicNewsListResponse(BaseResponse):
    """Public news list response."""

    data: PublicNewsListResponseData


class PublicNewsData(DateTimeModel):
    """Public news detail payload."""

    uid: int
    title: str
    slug: str
    summary: Optional[str] = None
    cover_image: Optional[str] = None
    content: str
    status: int
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PublicNewsResponse(BaseResponse):
    """Public news response."""

    data: PublicNewsData
