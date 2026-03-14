from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_content_admin_news_create_serializes_uid_as_string(monkeypatch):
    from content_service.api.v1.endpoints.admin_news import create_news
    from content_service.schemas import CreateNewsRequest

    async def fake_create(**kwargs):
        assert kwargs["author_id"] == 1
        return SimpleNamespace(
            uid=123456789,
            language="zh",
            title=kwargs["title"],
            slug=kwargs["slug"],
            summary=kwargs.get("summary"),
            cover_image=kwargs.get("cover_image"),
            content=kwargs["content"],
            status=kwargs.get("status", 0),
            published_at=kwargs.get("published_at"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    monkeypatch.setattr("content_service.api.v1.endpoints.admin_news.NewsService.create", fake_create)

    response = await create_news(
        request=CreateNewsRequest(title="title", slug="slug", content="content"),
        current_admin=SimpleNamespace(id=1, uid=99, role="super_admin", status=1),
        db=object(),
    )

    assert response.data.uid == "123456789"


@pytest.mark.asyncio
async def test_content_admin_news_update_serializes_uid_as_string(monkeypatch):
    from content_service.api.v1.endpoints.admin_news import update_news
    from content_service.schemas import UpdateNewsRequest

    async def fake_update(**kwargs):
        assert kwargs["uid"] == 123456789
        return SimpleNamespace(
            uid=123456789,
            language="zh",
            title=kwargs.get("title", "title"),
            slug=kwargs.get("slug") or "slug",
            summary=kwargs.get("summary"),
            cover_image=kwargs.get("cover_image"),
            content=kwargs.get("content") or "content",
            status=kwargs.get("status") if kwargs.get("status") is not None else 0,
            published_at=kwargs.get("published_at"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    monkeypatch.setattr("content_service.api.v1.endpoints.admin_news.NewsService.update", fake_update)

    response = await update_news(
        uid=123456789,
        request=UpdateNewsRequest(title="new title"),
        current_admin=SimpleNamespace(id=1, uid=99, role="super_admin", status=1),
        db=object(),
    )

    assert response.data.uid == "123456789"
