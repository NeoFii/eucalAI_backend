"""Integration + unit tests for the model catalog read service (USER-05).

Covers VALIDATION slots:
- T-04-18 (test_cache_hits): second call with identical inputs hits the
  Redis cache and does NOT re-invoke the underlying repository.
- T-04-19 (test_filter): GET /api/v1/models forwards vendor + q query
  params to ModelCatalogReadService.list_models as kwargs.
- T-04-20 (test_404): GET /api/v1/models/{slug} surfaces a 404 when the
  service raises NotFoundException.

All tests rely on AsyncMock + dependency_overrides + ASGITransport (no real
DB / Redis / network).
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
os.environ.setdefault("INTERNAL_SECRET", "test-internal-secret-at-least-32-characters-long")

from app.common.core.exceptions import NotFoundException  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.service.model_catalog_service import (  # noqa: E402
    ModelCatalogReadService,
)


@pytest_asyncio.fixture
async def client():
    """ASGI test client with mocked DB dependency. Cleans up overrides on exit."""

    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class _DictBackedRedis:
    """Tiny in-memory stand-in for the cache Redis client.

    Mirrors the subset of the ``redis.asyncio.Redis`` interface used by
    ``cache_get_or_fetch`` (``get`` / ``set`` — both awaitable) without needing
    a live Redis server. Each instance has its own private dict so concurrent
    tests cannot leak state across one another.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):  # noqa: ARG002
        self._store[key] = value
        return True


@pytest.mark.asyncio
async def test_cache_hits():
    """T-04-18 — Two calls to ``ModelCatalogReadService.list_vendors`` with
    identical paging args MUST hit the cache on the second call. The
    underlying ``ModelVendorRepository.list_vendors`` is invoked exactly once
    across both calls; the second call returns the cached payload without
    touching the DB.
    """
    db = AsyncMock()
    fake_redis = _DictBackedRedis()

    vendor = MagicMock()
    vendor.id = 1
    vendor.slug = "openai"
    vendor.name = "OpenAI"
    vendor.logo_url = None
    vendor.is_active = True
    vendor.sort_order = 1
    vendor.created_at = None
    vendor.updated_at = None

    with patch(
        "app.common.infra.cache.get_cache_redis",
        return_value=fake_redis,
    ), patch(
        "app.service.model_catalog_service.ModelVendorRepository"
    ) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.list_vendors = AsyncMock(return_value=([vendor], 1))
        mock_repo_cls.return_value = mock_repo

        # First call — cache miss, repo invoked.
        payload1 = await ModelCatalogReadService.list_vendors(db, page=1, page_size=100)
        assert mock_repo.list_vendors.call_count == 1, (
            "first call must trigger repository fetch"
        )
        assert payload1["total"] == 1
        assert payload1["page"] == 1
        assert payload1["page_size"] == 100
        assert payload1["items"][0]["slug"] == "openai"

        # Second call with identical args — cache hit, repo NOT invoked again.
        payload2 = await ModelCatalogReadService.list_vendors(db, page=1, page_size=100)
        assert mock_repo.list_vendors.call_count == 1, (
            "cache miss on second identical call: cache layer not wired "
            f"correctly (repo.list_vendors called {mock_repo.list_vendors.call_count} "
            "times)"
        )
        # The cache returned the same shape — JSON round-tripped through the
        # fake Redis preserves the payload contract.
        assert payload2 == payload1

        # active_only=True invariant (D-04) — every repo call must pass it.
        for call in mock_repo.list_vendors.call_args_list:
            _, kwargs = call
            assert kwargs.get("active_only") is True, (
                "D-04 violated: user-facing list_vendors must use active_only=True"
            )


@pytest.mark.asyncio
@patch(
    "app.controller.model_catalog.ModelCatalogReadService.list_models",
    new_callable=AsyncMock,
)
async def test_filter(mock_list_models, client):
    """T-04-19 — GET /api/v1/models?vendor=openai&q=gpt-4 forwards the
    parsed query params to ``ModelCatalogReadService.list_models`` as
    ``vendors=["openai"]`` and ``q="gpt-4"``.
    """
    mock_list_models.return_value = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 50,
    }

    resp = await client.get(
        "/api/v1/models",
        params={"vendor": "openai", "q": "gpt-4"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 50}

    # The controller invokes the service with kwargs (db is the first positional
    # argument). vendors must be the parsed list form because the controller
    # declares ``vendors: list[str] | None = Query(None, alias="vendor")``.
    assert mock_list_models.await_count == 1
    kwargs = mock_list_models.await_args.kwargs
    assert kwargs.get("q") == "gpt-4", f"unexpected q kwarg: {kwargs}"
    vendors_kwarg = kwargs.get("vendors")
    assert vendors_kwarg in (["openai"], ("openai",)), (
        f"vendor query param did not flow through as vendors kwarg: {kwargs}"
    )


@pytest.mark.asyncio
@patch(
    "app.controller.model_catalog.ModelCatalogReadService.get_model_by_slug",
    new_callable=AsyncMock,
)
async def test_404(mock_get_by_slug, client):
    """T-04-20 — GET /api/v1/models/{slug} returns HTTP 404 when the service
    raises NotFoundException. The slug pattern still accepts the input —
    ``nonexistent-slug`` satisfies ^[a-z0-9][a-z0-9._-]*$.
    """
    mock_get_by_slug.side_effect = NotFoundException(
        detail="Model not found: nonexistent-slug"
    )

    resp = await client.get("/api/v1/models/nonexistent-slug")

    assert resp.status_code == 404, resp.text
    body = resp.json()
    # The global exception handler maps NotFoundException -> {detail: "..."},
    # so the response body must surface our message verbatim.
    assert "nonexistent-slug" in (body.get("detail") or body.get("message") or "")
    # Service was invoked exactly once with the requested slug.
    assert mock_get_by_slug.await_count == 1
    args = mock_get_by_slug.await_args.args
    assert args[1] == "nonexistent-slug", (
        f"slug must be forwarded verbatim to service: {args}"
    )
