# -*- coding: utf-8 -*-
"""
Testing 服务 SQLAlchemy 模型
定义模型、研发商、服务提供商、分类和性能探测结果的数据结构

表关系：
  model_vendors    → 研发商（创造模型的公司：Anthropic / OpenAI / DeepSeek）
  providers        → 服务提供商（提供 API 访问的公司：OpenRouter / Azure）
  两者严格分离，不可混用。
"""

from sqlalchemy import (
    Column, BigInteger, Integer, SmallInteger, String, Text,
    Boolean, DECIMAL, Date, DateTime, JSON, ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from common.db.base import Base, TimestampMixin


class ModelCategory(Base, TimestampMixin):
    """
    模型能力分类
    对应 model_categories 表，用于前端 Tab 筛选
    """

    __tablename__ = "model_categories"

    id         = Column(BigInteger, primary_key=True, autoincrement=True, comment="内部主键")
    key        = Column(String(50), nullable=False, unique=True, comment="分类键，如 reasoning / coding")
    name       = Column(String(100), nullable=False, comment="显示名，如 逻辑推理与规划")
    sort_order = Column(SmallInteger, nullable=False, default=0, comment="排序权重")
    is_active  = Column(Boolean, nullable=False, default=True, comment="是否启用")

    # 与关联表的关系（级联删除）
    category_maps = relationship(
        "ModelCategoryMap",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ModelVendor(Base, TimestampMixin):
    """
    模型研发商
    对应 model_vendors 表，记录创造模型的公司（≠ 服务提供商）
    """

    __tablename__ = "model_vendors"

    id         = Column(BigInteger, primary_key=True, autoincrement=True, comment="内部主键")
    slug       = Column(String(100), nullable=False, unique=True, comment="研发商标识，如 anthropic / openai")
    name       = Column(String(200), nullable=False, comment="显示名称")
    logo_url   = Column(Text, comment="Logo 图片地址")
    is_active  = Column(Boolean, nullable=False, default=True, comment="是否启用")

    # 研发商名下的所有模型
    models = relationship(
        "Model",
        back_populates="vendor",
        lazy="selectin",
    )


class Model(Base, TimestampMixin):
    """
    AI 模型本体
    对应 models 表，一条记录代表一个模型（如 Claude 3.7 Sonnet）
    capability_tags 使用 JSON 数组存储，查询用 JSON_CONTAINS()
    """

    __tablename__ = "models"

    id                 = Column(BigInteger, primary_key=True, autoincrement=True, comment="内部主键")
    vendor_id          = Column(BigInteger, ForeignKey("model_vendors.id"), nullable=False, comment="研发商 ID")
    slug               = Column(String(100), nullable=False, unique=True, comment="对外模型标识，如 gpt-4o")
    name               = Column(String(200), nullable=False, comment="显示名称")
    description        = Column(Text, comment="模型描述")
    # MySQL JSON 类型，存储如 ["chat","reasoning","vision","tool_calling"]
    capability_tags    = Column(JSON, nullable=False, comment="能力标签数组")
    context_window     = Column(Integer, comment="上下文窗口（tokens）")
    max_output_tokens  = Column(Integer, comment="最大输出 tokens")
    knowledge_cutoff   = Column(Date, comment="知识截止日期")
    # 冗余字段：方便快速过滤推理模型，无需解析 JSON
    is_reasoning_model = Column(Boolean, nullable=False, default=False, comment="是否为推理模型")
    sort_order         = Column(Integer, nullable=False, default=0, comment="全局排序权重")
    is_active          = Column(Boolean, nullable=False, default=True, comment="是否启用")

    # 关联研发商
    vendor = relationship("ModelVendor", back_populates="models", lazy="selectin")

    # 关联分类（多对多，通过 ModelCategoryMap）
    category_maps = relationship(
        "ModelCategoryMap",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # 关联报价配置（一个模型可在多个提供商上线）
    offerings = relationship(
        "ModelProviderOffering",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_models_vendor_id", "vendor_id"),
        Index("idx_models_is_active", "is_active"),
        Index("idx_models_sort_order", "sort_order"),
    )


class ModelCategoryMap(Base):
    """
    模型-分类多对多关联
    对应 model_category_map 表，复合主键（model_id, category_id）
    sort_order 为该模型在该分类下的排序权重（优先于 models.sort_order）
    """

    __tablename__ = "model_category_map"

    model_id    = Column(BigInteger, ForeignKey("models.id", ondelete="CASCADE"), primary_key=True, comment="模型 ID")
    category_id = Column(BigInteger, ForeignKey("model_categories.id", ondelete="CASCADE"), primary_key=True, comment="分类 ID")
    sort_order  = Column(Integer, nullable=False, default=0, comment="模型在该分类下的排序权重")
    created_at  = Column(DateTime, comment="创建时间")

    # 关联关系
    model    = relationship("Model", back_populates="category_maps")
    category = relationship("ModelCategory", back_populates="category_maps")

    __table_args__ = (
        Index("idx_mcm_category_sort", "category_id", "sort_order"),
    )


class Provider(Base, TimestampMixin):
    """
    API 服务提供商
    对应 providers 表，记录提供模型 API 访问的公司（≠ 研发商）
    """

    __tablename__ = "providers"

    id         = Column(BigInteger, primary_key=True, autoincrement=True, comment="内部主键")
    slug       = Column(String(100), nullable=False, unique=True, comment="提供商标识，如 openrouter / azure")
    name       = Column(String(200), nullable=False, comment="显示名称")
    logo_url   = Column(Text, comment="Logo 图片地址")
    is_active  = Column(Boolean, nullable=False, default=True, comment="是否启用")

    # 通过该提供商上线的模型报价
    offerings = relationship(
        "ModelProviderOffering",
        back_populates="provider",
        cascade="all, delete-orphan",
    )


class ModelProviderOffering(Base, TimestampMixin):
    """
    模型-提供商报价配置
    对应 model_provider_offerings 表
    记录每个模型在各提供商的价格和 API 配置
    """

    __tablename__ = "model_provider_offerings"

    id                 = Column(BigInteger, primary_key=True, autoincrement=True, comment="内部主键")
    model_id           = Column(BigInteger, ForeignKey("models.id", ondelete="CASCADE"), nullable=False, comment="模型 ID")
    provider_id        = Column(BigInteger, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, comment="提供商 ID")
    # 价格允许 NULL：价格未知时先建立关联关系
    price_input_per_m  = Column(DECIMAL(10, 4), comment="每百万输入 token 价格（人民币，NULL=未知）")
    price_output_per_m = Column(DECIMAL(10, 4), comment="每百万输出 token 价格（人民币，NULL=未知）")
    provider_model_id  = Column(String(200), comment="在该提供商的模型标识，如 openai/gpt-4o")
    api_base_url       = Column(Text, comment="API 基础地址（空则使用提供商默认地址）")
    price_updated_at   = Column(DateTime, comment="价格最后更新时间")
    price_updated_by   = Column(String(100), comment="价格更新人（管理员邮箱/名称）")
    is_active          = Column(Boolean, nullable=False, default=True, comment="是否启用")

    # 关联关系
    model    = relationship("Model", back_populates="offerings")
    provider = relationship("Provider", back_populates="offerings")

    # 性能探测记录（append-only）
    performance_metrics = relationship(
        "ProviderPerformanceMetric",
        back_populates="offering",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # 同一模型在同一提供商只能有一条记录
        UniqueConstraint("model_id", "provider_id", name="uk_mpo_model_provider"),
        Index("idx_mpo_model_id", "model_id"),
        Index("idx_mpo_provider_id", "provider_id"),
        Index("idx_mpo_is_active", "is_active"),
    )


class ProviderPerformanceMetric(Base):
    """
    性能探测原始记录（append-only）
    对应 provider_performance_metrics 表
    由 APScheduler 定时任务写入，只 INSERT 不 UPDATE
    聚合查询通过 VIEW provider_metrics_ranked 完成
    """

    __tablename__ = "provider_performance_metrics"

    id             = Column(BigInteger, primary_key=True, autoincrement=True, comment="内部主键")
    offering_id    = Column(BigInteger, ForeignKey("model_provider_offerings.id", ondelete="CASCADE"), nullable=False, comment="报价 ID")
    throughput_tps = Column(DECIMAL(8, 2), comment="吞吐量（tokens/秒）")
    ttft_ms        = Column(Integer, comment="首字延迟（毫秒）")
    e2e_latency_ms = Column(Integer, comment="端到端延迟（毫秒）")
    success        = Column(Boolean, nullable=False, default=True, comment="是否成功")
    error_code     = Column(String(50), comment="错误码（失败时记录）")
    prompt_tokens  = Column(Integer, comment="本次探测消耗的 prompt tokens")
    output_tokens  = Column(Integer, comment="本次探测产生的输出 tokens")
    probe_region   = Column(String(50), comment="探测区域，如 cn-east / us-west")
    measured_at    = Column(DateTime, nullable=False, comment="探测时间")

    # 关联报价配置
    offering = relationship("ModelProviderOffering", back_populates="performance_metrics")

    __table_args__ = (
        # 快速查询某 offering 最新记录
        Index("idx_ppm_offering_time", "offering_id", "measured_at"),
        # 支持按区域聚合
        Index("idx_ppm_offering_region", "offering_id", "probe_region"),
    )


class ProviderMetricsRanked(Base):
    """
    性能排名视图（只读，对应数据库 VIEW provider_metrics_ranked）
    暴露 rn 字段，应用层通过 WHERE rn <= n 控制取最近 N 次的窗口
    应用层聚合示例：
        SELECT offering_id, probe_region, AVG(throughput_tps), AVG(ttft_ms)
        FROM provider_metrics_ranked
        WHERE rn <= 5
        GROUP BY offering_id, probe_region
    """

    __tablename__ = "provider_metrics_ranked"

    # VIEW 无自增主键，用 offering_id + probe_region + measured_at 作为联合主键
    offering_id    = Column(BigInteger, primary_key=True, comment="报价 ID")
    probe_region   = Column(String(50), primary_key=True, comment="探测区域")
    measured_at    = Column(DateTime, primary_key=True, comment="探测时间")
    throughput_tps = Column(DECIMAL(8, 2), comment="吞吐量（tokens/秒）")
    ttft_ms        = Column(Integer, comment="首字延迟（毫秒）")
    e2e_latency_ms = Column(Integer, comment="端到端延迟（毫秒）")
    rn             = Column(Integer, comment="按 (offering_id, probe_region) 分区的时间倒序排名")

    # 标记为视图，不参与 create_all / drop_all
    __table_args__ = ({"info": {"is_view": True}},)
