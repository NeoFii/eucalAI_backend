# -*- coding: utf-8 -*-
"""
Testing 服务 Pydantic Schema
定义 API 请求/响应的数据结构，与数据库表结构严格对应
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ========== 通用响应 ==========

class ApiResponse(BaseModel, Generic[T]):
    """通用 API 响应"""
    code: int = Field(default=200, description="状态码")
    message: str = Field(default="success", description="消息")
    data: Optional[T] = Field(None, description="数据")


class ListResponse(BaseModel, Generic[T]):
    """分页列表数据"""
    items: List[T]
    total: int
    page: int
    page_size: int


# ========== 研发商（model_vendors）==========

class ModelVendorResponse(BaseModel):
    """研发商响应（创造模型的公司，≠ 服务提供商）"""
    id: int
    slug: str = Field(..., description="研发商标识，如 anthropic / openai")
    name: str = Field(..., description="显示名称")
    logo_url: Optional[str] = Field(None, description="Logo 图片地址")
    is_active: bool

    class Config:
        from_attributes = True


class ModelVendorBrief(BaseModel):
    """研发商简要信息（嵌入模型响应中）"""
    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True


class VendorCreate(BaseModel):
    """创建研发商"""
    slug: str = Field(..., description="研发商标识，如 anthropic / openai")
    name: str = Field(..., description="显示名称")
    logo_url: Optional[str] = Field(None, description="Logo 图片地址")
    is_active: bool = Field(True, description="是否启用")


class VendorUpdate(BaseModel):
    """更新研发商（所有字段可选）"""
    name: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: Optional[bool] = None


# ========== 分类（model_categories）==========

class ModelCategoryResponse(BaseModel):
    """模型能力分类响应"""
    id: int
    key: str = Field(..., description="分类键，如 reasoning / coding")
    name: str = Field(..., description="显示名，如 逻辑推理与规划")
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class ModelCategoryBrief(BaseModel):
    """分类简要信息（嵌入模型响应中）"""
    key: str
    name: str
    sort_order: int = Field(..., description="模型在该分类下的排序权重（来自 model_category_map）")

    class Config:
        from_attributes = True


# ========== 服务提供商（providers）==========

class ProviderResponse(BaseModel):
    """服务提供商响应（提供 API 访问的公司，≠ 研发商）"""
    id: int
    slug: str = Field(..., description="提供商标识，如 openrouter / azure")
    name: str = Field(..., description="显示名称")
    logo_url: Optional[str] = Field(None, description="Logo 图片地址")
    is_active: bool

    class Config:
        from_attributes = True


class ProviderCreate(BaseModel):
    """创建服务提供商（必填 slug + name）"""
    slug: str = Field(..., description="提供商标识，如 openrouter / azure")
    name: str = Field(..., description="显示名称")
    logo_url: Optional[str] = Field(None, description="Logo 图片地址")
    is_active: bool = Field(True, description="是否启用")


class ProviderUpdate(BaseModel):
    """更新服务提供商（所有字段可选）"""
    name: Optional[str] = Field(None, description="显示名称")
    logo_url: Optional[str] = Field(None, description="Logo 图片地址")
    is_active: Optional[bool] = Field(None, description="是否启用")


class ProviderBrief(BaseModel):
    """提供商简要信息（嵌入报价响应中）"""
    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True


# ========== 性能指标（聚合自 provider_metrics_ranked 视图）==========

class OfferingMetricsResponse(BaseModel):
    """
    单个报价的性能指标（聚合近 N 次成功探测均值）
    数据来源：provider_metrics_ranked 视图 WHERE rn <= N
    """
    probe_region: Optional[str] = Field(None, description="探测区域，如 cn-east")
    avg_throughput_tps: Optional[float] = Field(None, description="平均吞吐量（tokens/秒）")
    avg_ttft_ms: Optional[int] = Field(None, description="平均首字延迟（毫秒）")
    avg_e2e_latency_ms: Optional[int] = Field(None, description="平均端到端延迟（毫秒）")
    sample_count: int = Field(0, description="参与聚合的样本数量（≤N）")
    last_measured_at: Optional[datetime] = Field(None, description="最近一次探测时间")


# ========== 模型-提供商报价（model_provider_offerings）==========

class ModelOfferingResponse(BaseModel):
    """
    模型在某提供商的报价配置（附带性能指标）
    用于模型详情页的提供商卡片
    """
    id: int
    provider: ProviderBrief
    price_input_per_m: Optional[Decimal] = Field(None, description="每百万输入 token 价格（人民币，NULL=未知）")
    price_output_per_m: Optional[Decimal] = Field(None, description="每百万输出 token 价格（人民币，NULL=未知）")
    provider_model_id: Optional[str] = Field(None, description="在该提供商的模型标识")
    price_updated_at: Optional[datetime] = Field(None, description="价格最后更新时间")
    is_active: bool
    # 性能指标，由 service 层聚合注入；可能为空（从未探测或全部失败）
    metrics: Optional[OfferingMetricsResponse] = None

    class Config:
        from_attributes = True


# ========== 模型（models）==========

class ModelListItem(BaseModel):
    """
    模型列表项（用于分类页卡片展示）
    前端按 category_maps[].sort_order → sort_order → name 排序
    """
    id: int
    slug: str = Field(..., description="对外模型标识，如 gpt-4o")
    name: str = Field(..., description="显示名称")
    description: Optional[str] = None
    # JSON 数组，如 ["chat","reasoning","vision","tool_calling"]
    capability_tags: List[str] = Field(default_factory=list, description="能力标签")
    context_window: Optional[int] = Field(None, description="上下文窗口（tokens）")
    max_output_tokens: Optional[int] = Field(None, description="最大输出 tokens")
    knowledge_cutoff: Optional[date] = Field(None, description="知识截止日期")
    is_reasoning_model: bool = Field(False, description="是否为推理模型")
    sort_order: int = Field(0, description="全局排序权重")
    # 嵌套研发商简要信息
    vendor: ModelVendorBrief
    # 该模型所属的分类（含在该分类下的 sort_order）
    categories: List[ModelCategoryBrief] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ModelDetailResponse(BaseModel):
    """
    模型详情（用于详情页）
    附带所有报价配置（含性能指标）
    """
    id: int
    slug: str
    name: str
    description: Optional[str] = None
    capability_tags: List[str] = Field(default_factory=list)
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    knowledge_cutoff: Optional[date] = None
    is_reasoning_model: bool = False
    is_active: bool = True
    vendor: ModelVendorBrief
    categories: List[ModelCategoryBrief] = Field(default_factory=list)
    # 各提供商的报价（含性能指标）
    offerings: List[ModelOfferingResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ========== 模型写操作 Schema ==========

class ModelCategoryAssign(BaseModel):
    """模型-分类关联条目（含该模型在此分类下的排序权重）"""
    category_id: int = Field(..., description="分类 ID")
    sort_order: int = Field(0, description="模型在该分类下的排序权重")


class ModelCreate(BaseModel):
    """创建模型"""
    vendor_id: int = Field(..., description="研发商 ID")
    slug: str = Field(..., description="模型标识，如 gpt-4o")
    name: str = Field(..., description="显示名称")
    description: Optional[str] = None
    capability_tags: List[str] = Field(default_factory=list, description="能力标签数组")
    context_window: Optional[int] = Field(None, description="上下文窗口（tokens）")
    max_output_tokens: Optional[int] = Field(None, description="最大输出 tokens")
    knowledge_cutoff: Optional[date] = Field(None, description="知识截止日期")
    is_reasoning_model: bool = Field(False, description="是否为推理模型")
    sort_order: int = Field(0, description="全局排序权重")
    is_active: bool = Field(True, description="是否启用")
    categories: List[ModelCategoryAssign] = Field(default_factory=list, description="分类关联列表")


class ModelUpdate(BaseModel):
    """更新模型（所有字段可选；categories=None 时不变更分类关联）"""
    name: Optional[str] = None
    description: Optional[str] = None
    capability_tags: Optional[List[str]] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    knowledge_cutoff: Optional[date] = None
    is_reasoning_model: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    categories: Optional[List[ModelCategoryAssign]] = None


# ========== 报价写操作 Schema ==========

class OfferingCreate(BaseModel):
    """添加模型-服务商报价配置"""
    provider_id: int = Field(..., description="服务商 ID")
    price_input_per_m: Optional[Decimal] = Field(None, description="每百万输入 token 价格（人民币）")
    price_output_per_m: Optional[Decimal] = Field(None, description="每百万输出 token 价格（人民币）")
    provider_model_id: Optional[str] = Field(None, description="在该服务商的 API 模型 ID，如 anthropic/claude-3-7-sonnet")


# ========== 探测原始记录写入（供定时任务使用）==========

class PerformanceMetricCreate(BaseModel):
    """
    性能探测记录写入（append-only，由 APScheduler 定时任务调用）
    """
    offering_id: int = Field(..., description="报价 ID")
    throughput_tps: Optional[float] = Field(None, description="吞吐量（tokens/秒）")
    ttft_ms: Optional[int] = Field(None, description="首字延迟（毫秒）")
    e2e_latency_ms: Optional[int] = Field(None, description="端到端延迟（毫秒）")
    success: bool = Field(True, description="是否成功")
    error_code: Optional[str] = Field(None, description="错误码")
    prompt_tokens: Optional[int] = Field(None, description="prompt tokens 数")
    output_tokens: Optional[int] = Field(None, description="输出 tokens 数")
    probe_region: Optional[str] = Field(None, description="探测区域，如 cn-east")
    measured_at: datetime = Field(..., description="探测时间")
