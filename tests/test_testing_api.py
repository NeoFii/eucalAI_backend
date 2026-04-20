# -*- coding: utf-8 -*-`r`n"""Schema smoke tests for the testing service."""

from decimal import Decimal

import pytest
from pydantic import ValidationError


class TestTestingSchemas:
    def test_model_create_uses_canonical_fields(self):
        from testing_service.schemas import ModelCategoryAssign, ModelCreate

        model = ModelCreate(
            slug="gpt-4-turbo",
            name="GPT-4 Turbo",
            description="Advanced language model",
            context_window=128000,
            capability_tags=["text", "reasoning"],
            categories=[ModelCategoryAssign(category_id=1, sort_order=2)],
        )

        assert model.slug == "gpt-4-turbo"
        assert model.context_window == 128000
        assert model.capability_tags == ["text", "reasoning"]
        assert model.categories[0].category_id == 1

    def test_model_update_uses_canonical_fields(self):
        from testing_service.schemas import ModelUpdate

        update = ModelUpdate(
            name="Updated Model Name",
            description="Updated description",
            context_window=16384,
            capability_tags=["chat"],
        )

        assert update.name == "Updated Model Name"
        assert update.context_window == 16384
        assert update.capability_tags == ["chat"]

    def test_model_responses_use_canonical_fields(self):
        from testing_service.schemas import ModelCategoryBrief, ModelDetailResponse, ModelListItem

        category = ModelCategoryBrief(key="reasoning", name="Reasoning", sort_order=1)
        item = ModelListItem(
            id=1,
            slug="gpt-4",
            name="GPT-4",
            description="Advanced model",
            context_window=8192,
            capability_tags=["text"],
            categories=[category],
        )
        detail = ModelDetailResponse(
            id=1,
            slug="gpt-4",
            name="GPT-4",
            description="Advanced model",
            context_window=8192,
            capability_tags=["text"],
            categories=[category],
        )

        assert item.slug == "gpt-4"
        assert item.capability_tags == ["text"]
        assert item.categories[0].key == "reasoning"
        assert detail.slug == "gpt-4"
        assert detail.capability_tags == ["text"]

    def test_provider_schemas_use_slug(self):
        from testing_service.schemas import ProviderCreate, ProviderResponse, ProviderUpdate

        provider = ProviderCreate(
            slug="openai",
            name="OpenAI",
            logo_url="https://openai.com/logo.png",
            is_active=True,
        )
        response = ProviderResponse(
            id=1,
            slug="openai",
            name="OpenAI",
            logo_url="https://openai.com/logo.png",
            is_active=True,
        )
        update = ProviderUpdate(
            name="Updated Provider",
            logo_url="https://new-logo.com/logo.png",
            is_active=False,
        )

        assert provider.slug == "openai"
        assert response.slug == "openai"
        assert update.is_active is False

    def test_offering_create_keeps_current_public_shape(self):
        from testing_service.schemas import OfferingCreate

        offering = OfferingCreate(
            provider_id=1,
            price_input_per_m=Decimal("1.25"),
            price_output_per_m=Decimal("2.50"),
            provider_model_id="gpt-4.1",
        )

        assert offering.provider_id == 1
        assert offering.provider_model_id == "gpt-4.1"

    def test_legacy_model_alias_fields_are_rejected(self):
        from testing_service.schemas import ModelCreate, ModelUpdate

        with pytest.raises(ValidationError):
            ModelCreate(model_id="gpt-4", name="GPT-4")
        with pytest.raises(ValidationError):
            ModelCreate(slug="gpt-4", name="GPT-4", context_length=8192)
        with pytest.raises(ValidationError):
            ModelCreate(slug="gpt-4", name="GPT-4", tag_names=["text"])
        with pytest.raises(ValidationError):
            ModelCreate(slug="gpt-4", name="GPT-4", category_ids=[1, 2])
        with pytest.raises(ValidationError):
            ModelUpdate(context_length=8192)

    def test_legacy_provider_alias_fields_are_rejected(self):
        from testing_service.schemas import ProviderCreate, ProviderResponse

        with pytest.raises(ValidationError):
            ProviderCreate(provider_id="openai", name="OpenAI")
        with pytest.raises(ValidationError):
            ProviderResponse(id=1, provider_id="openai", name="OpenAI")

    def test_removed_compatibility_types_are_no_longer_exported(self):
        import testing_service.schemas as schemas

        for removed_name in (
            "CategoryCreate",
            "CategoryResponse",
            "CategoryUpdate",
            "ModelCategoryInfo",
            "ProviderWithModels",
            "BenchmarkRunRequest",
        ):
            assert not hasattr(schemas, removed_name)


