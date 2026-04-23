from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_32bytes_long!!")
os.environ.setdefault("INTERNAL_SECRET", "test_internal_secret_32chars_long!")
os.environ.setdefault("ADMIN_DATABASE_URL", "mysql+aiomysql://root:pw@localhost/admin")


def test_catalog_service_serializes_supported_model_with_vendor_and_categories():
    from admin_service.models import (
        ModelCategory,
        ModelVendor,
        SupportedModel,
        SupportedModelCategoryMap,
    )
    from admin_service.services.model_catalog_service import ModelCatalogService

    vendor = ModelVendor(
        id=1,
        slug="deepseek",
        name="DeepSeek",
        logo_url="/icons/providers/deepseek.png",
        is_active=True,
        sort_order=10,
    )
    reasoning = ModelCategory(
        id=1,
        key="reasoning",
        name="Reasoning",
        sort_order=1,
        is_active=True,
    )
    coding = ModelCategory(
        id=2,
        key="coding",
        name="Coding",
        sort_order=2,
        is_active=True,
    )
    model = SupportedModel(
        id=1,
        slug="deepseek-v3-2",
        name="DeepSeek-V3.2",
        vendor=vendor,
        summary="General-purpose flagship for coding workflows",
        description="DeepSeek latest general-purpose chat model",
        price_input_per_m_fen=120,
        price_output_per_m_fen=240,
        capability_tags=["chat", "coding", "reasoning"],
        context_window=128000,
        max_output_tokens=8192,
        is_reasoning_model=False,
        is_active=True,
        sort_order=20,
    )
    model.category_links = [
        SupportedModelCategoryMap(id=1, category=reasoning, sort_order=1),
        SupportedModelCategoryMap(id=2, category=coding, sort_order=2),
    ]

    item = ModelCatalogService._model_item(model, detail=True)

    assert item.slug == "deepseek-v3-2"
    assert item.name == "DeepSeek-V3.2"
    assert item.vendor.slug == "deepseek"
    assert item.summary == "General-purpose flagship for coding workflows"
    assert item.description == "DeepSeek latest general-purpose chat model"
    assert item.price_input_per_m_fen == 120
    assert item.price_output_per_m_fen == 240
    assert item.capability_tags == ["chat", "coding", "reasoning"]
    assert [category.key for category in item.categories] == ["reasoning", "coding"]
    assert item.offerings == []


async def _fake_list_vendors(db, *, page, page_size, active_only):
    from admin_service.schemas.model_catalog import ModelVendorItem

    assert db == "db"
    assert (page, page_size, active_only) == (1, 100, True)
    return [
        ModelVendorItem(
            id=1,
            slug="deepseek",
            name="DeepSeek",
            logo_url=None,
            is_active=True,
            sort_order=10,
        )
    ], 1


async def _fake_list_categories(db, *, page, page_size, active_only):
    from admin_service.schemas.model_catalog import ModelCategoryItem

    assert db == "db"
    assert (page, page_size, active_only) == (1, 100, True)
    return [
        ModelCategoryItem(
            id=1,
            key="reasoning",
            name="Reasoning",
            sort_order=1,
            is_active=True,
        )
    ], 1


async def _fake_list_models(db, **kwargs):
    from admin_service.schemas.model_catalog import (
        ModelCategoryBrief,
        ModelVendorBrief,
        SupportedModelItem,
    )

    assert db == "db"
    assert kwargs == {
        "category": "reasoning",
        "vendors": ["deepseek"],
        "q": "V3.2",
        "page": 1,
        "page_size": 20,
        "active_only": True,
    }
    return [
        SupportedModelItem(
            id=1,
            slug="deepseek-v3-2",
            name="DeepSeek-V3.2",
            summary="General-purpose flagship for coding workflows",
            description=None,
            price_input_per_m_fen=120,
            price_output_per_m_fen=240,
            capability_tags=["chat"],
            context_window=128000,
            max_output_tokens=8192,
            is_reasoning_model=False,
            sort_order=20,
            vendor=ModelVendorBrief(id=1, slug="deepseek", name="DeepSeek"),
            categories=[ModelCategoryBrief(key="reasoning", name="Reasoning", sort_order=1)],
        )
    ], 1


