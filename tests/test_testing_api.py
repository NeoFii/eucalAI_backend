# -*- coding: utf-8 -*-
"""
Testing 服务接口测试
验证迁移后的 Schema 和服务层是否正常工作
"""

import pytest
from pydantic import ValidationError


class TestCategorySchema:
    """测试分类 Schema"""

    def test_category_create_with_required_fields(self):
        """测试必填字段"""
        from testing.schemas import CategoryCreate

        # 提供必填字段
        category = CategoryCreate(
            name="Reasoning & Planning",
            slug="reasoning",
        )

        assert category.name == "Reasoning & Planning"
        assert category.slug == "reasoning"
        assert category.description is None

    def test_category_create_with_all_fields(self):
        """测试完整字段"""
        from testing.schemas import CategoryCreate

        category = CategoryCreate(
            name="Programming",
            slug="programming",
            description="Models specialized in code generation",
            icon="code",
            sort_order=2,
        )

        assert category.name == "Programming"
        assert category.slug == "programming"
        assert category.description == "Models specialized in code generation"
        assert category.icon == "code"
        assert category.sort_order == 2

    def test_category_response_schema(self):
        """测试分类响应 Schema"""
        from testing.schemas import CategoryResponse

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
        """测试分类更新 Schema"""
        from testing.schemas import CategoryUpdate

        update = CategoryUpdate(
            name="Updated Name",
            description="Updated description",
        )

        assert update.name == "Updated Name"
        assert update.description == "Updated description"


class TestModelSchema:
    """测试模型 Schema"""

    def test_model_create_with_required_fields(self):
        """测试必填字段"""
        from testing.schemas import ModelCreate

        model = ModelCreate(
            model_id="gpt-4",
            name="GPT-4",
        )

        assert model.model_id == "gpt-4"
        assert model.name == "GPT-4"
        assert model.description is None

    def test_model_create_with_all_fields(self):
        """测试完整字段"""
        from testing.schemas import ModelCreate

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
        """测试模型响应 Schema"""
        from testing.schemas import ModelDetailResponse

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
        """测试模型更新 Schema"""
        from testing.schemas import ModelUpdate

        update = ModelUpdate(
            name="Updated Model Name",
            description="Updated description",
            context_length=16384,
        )

        assert update.name == "Updated Model Name"
        assert update.context_length == 16384

    def test_model_list_item_schema(self):
        """测试模型列表项 Schema"""
        from testing.schemas import ModelListItem, ModelCategoryInfo

        # 创建 ModelCategoryInfo 对象
        category = ModelCategoryInfo(
            slug="reasoning",
            name="Reasoning & Planning",
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
        assert item.category.name == "Reasoning & Planning"

    def test_model_category_info_schema(self):
        """测试模型分类信息 Schema"""
        from testing.schemas import ModelCategoryInfo

        info = ModelCategoryInfo(
            slug="reasoning",
            name="Reasoning & Planning",
        )

        assert info.slug == "reasoning"
        assert info.name == "Reasoning & Planning"


class TestProviderSchema:
    """测试供应商 Schema"""

    def test_provider_create_with_required_fields(self):
        """测试必填字段"""
        from testing.schemas import ProviderCreate

        provider = ProviderCreate(
            provider_id="openai",
            name="OpenAI",
        )

        assert provider.provider_id == "openai"
        assert provider.name == "OpenAI"
        assert provider.logo_url is None

    def test_provider_create_with_all_fields(self):
        """测试完整字段"""
        from testing.schemas import ProviderCreate

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
        """测试供应商响应 Schema"""
        from testing.schemas import ProviderResponse

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
        """测试供应商更新 Schema"""
        from testing.schemas import ProviderUpdate

        update = ProviderUpdate(
            name="Updated Provider",
            logo_url="https://new-logo.com/logo.png",
            is_active=False,
        )

        assert update.name == "Updated Provider"
        assert update.logo_url == "https://new-logo.com/logo.png"
        assert update.is_active is False

    def test_provider_with_models_schema(self):
        """测试带模型列表的供应商 Schema"""
        from testing.schemas import ProviderWithModels

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
    """测试性能测试相关 Schema"""

    def test_benchmark_run_request_schema(self):
        """测试性能测试请求 Schema"""
        from testing.schemas import BenchmarkRunRequest

        request = BenchmarkRunRequest(
            model_provider_ids=[1, 2, 3],
            concurrency=10,
            timeout=60,
        )

        assert request.model_provider_ids == [1, 2, 3]
        assert request.concurrency == 10
        assert request.timeout == 60

    def test_benchmark_run_request_defaults(self):
        """测试性能测试请求默认值"""
        from testing.schemas import BenchmarkRunRequest

        request = BenchmarkRunRequest()

        assert request.concurrency == 10
        assert request.timeout == 60
        assert request.model_provider_ids is None


class TestModelFieldsRemoved:
    """验证旧字段已被删除"""

    def test_category_no_old_fields(self):
        """验证分类无旧字段"""
        from testing.schemas import CategoryCreate, CategoryResponse

        # 确认没有旧字段
        assert not hasattr(CategoryCreate, 'name_zh')
        assert not hasattr(CategoryCreate, 'name_en')
        assert not hasattr(CategoryCreate, 'description_zh')
        assert not hasattr(CategoryCreate, 'description_en')

    def test_model_no_old_fields(self):
        """验证模型无旧字段"""
        from testing.schemas import ModelCreate

        assert not hasattr(ModelCreate, 'name_zh')
        assert not hasattr(ModelCreate, 'description_zh')
        assert not hasattr(ModelCreate, 'description_en')

    def test_provider_no_old_fields(self):
        """验证供应商无旧字段"""
        from testing.schemas import ProviderCreate

        assert not hasattr(ProviderCreate, 'name_zh')
        assert not hasattr(ProviderCreate, 'color')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