'''
class TestCategorySchema:
    """濞村鐦崚鍡欒 Schema"""

    def test_category_create_with_required_fields(self):
        """濞村鐦箛鍛綖鐎涙顔"""
        from testing_service.schemas import CategoryCreate

        # 閹绘劒绶佃箛鍛綖鐎涙顔?
        category = CategoryCreate(
            name="Reasoning",
            slug="reasoning",
        )

        assert category.name == "Reasoning"
        assert category.slug == "reasoning"
        assert category.description is None

    def test_category_create_with_all_fields(self):
        """濞村鐦€瑰本鏆ｇ€涙顔"""
        from testing_service.schemas import CategoryCreate

        category = CategoryCreate(
            name="Programming",
            slug="programming",
            description="Programming tasks",
            icon="code",
            sort_order=2,
        )

        assert category.name == "Programming"
        assert category.slug == "programming"
        assert category.description == "Programming tasks"
        assert category.icon == "code"
        assert category.sort_order == 2

    def test_category_response_schema(self):
        """濞村鐦崚鍡欒閸濆秴绨?Schema"""
        from testing_service.schemas import CategoryResponse

        response = CategoryResponse(
            id=1,
            name="Test Category",
            slug="test-category",
            description="Test description",
            icon="test",
            sort_order=1,
        )

        assert response.id == 1
        assert response.name == "Test Category"
        assert response.slug == "test-category"

    def test_category_update_schema(self):
        """濞村鐦崚鍡欒閺囧瓨鏌?Schema"""
        from testing_service.schemas import CategoryUpdate

        update = CategoryUpdate(
            name="Updated Name",
            description="Updated description",
        )

        assert update.name == "Updated Name"
        assert update.description == "Updated description"


class TestModelSchema:
    """濞村鐦Ο鈥崇€?Schema"""

    def test_model_create_with_required_fields(self):
        """濞村鐦箛鍛綖鐎涙顔"""
        from testing_service.schemas import ModelCreate

        model = ModelCreate(
            model_id="gpt-4",
            name="GPT-4",
        )

        assert model.model_id == "gpt-4"
        assert model.name == "GPT-4"
        assert model.description is None

    def test_model_create_with_all_fields(self):
        """濞村鐦€瑰本鏆ｇ€涙顔"""
        from testing_service.schemas import ModelCreate

        model = ModelCreate(
            model_id="gpt-4-turbo",
            name="GPT-4 Turbo",
            description="Advanced language model",
            context_length=128000,
            model_size="large",
            is_open_source=False,
            is_active=True,
            category_ids=[1, 2],
            tag_names=["text", "reasoning"],
        )

        assert model.model_id == "gpt-4-turbo"
        assert model.name == "GPT-4 Turbo"
        assert model.description == "Advanced language model"
        assert model.context_length == 128000
        assert model.category_ids == [1, 2]
        assert model.tag_names == ["text", "reasoning"]

    def test_model_response_schema(self):
        """濞村鐦Ο鈥崇€烽崫宥呯安 Schema"""
        from testing_service.schemas import ModelDetailResponse

        response = ModelDetailResponse(
            id=1,
            model_id="gpt-4",
            name="GPT-4",
            description="Advanced language model",
            context_length=8192,
            model_size="large",
            is_open_source=False,
            is_active=True,
            tags=["text"],
            categories=[],
        )

        assert response.id == 1
        assert response.model_id == "gpt-4"
        assert response.name == "GPT-4"

    def test_model_update_schema(self):
        """濞村鐦Ο鈥崇€烽弴瀛樻煀 Schema"""
        from testing_service.schemas import ModelUpdate

        update = ModelUpdate(
            name="Updated Model Name",
            description="Updated description",
            context_length=16384,
        )

        assert update.name == "Updated Model Name"
        assert update.context_length == 16384

    def test_model_list_item_schema(self):
        """濞村鐦Ο鈥崇€烽崚妤勩€冩い?Schema"""
        from testing_service.schemas import ModelListItem, ModelCategoryInfo

        # 閸掓稑缂?ModelCategoryInfo 鐎电钖?
        category = ModelCategoryInfo(
            slug="reasoning",
            name="Reasoning",
        )

        item = ModelListItem(
            id=1,
            model_id="gpt-4",
            name="GPT-4",
            description="Advanced model",
            context_length=8192,
            model_size="large",
            is_open_source=False,
            tags=["text"],
            category=category,
            provider_count=3,
        )

        assert item.id == 1
        assert item.provider_count == 3
        assert item.category.slug == "reasoning"
        assert item.category.name == "Reasoning"

    def test_model_category_info_schema(self):
        """濞村鐦Ο鈥崇€烽崚鍡欒娣団剝浼?Schema"""
        from testing_service.schemas import ModelCategoryInfo

        info = ModelCategoryInfo(
            slug="reasoning",
            name="Reasoning",
        )

        assert info.slug == "reasoning"
        assert info.name == "Reasoning"


class TestProviderSchema:
    """濞村鐦笟娑樼安閸?Schema"""

    def test_provider_create_with_required_fields(self):
        """濞村鐦箛鍛綖鐎涙顔"""
        from testing_service.schemas import ProviderCreate

        provider = ProviderCreate(
            provider_id="openai",
            name="OpenAI",
        )

        assert provider.provider_id == "openai"
        assert provider.name == "OpenAI"
        assert provider.logo_url is None

    def test_provider_create_with_all_fields(self):
        """濞村鐦€瑰本鏆ｇ€涙顔"""
        from testing_service.schemas import ProviderCreate

        provider = ProviderCreate(
            provider_id="aliyun",
            name="Aliyun",
            logo_url="https://aliyun.com/logo.png",
            is_active=True,
            sort_order=1,
        )

        assert provider.provider_id == "aliyun"
        assert provider.name == "Aliyun"
        assert provider.logo_url == "https://aliyun.com/logo.png"
        assert provider.is_active is True
        assert provider.sort_order == 1

    def test_provider_response_schema(self):
        """濞村鐦笟娑樼安閸熷棗鎼锋惔?Schema"""
        from testing_service.schemas import ProviderResponse

        response = ProviderResponse(
            id=1,
            provider_id="openai",
            name="OpenAI",
            logo_url="https://openai.com/logo.png",
            is_active=True,
            sort_order=1,
        )

        assert response.id == 1
        assert response.provider_id == "openai"
        assert response.name == "OpenAI"

    def test_provider_update_schema(self):
        """濞村鐦笟娑樼安閸熷棙娲块弬?Schema"""
        from testing_service.schemas import ProviderUpdate

        update = ProviderUpdate(
            name="Updated Provider",
            logo_url="https://new-logo.com/logo.png",
            is_active=False,
        )

        assert update.name == "Updated Provider"
        assert update.logo_url == "https://new-logo.com/logo.png"
        assert update.is_active is False

    def test_provider_with_models_schema(self):
        """濞村鐦敮锔侥侀崹瀣灙鐞涖劎娈戞笟娑樼安閸?Schema"""
        from testing_service.schemas import ProviderWithModels

        provider = ProviderWithModels(
            id=1,
            provider_id="openai",
            name="OpenAI",
            logo_url="https://openai.com/logo.png",
            is_active=True,
            sort_order=1,
            model_count=10,
        )

        assert provider.model_count == 10


class TestBenchmarkSchema:
    """濞村鐦幀褑鍏樺ù瀣槸閻╃鍙?Schema"""

    def test_benchmark_run_request_schema(self):
        """濞村鐦幀褑鍏樺ù瀣槸鐠囬攱鐪?Schema"""
        from testing_service.schemas import BenchmarkRunRequest

        request = BenchmarkRunRequest(
            model_provider_ids=[1, 2, 3],
            concurrency=10,
            timeout=60,
        )

        assert request.model_provider_ids == [1, 2, 3]
        assert request.concurrency == 10
        assert request.timeout == 60

    def test_benchmark_run_request_defaults(self):
        """濞村鐦幀褑鍏樺ù瀣槸鐠囬攱鐪版妯款吇閸"""
        from testing_service.schemas import BenchmarkRunRequest

        request = BenchmarkRunRequest()

        assert request.concurrency == 10
        assert request.timeout == 60
        assert request.model_provider_ids is None


class TestModelFieldsRemoved:
    """妤犲矁鐦夐弮褍鐡у▓闈涘嚒鐞氼偄鍨归梽"""

    def test_category_no_old_fields(self):
        """妤犲矁鐦夐崚鍡欒閺冪姵妫€涙顔"""
        from testing_service.schemas import CategoryCreate, CategoryResponse

        # 绾喛顓诲▽鈩冩箒閺冄冪摟濞?
        assert not hasattr(CategoryCreate, 'name_zh')
        assert not hasattr(CategoryCreate, 'name_en')
        assert not hasattr(CategoryCreate, 'description_zh')
        assert not hasattr(CategoryCreate, 'description_en')

    def test_model_no_old_fields(self):
        """妤犲矁鐦夊Ο鈥崇€烽弮鐘虫＋鐎涙顔"""
        from testing_service.schemas import ModelCreate

        assert not hasattr(ModelCreate, 'name_zh')
        assert not hasattr(ModelCreate, 'description_zh')
        assert not hasattr(ModelCreate, 'description_en')

    def test_provider_no_old_fields(self):
        """妤犲矁鐦夋笟娑樼安閸熷棙妫ら弮褍鐡у▓"""
        from testing_service.schemas import ProviderCreate

        assert not hasattr(ProviderCreate, 'name_zh')
        assert not hasattr(ProviderCreate, 'color')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
'''