async def _fake_create_model(db, payload, **kwargs):
    from admin_service.schemas.model_catalog import (
        ModelCategoryBrief,
        ModelVendorBrief,
        SupportedModelDetail,
    )

    assert db == "db"
    assert payload.slug == "deepseek-r1"
    return SupportedModelDetail(
        id=2,
        slug=payload.slug,
        name=payload.name,
        summary=payload.summary,
        description=payload.description,
        price_input_per_m_fen=payload.price_input_per_m_fen,
        price_output_per_m_fen=payload.price_output_per_m_fen,
        capability_tags=payload.capability_tags,
        context_window=payload.context_window,
        max_output_tokens=payload.max_output_tokens,
        is_reasoning_model=payload.is_reasoning_model,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
        vendor=ModelVendorBrief(id=1, slug="deepseek", name="DeepSeek"),
        categories=[ModelCategoryBrief(key="reasoning", name="Reasoning", sort_order=1)],
        offerings=[],
    )


async def _fake_update_model(db, slug, payload, **kwargs):
    from admin_service.schemas.model_catalog import (
        ModelCategoryBrief,
        ModelVendorBrief,
        SupportedModelDetail,
    )

    assert db == "db"
    assert slug == "deepseek-r1"
    return SupportedModelDetail(
        id=2,
        slug=slug,
        name=payload.name or "DeepSeek-R1",
        summary=payload.summary,
        description=payload.description,
        price_input_per_m_fen=payload.price_input_per_m_fen,
        price_output_per_m_fen=payload.price_output_per_m_fen,
        capability_tags=payload.capability_tags or ["reasoning"],
        context_window=payload.context_window or 128000,
        max_output_tokens=payload.max_output_tokens or 8192,
        is_reasoning_model=payload.is_reasoning_model if payload.is_reasoning_model is not None else True,
        is_active=payload.is_active if payload.is_active is not None else True,
        sort_order=payload.sort_order or 30,
        vendor=ModelVendorBrief(id=1, slug="deepseek", name="DeepSeek"),
        categories=[ModelCategoryBrief(key="reasoning", name="Reasoning", sort_order=1)],
        offerings=[],
    )


async def _fake_get_model(db, slug, *, active_only):
    from admin_service.schemas.model_catalog import (
        ModelCategoryBrief,
        ModelVendorBrief,
        SupportedModelDetail,
    )

    assert db == "db"
    assert slug == "deepseek-v3-2"
    assert active_only is True
    return SupportedModelDetail(
        id=1,
        slug=slug,
        name="DeepSeek-V3.2",
        summary="General-purpose flagship for coding workflows",
        description="Full detail body for detail page",
        price_input_per_m_fen=120,
        price_output_per_m_fen=240,
        capability_tags=["chat"],
        context_window=128000,
        max_output_tokens=8192,
        is_reasoning_model=False,
        is_active=True,
        sort_order=20,
        vendor=ModelVendorBrief(id=1, slug="deepseek", name="DeepSeek"),
        categories=[ModelCategoryBrief(key="reasoning", name="Reasoning", sort_order=1)],
        offerings=[],
    )


