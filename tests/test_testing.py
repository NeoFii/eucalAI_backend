# -*- coding: utf-8 -*-
"""
Testing 模块单元测试
测试模型管理、供应商管理和性能测试功能
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

# 添加 backend 到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# 设置环境变量
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TESTING_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


class TestModelsImport:
    """测试模型导入"""

    def test_import_models(self):
        """测试导入模型定义"""
        from testing.models import (
            ModelCategory,
            ModelCategoryMapping,
            Model,
            ModelTag,
            Provider,
            ModelProvider,
            BenchmarkResult,
        )

        assert ModelCategory is not None
        assert ModelCategoryMapping is not None
        assert Model is not None
        assert ModelTag is not None
        assert Provider is not None
        assert ModelProvider is not None
        assert BenchmarkResult is not None

    def test_model_category_columns(self):
        """测试 ModelCategory 字段"""
        from testing.models import ModelCategory

        # 检查主要字段存在
        assert hasattr(ModelCategory, 'id')
        assert hasattr(ModelCategory, 'name')
        assert hasattr(ModelCategory, 'slug')
        assert hasattr(ModelCategory, 'description')
        assert hasattr(ModelCategory, 'icon')
        assert hasattr(ModelCategory, 'sort_order')

        # 验证旧字段已被删除
        assert not hasattr(ModelCategory, 'name_zh')
        assert not hasattr(ModelCategory, 'name_en')
        assert not hasattr(ModelCategory, 'description_zh')
        assert not hasattr(ModelCategory, 'description_en')

    def test_model_columns(self):
        """测试 Model 字段"""
        from testing.models import Model

        # 检查主要字段存在
        assert hasattr(Model, 'id')
        assert hasattr(Model, 'model_id')
        assert hasattr(Model, 'name')
        assert hasattr(Model, 'description')
        assert hasattr(Model, 'context_length')
        assert hasattr(Model, 'model_size')
        assert hasattr(Model, 'is_open_source')
        assert hasattr(Model, 'is_active')

        # 验证旧字段已被删除
        assert not hasattr(Model, 'name_zh')
        assert not hasattr(Model, 'description_zh')
        assert not hasattr(Model, 'description_en')

    def test_provider_columns(self):
        """测试 Provider 字段"""
        from testing.models import Provider

        # 检查主要字段存在
        assert hasattr(Provider, 'id')
        assert hasattr(Provider, 'provider_id')
        assert hasattr(Provider, 'name')
        assert hasattr(Provider, 'logo_url')
        assert hasattr(Provider, 'is_active')
        assert hasattr(Provider, 'sort_order')

        # 验证旧字段已被删除
        assert not hasattr(Provider, 'name_zh')
        assert not hasattr(Provider, 'color')

    def test_model_provider_columns(self):
        """测试 ModelProvider 字段"""
        from testing.models import ModelProvider

        # 检查主要字段存在
        assert hasattr(ModelProvider, 'id')
        assert hasattr(ModelProvider, 'model_id')
        assert hasattr(ModelProvider, 'provider_id')
        assert hasattr(ModelProvider, 'api_model_name')
        assert hasattr(ModelProvider, 'routing_alias')
        assert hasattr(ModelProvider, 'input_price_cny_1m')
        assert hasattr(ModelProvider, 'output_price_cny_1m')
        assert hasattr(ModelProvider, 'rate_limit_rpm')
        assert hasattr(ModelProvider, 'is_default')
        assert hasattr(ModelProvider, 'is_active')

    def test_benchmark_result_columns(self):
        """测试 BenchmarkResult 字段"""
        from testing.models import BenchmarkResult

        # 检查主要字段存在
        assert hasattr(BenchmarkResult, 'id')
        assert hasattr(BenchmarkResult, 'model_provider_id')
        assert hasattr(BenchmarkResult, 'latency_ttft')
        assert hasattr(BenchmarkResult, 'latency_total')
        assert hasattr(BenchmarkResult, 'throughput')
        assert hasattr(BenchmarkResult, 'success_count')
        assert hasattr(BenchmarkResult, 'fail_count')
        assert hasattr(BenchmarkResult, 'test_prompt')
        assert hasattr(BenchmarkResult, 'test_at')


class TestSchemasImport:
    """测试 Schema 导入"""

    def test_import_schemas(self):
        """测试导入 Schema 定义"""
        from testing.schemas import (
            CategoryBase,
            CategoryCreate,
            CategoryResponse,
            ModelBase,
            ModelCreate,
            ProviderBase,
            ProviderCreate,
            ProviderResponse,
            BenchmarkResultBase,
            BenchmarkStatsResponse,
        )

        assert CategoryBase is not None
        assert CategoryCreate is not None
        assert CategoryResponse is not None
        assert ModelBase is not None
        assert ModelCreate is not None
        assert ProviderBase is not None
        assert ProviderCreate is not None

    def test_category_schema_fields(self):
        """测试 Category Schema 字段"""
        from testing.schemas import CategoryCreate

        schema = CategoryCreate(
            name="Test Category",
            slug="test-category",
            description="This is a test category",
        )

        assert schema.name == "Test Category"
        assert schema.slug == "test-category"
        assert schema.description == "This is a test category"

        # 验证旧字段已被删除
        assert not hasattr(schema, 'name_zh')
        assert not hasattr(schema, 'name_en')
        assert not hasattr(schema, 'description_zh')
        assert not hasattr(schema, 'description_en')

    def test_model_schema_fields(self):
        """测试 Model Schema 字段"""
        from testing.schemas import ModelCreate

        schema = ModelCreate(
            model_id="test-model",
            name="Test Model",
            description="This is a test model",
            context_length=4096,
            category_ids=[1, 2],
            tag_names=["text", "reasoning"],
        )

        assert schema.model_id == "test-model"
        assert schema.name == "Test Model"
        assert schema.description == "This is a test model"
        assert schema.context_length == 4096
        assert schema.category_ids == [1, 2]
        assert schema.tag_names == ["text", "reasoning"]

        # 验证旧字段已被删除
        assert not hasattr(schema, 'name_zh')
        assert not hasattr(schema, 'description_zh')
        assert not hasattr(schema, 'description_en')

    def test_provider_schema_fields(self):
        """测试 Provider Schema 字段"""
        from testing.schemas import ProviderCreate

        schema = ProviderCreate(
            provider_id="test-provider",
            name="Test Provider",
            logo_url="https://example.com/logo.png",
            sort_order=1,
        )

        assert schema.provider_id == "test-provider"
        assert schema.name == "Test Provider"
        assert schema.logo_url == "https://example.com/logo.png"
        assert schema.sort_order == 1

        # 验证旧字段已被删除
        assert not hasattr(schema, 'name_zh')
        assert not hasattr(schema, 'color')

    def test_benchmark_run_request_schema(self):
        """测试 BenchmarkRunRequest Schema"""
        from testing.schemas import BenchmarkRunRequest

        schema = BenchmarkRunRequest(
            model_provider_ids=[1, 2, 3],
            concurrency=10,
            timeout=60,
        )

        assert schema.model_provider_ids == [1, 2, 3]
        assert schema.concurrency == 10
        assert schema.timeout == 60


class TestConfig:
    """测试配置"""

    def test_config_import(self):
        """测试配置导入"""
        from testing.config import Settings, get_settings

        assert Settings is not None
        assert get_settings is not None

    def test_settings_default_values(self):
        """测试配置默认值"""
        from testing.config import Settings

        settings = Settings()

        assert settings.host == "0.0.0.0"
        assert settings.port == 8001
        assert settings.benchmark_default_timeout == 60
        assert settings.benchmark_default_concurrency == 10
        assert settings.benchmark_default_rate_limit == 60
        assert settings.cache_ttl_short == 300
        assert settings.cache_ttl_long == 86400

    def test_get_database_url(self):
        """测试获取数据库 URL"""
        from testing.config import Settings

        settings = Settings()

        # 测试空值情况
        url = settings.get_database_url()
        assert url == "" or url is not None


class TestCache:
    """测试缓存模块"""

    def test_cache_import(self):
        """测试缓存导入"""
        from testing.core.cache import (
            get_or_set,
            invalidate,
            invalidate_prefix,
            long_cache,
            short_cache,
        )

        assert get_or_set is not None
        assert invalidate is not None
        assert invalidate_prefix is not None
        assert long_cache is not None
        assert short_cache is not None

    def test_cache_instances(self):
        """测试缓存实例"""
        from testing.core.cache import long_cache, short_cache

        # 测试缓存是 TTLCache 实例
        from cachetools import TTLCache

        assert isinstance(long_cache, TTLCache)
        assert isinstance(short_cache, TTLCache)

        # 测试 TTL 设置
        assert long_cache.ttl == 86400  # 24小时
        assert short_cache.ttl == 300    # 5分钟

    @pytest.mark.asyncio
    async def test_get_or_set_with_value(self):
        """测试 get_or_set 有值的情况"""
        from testing.core.cache import short_cache, get_or_set

        # 设置一个值
        short_cache["test_key"] = "test_value"

        # 定义回调函数（不应该被调用）
        async def fetch_data():
            return "should_not_be_called"

        # 获取值（应该返回缓存的值）
        result = await get_or_set(short_cache, "test_key", fetch_data)
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_or_set_without_value(self):
        """测试 get_or_set 无值的情况"""
        from testing.core.cache import short_cache, get_or_set

        # 确保键不存在
        if "new_key" in short_cache:
            del short_cache["new_key"]

        # 定义回调函数
        async def fetch_data():
            return "fetched_value"

        # 获取值（应该调用回调函数）
        result = await get_or_set(short_cache, "new_key", fetch_data)
        assert result == "fetched_value"
        assert short_cache["new_key"] == "fetched_value"

    def test_invalidate(self):
        """测试 invalidate 函数"""
        from testing.core.cache import short_cache, invalidate

        # 设置值
        short_cache["key1"] = "value1"
        short_cache["key2"] = "value2"

        # 删除键
        invalidate(short_cache, "key1")

        assert "key1" not in short_cache
        assert "key2" in short_cache  # 不应被删除

    def test_invalidate_prefix(self):
        """测试 invalidate_prefix 函数"""
        from testing.core.cache import short_cache, invalidate_prefix

        # 设置多个键
        short_cache["user:1"] = "user1"
        short_cache["user:2"] = "user2"
        short_cache["post:1"] = "post1"

        # 删除前缀为 "user:" 的键
        invalidate_prefix(short_cache, "user:")

        assert "user:1" not in short_cache
        assert "user:2" not in short_cache
        assert "post:1" in short_cache  # 不应被删除


class TestBenchmarkEngine:
    """测试基准测试引擎"""

    def test_engine_import(self):
        """测试引擎导入"""
        from testing.benchmark.engine import BenchmarkEngine

        assert BenchmarkEngine is not None

    def test_engine_initialization(self):
        """测试引擎初始化"""
        from testing.benchmark.engine import BenchmarkEngine

        engine = BenchmarkEngine()
        assert engine is not None

    def test_engine_has_run_benchmark_method(self):
        """测试引擎有 run_benchmark 方法"""
        from testing.benchmark.engine import BenchmarkEngine

        engine = BenchmarkEngine()
        assert hasattr(engine, 'run_benchmark')
        assert hasattr(engine, 'run_batch')
        assert hasattr(engine, 'run_adaptive_batch')


class TestBenchmarkTasks:
    """测试基准测试任务"""

    def test_task_import(self):
        """测试任务导入"""
        from testing.benchmark.tasks import BenchmarkTask, BenchmarkScheduler

        assert BenchmarkTask is not None
        assert BenchmarkScheduler is not None

    def test_task_has_required_methods(self):
        """测试任务有必需的方法"""
        from testing.benchmark.tasks import BenchmarkTask

        # 检查必需的方法存在
        assert hasattr(BenchmarkTask, 'run_single_test')
        assert hasattr(BenchmarkTask, 'run_batch')
        assert hasattr(BenchmarkTask, 'update_stats')


class TestServicesImport:
    """测试服务层导入"""

    def test_import_services(self):
        """测试导入服务层"""
        from testing.services import (
            CategoryService,
            ModelService,
            ProviderService,
            ModelProviderService,
            BenchmarkService,
        )

        assert CategoryService is not None
        assert ModelService is not None
        assert ProviderService is not None
        assert ModelProviderService is not None
        assert BenchmarkService is not None

    def test_category_service_methods(self):
        """测试 CategoryService 方法"""
        from testing.services import CategoryService

        # 检查必需的方法存在
        assert hasattr(CategoryService, 'create')
        assert hasattr(CategoryService, 'get_by_id')
        assert hasattr(CategoryService, 'get_by_slug')
        assert hasattr(CategoryService, 'list_all')
        assert hasattr(CategoryService, 'update')
        assert hasattr(CategoryService, 'delete')

    def test_model_service_methods(self):
        """测试 ModelService 方法"""
        from testing.services import ModelService

        # 检查必需的方法存在
        assert hasattr(ModelService, 'create')
        assert hasattr(ModelService, 'get_by_id')
        assert hasattr(ModelService, 'get_by_model_id')
        assert hasattr(ModelService, 'list_all')
        assert hasattr(ModelService, 'get_tags')
        assert hasattr(ModelService, 'get_categories_info')
        assert hasattr(ModelService, 'get_provider_count')

    def test_provider_service_methods(self):
        """测试 ProviderService 方法"""
        from testing.services import ProviderService

        # 检查必需的方法存在
        assert hasattr(ProviderService, 'create')
        assert hasattr(ProviderService, 'get_by_id')
        assert hasattr(ProviderService, 'get_by_provider_id')
        assert hasattr(ProviderService, 'list_all')
        assert hasattr(ProviderService, 'get_model_count')

    def test_benchmark_service_methods(self):
        """测试 BenchmarkService 方法"""
        from testing.services import BenchmarkService

        # 检查必需的方法存在
        assert hasattr(BenchmarkService, 'create_result')
        assert hasattr(BenchmarkService, 'get_stats')
        assert hasattr(BenchmarkService, 'get_provider_stats')
        assert hasattr(BenchmarkService, 'cleanup_old_results')


class TestAPIEndpoints:
    """测试 API 端点"""

    def test_models_endpoint_import(self):
        """测试模型端点导入"""
        from testing.api.v1.endpoints import models

        assert models is not None

    def test_providers_endpoint_import(self):
        """测试供应商端点导入"""
        from testing.api.v1.endpoints import providers

        assert providers is not None

    def test_benchmark_endpoint_import(self):
        """测试基准测试端点导入"""
        from testing.api.v1.endpoints import benchmark

        assert benchmark is not None


class TestAPIRouter:
    """测试 API 路由"""

    def test_router_import(self):
        """测试路由导入"""
        from testing.api.v1.router import api_router

        assert api_router is not None


class TestMainApp:
    """测试主应用"""

    def test_main_import(self):
        """测试主模块导入"""
        from testing import main

        assert main is not None

    def test_app_creation(self):
        """测试应用创建"""
        from testing.main import app

        assert app is not None
        assert app.title == "Eucal AI Testing Service"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
