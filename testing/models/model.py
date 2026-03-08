# -*- coding: utf-8 -*-
"""
Testing 服务 SQLAlchemy 模型
定义模型、供应商、分类和性能测试结果的数据结构
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DECIMAL, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base, TimestampMixin


class ModelCategory(Base, TimestampMixin):
    """
    模型分类
    支持多对多关系，一个模型可属于多个分类
    """

    __tablename__ = "model_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name_zh = Column(String(50), nullable=False, comment="中文名称")
    name_en = Column(String(50), nullable=False, comment="英文名称")
    slug = Column(String(50), nullable=False, unique=True, comment="英文别名")
    description_zh = Column(Text, comment="中文描述")
    description_en = Column(Text, comment="英文描述")
    icon = Column(String(50), comment="图标标识")
    sort_order = Column(Integer, default=0, comment="排序顺序")

    # 多对多关系通过 ModelCategoryMapping 实现，使用 selectin 避免懒加载问题
    mappings = relationship(
        "ModelCategoryMapping",
        back_populates="category",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class ModelCategoryMapping(Base, TimestampMixin):
    """
    模型-分类关联表（多对多）
    """

    __tablename__ = "model_category_mapping"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False, comment="模型ID")
    category_id = Column(Integer, ForeignKey("model_categories.id"), nullable=False, comment="分类ID")
    is_primary = Column(Boolean, default=False, comment="是否为主分类")

    model = relationship("Model", back_populates="category_mappings")
    category = relationship("ModelCategory", back_populates="mappings")


class Model(Base, TimestampMixin):
    """
    模型基础信息
    """

    __tablename__ = "models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String(100), nullable=False, unique=True, comment="对外模型ID")
    name = Column(String(100), nullable=False, comment="显示名称")
    name_zh = Column(String(100), comment="中文名称")
    description_zh = Column(Text, comment="中文描述")
    description_en = Column(Text, comment="英文描述")
    context_length = Column(Integer, default=0, comment="上下文长度")
    model_size = Column(String(50), comment="模型大小")
    is_open_source = Column(Boolean, default=False, comment="是否开源")
    is_active = Column(Boolean, default=True, comment="是否启用")

    # 多对多关系，使用 selectin 避免懒加载问题
    category_mappings = relationship(
        "ModelCategoryMapping",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    tags = relationship(
        "ModelTag",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    providers = relationship(
        "ModelProvider",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class ModelTag(Base):
    """
    模型标签
    """

    __tablename__ = "model_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False, comment="模型ID")
    tag = Column(String(50), nullable=False, comment="标签名")
    tag_type = Column(String(20), default="feature", comment="标签类型")

    model = relationship("Model", back_populates="tags")

    __table_args__ = (
        Index("ix_model_tags_model_id", "model_id"),
        Index("ix_model_tags_tag", "tag"),
    )


class Provider(Base):
    """
    供应商
    """

    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(String(50), nullable=False, unique=True, comment="供应商ID")
    name = Column(String(100), nullable=False, comment="显示名称")
    name_zh = Column(String(100), comment="中文名称")
    logo_url = Column(String(255), comment="Logo URL")
    color = Column(String(20), comment="主题色")
    is_active = Column(Boolean, default=True, comment="是否启用")
    sort_order = Column(Integer, default=0, comment="排序顺序")

    model_providers = relationship(
        "ModelProvider",
        back_populates="provider",
        cascade="all, delete-orphan"
    )


class ModelProvider(Base, TimestampMixin):
    """
    模型-供应商关联
    记录每个模型在各个供应商的配置和价格信息
    """

    __tablename__ = "model_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False, comment="模型ID")
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, comment="供应商ID")
    api_model_name = Column(String(200), nullable=False, comment="供应商API模型名")
    routing_alias = Column(String(100), comment="路由别名")
    input_price_cny_1m = Column(DECIMAL(10, 4), comment="每百万输入价格(人民币)")
    output_price_cny_1m = Column(DECIMAL(10, 4), comment="每百万输出价格(人民币)")
    rate_limit_rpm = Column(Integer, default=60, comment="供应商限速(每分钟请求数)")
    is_default = Column(Boolean, default=False, comment="是否默认供应商")
    is_active = Column(Boolean, default=True, comment="是否启用")

    model = relationship("Model", back_populates="providers")
    provider = relationship("Provider", back_populates="model_providers")
    benchmark_results = relationship(
        "BenchmarkResult",
        back_populates="model_provider",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_model_providers_model_id", "model_id"),
        Index("ix_model_providers_provider_id", "provider_id"),
        Index("ix_model_providers_is_active", "is_active"),
    )


class BenchmarkResult(Base):
    """
    性能测试结果
    记录每次基准测试的详细数据
    """

    __tablename__ = "benchmark_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_provider_id = Column(
        Integer,
        ForeignKey("model_providers.id"),
        nullable=False,
        comment="模型供应商ID"
    )
    latency_ttft = Column(DECIMAL(10, 4), comment="首字延迟(秒)")
    latency_total = Column(DECIMAL(10, 4), comment="总延迟(秒)")
    throughput = Column(DECIMAL(10, 2), comment="吞吐量(tokens/秒)")
    success_count = Column(Integer, default=0, comment="成功次数")
    fail_count = Column(Integer, default=0, comment="失败次数")
    test_prompt = Column(String(500), comment="测试使用的prompt")
    test_at = Column(DateTime, server_default=func.now(), comment="测试时间")

    model_provider = relationship("ModelProvider", back_populates="benchmark_results")

    __table_args__ = (
        Index("ix_benchmark_results_model_provider_id", "model_provider_id"),
        Index("ix_benchmark_results_test_at", "test_at"),
    )