@pytest.mark.asyncio
async def test_public_catalog_endpoints_delegate_filters_and_wrap_responses(monkeypatch):
    from admin_service.api.v1.endpoints import model_catalog

    monkeypatch.setattr(
        model_catalog.ModelCatalogService,
        "list_vendors",
        staticmethod(_fake_list_vendors),
    )
    monkeypatch.setattr(
        model_catalog.ModelCatalogService,
        "list_categories",
        staticmethod(_fake_list_categories),
    )
    monkeypatch.setattr(
        model_catalog.ModelCatalogService,
        "list_models",
        staticmethod(_fake_list_models),
    )
    monkeypatch.setattr(
        model_catalog.ModelCatalogService,
        "get_model_by_slug",
        staticmethod(_fake_get_model),
    )

    vendors = await model_catalog.list_model_vendors(page=1, page_size=100, db="db")
    categories = await model_catalog.list_model_categories(page=1, page_size=100, db="db")
    models = await model_catalog.list_supported_models(
        category="reasoning",
        vendors="deepseek",
        q="V3.2",
        page=1,
        page_size=20,
        db="db",
    )
    detail = await model_catalog.get_supported_model(slug="deepseek-v3-2", db="db")

    assert vendors.data.items[0].slug == "deepseek"
    assert categories.data.items[0].key == "reasoning"
    assert models.data.items[0].name == "DeepSeek-V3.2"
    assert models.data.items[0].summary == "General-purpose flagship for coding workflows"
    assert models.data.items[0].price_input_per_m_fen == 120
    assert detail.data.offerings == []
    assert detail.data.description == "Full detail body for detail page"
    assert detail.data.price_output_per_m_fen == 240


@pytest.mark.asyncio
async def test_admin_catalog_create_model_delegates_to_service(monkeypatch):
    from admin_service.api.v1.endpoints import model_catalog_admin
    from admin_service.models import AdminUser
    from admin_service.schemas.model_catalog import SupportedModelCreate

    monkeypatch.setattr(
        model_catalog_admin.ModelCatalogService,
        "create_model",
        staticmethod(_fake_create_model),
    )
    current_admin = AdminUser(
        id=1,
        uid=99,
        email="super@example.com",
        password_hash="hash",
        name="Super",
        role="super_admin",
        status=1,
    )

    mock_request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "test"},
    )

    response = await model_catalog_admin.create_supported_model(
        payload=SupportedModelCreate(
            slug="deepseek-r1",
            name="DeepSeek-R1",
            vendor_slug="deepseek",
            summary="Reasoning-first model card summary",
            description="Reasoning model",
            price_input_per_m_fen=321,
            price_output_per_m_fen=654,
            capability_tags=["reasoning"],
            context_window=128000,
            max_output_tokens=8192,
            is_reasoning_model=True,
            is_active=True,
            sort_order=30,
            category_keys=["reasoning"],
        ),
        http_request=mock_request,
        current_admin=current_admin,
        db="db",
    )

    assert response.data.slug == "deepseek-r1"
    assert response.data.summary == "Reasoning-first model card summary"
    assert response.data.price_input_per_m_fen == 321
    assert response.data.price_output_per_m_fen == 654
    assert response.data.vendor.slug == "deepseek"
    assert [category.key for category in response.data.categories] == ["reasoning"]


@pytest.mark.asyncio
async def test_admin_catalog_update_model_accepts_summary_and_fen_fields(monkeypatch):
    from admin_service.api.v1.endpoints import model_catalog_admin
    from admin_service.models import AdminUser
    from admin_service.schemas.model_catalog import SupportedModelUpdate

    monkeypatch.setattr(
        model_catalog_admin.ModelCatalogService,
        "update_model",
        staticmethod(_fake_update_model),
    )
    current_admin = AdminUser(
        id=1,
        uid=99,
        email="super@example.com",
        password_hash="hash",
        name="Super",
        role="super_admin",
        status=1,
    )

    mock_request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "test"},
    )

    response = await model_catalog_admin.update_supported_model(
        slug="deepseek-r1",
        payload=SupportedModelUpdate(
            summary="更新后的卡片摘要",
            description="更新后的详情正文",
            price_input_per_m_fen=888,
            price_output_per_m_fen=999,
        ),
        http_request=mock_request,
        current_admin=current_admin,
        db="db",
    )

    assert response.data.slug == "deepseek-r1"
    assert response.data.summary == "更新后的卡片摘要"
    assert response.data.description == "更新后的详情正文"
    assert response.data.price_input_per_m_fen == 888
    assert response.data.price_output_per_m_fen == 999
