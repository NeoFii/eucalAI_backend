# -*- coding: utf-8 -*-
"""
Testing 服务 Pydantic 模型
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ========== 分类相关 ==========

class CategoryBase(BaseModel):
    """分类基础字段"""
    name_zh: str = Field(..., description="中文名称")
    name_en: str = Field(..., description="英文名称")
    slug: str = Field(..., description="英文别名")
    description_zh: Optional[str] = Field(None, description="中文描述")
    description_en: Optional[str] = Field(None, description="英文描述")
    icon: Optional[str] = Field(None, description="图标标识")
    sort_order: int = Field(0, description="排序顺序")


class CategoryCreate(CategoryBase):
    """创建分类请求"""
    pass


class CategoryUpdate(BaseModel):
    """更新分类请求"""
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    description_zh: Optional[str] = None
    description_en: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryResponse(BaseModel):
    """分类响应"""
    id: int
    name_zh: str
    name_en: str
    slug: str
    description_zh: Optional[str]
    description_en: Optional[str]
    icon: Optional[str]
    sort_order: int

    class Config:
        from_attributes = True


class CategoryWithModels(CategoryResponse):
    """带模型列表的分类"""
    model_count: int = Field(0, description="模型数量")

    class Config:
        from_attributes = True


# ========== 模型相关 ==========

class ModelTagBase(BaseModel):
    """模型标签基础字段"""
    tag: str
    tag_type: str = "feature"


class ModelTagCreate(ModelTagBase):
    """创建模型标签请求"""
    model_id: int


class ModelTagResponse(ModelTagBase):
    """模型标签响应"""
    id: int

    class Config:
        from_attributes = True


class ModelProviderBase(BaseModel):
    """模型供应商关联基础字段"""
    provider_id: int
    api_model_name: str
    routing_alias: Optional[str] = None
    input_price_cny_1m: Optional[float] = None
    output_price_cny_1m: Optional[float] = None
    rate_limit_rpm: int = 60
    is_default: bool = False
    is_active: bool = True


class ModelProviderCreate(ModelProviderBase):
    """创建模型供应商关联请求"""
    model_id: int


class ModelProviderResponse(ModelProviderBase):
    """模型供应商关联响应"""
    id: int
    model_id: int

    class Config:
        from_attributes = True


class ModelBase(BaseModel):
    """模型基础字段"""
    model_id: str = Field(..., description="对外模型ID")
    name: str = Field(..., description="显示名称")
    name_zh: Optional[str] = Field(None, description="中文名称")
    description_zh: Optional[str] = Field(None, description="中文描述")
    description_en: Optional[str] = Field(None, description="英文描述")
    context_length: int = Field(0, description="上下文长度")
    model_size: Optional[str] = Field(None, description="模型大小")
    is_open_source: bool = Field(False, description="是否开源")
    is_active: bool = Field(True, description="是否启用")


class ModelCreate(ModelBase):
    """创建模型请求"""
    category_ids: List[int] = Field(default_factory=list, description="分类ID列表")
    tag_names: List[str] = Field(default_factory=list, description="标签列表")


class ModelUpdate(BaseModel):
    """更新模型请求"""
    name: Optional[str] = None
    name_zh: Optional[str] = None
    description_zh: Optional[str] = None
    description_en: Optional[str] = None
    context_length: Optional[int] = None
    model_size: Optional[str] = None
    is_open_source: Optional[bool] = None
    is_active: Optional[bool] = None


class ModelCategoryInfo(BaseModel):
    """模型分类信息"""
    slug: str
    name_zh: str

    class Config:
        from_attributes = True


class ModelListItem(BaseModel):
    """模型列表项"""
    id: int
    model_id: str
    name: str
    name_zh: Optional[str]
    description_zh: Optional[str]
    context_length: int
    model_size: Optional[str]
    is_open_source: bool
    tags: List[str] = []
    category: Optional[ModelCategoryInfo] = None
    provider_count: int = 0

    class Config:
        from_attributes = True


class ModelDetailResponse(BaseModel):
    """模型详情响应"""
    id: int
    model_id: str
    name: str
    name_zh: Optional[str]
    description_zh: Optional[str]
    description_en: Optional[str]
    context_length: int
    model_size: Optional[str]
    is_open_source: bool
    is_active: bool
    tags: List[str] = []
    categories: List[ModelCategoryInfo] = []

    class Config:
        from_attributes = True


# ========== 供应商相关 ==========

class ProviderBase(BaseModel):
    """供应商基础字段"""
    provider_id: str = Field(..., description="供应商ID")
    name: str = Field(..., description="显示名称")
    name_zh: Optional[str] = Field(None, description="中文名称")
    logo_url: Optional[str] = Field(None, description="Logo URL")
    color: Optional[str] = Field(None, description="主题色")
    is_active: bool = Field(True, description="是否启用")
    sort_order: int = Field(0, description="排序顺序")


class ProviderCreate(ProviderBase):
    """创建供应商请求"""
    pass


class ProviderUpdate(BaseModel):
    """更新供应商请求"""
    name: Optional[str] = None
    name_zh: Optional[str] = None
    logo_url: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ProviderResponse(ProviderBase):
    """供应商响应"""
    id: int

    class Config:
        from_attributes = True


class ProviderWithModels(ProviderResponse):
    """带模型列表的供应商"""
    model_count: int = Field(0, description="模型数量")

    class Config:
        from_attributes = True


# ========== 性能测试相关 ==========

class BenchmarkResultBase(BaseModel):
    """性能测试结果基础字段"""
    model_provider_id: int
    latency_ttft: Optional[float] = None
    latency_total: Optional[float] = None
    throughput: Optional[float] = None
    success_count: int = 1
    fail_count: int = 0
    test_prompt: Optional[str] = None


class BenchmarkResultCreate(BenchmarkResultBase):
    """创建性能测试结果请求"""
    pass


class BenchmarkStatsResponse(BaseModel):
    """性能统计响应"""
    model_provider_id: int
    avg_latency_ttft: Optional[float] = None
    avg_latency_total: Optional[float] = None
    avg_throughput: Optional[float] = None
    success_rate: Optional[float] = None
    success_count: int = 0
    fail_count: int = 0
    test_count: int = 0
    last_test_at: Optional[datetime] = None


class ProviderStatsResponse(BaseModel):
    """供应商性能统计"""
    provider_id: int
    provider_name: str
    color: Optional[str]
    model_provider_id: int
    model_name: str
    api_model_name: str
    input_price_cny_1m: Optional[float]
    output_price_cny_1m: Optional[float]
    stats: BenchmarkStatsResponse


class BenchmarkRunRequest(BaseModel):
    """触发性能测试请求"""
    model_provider_ids: Optional[List[int]] = None
    concurrency: int = Field(10, description="并发数")
    timeout: int = Field(60, description="超时时间(秒)")


class BenchmarkRunResponse(BaseModel):
    """性能测试运行响应"""
    task_id: str
    status: str
    total: int
    submitted: int


# ========== 通用响应 ==========

class ListResponse(BaseModel):
    """列表响应"""
    items: List
    total: int
    page: int
    page_size: int


class BaseResponse(BaseModel):
    """基础响应"""
    code: int = 200
    message: str = "操作成功"


class DataResponse(BaseModel):
    """数据响应"""
    code: int = 200
    message: str = "操作成功"
    data: Optional[dict] = None
