"""Pool management models: Pool, PoolModel, PoolAccount."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from admin_service.db import Base
from common.db.base import SnowflakeIdMixin, TimestampMixin


class Pool(SnowflakeIdMixin, TimestampMixin, Base):
    __tablename__ = "pools"

    slug = Column(String(64), nullable=False, unique=True, comment="引用标识")
    name = Column(String(128), nullable=False, comment="显示名称")
    base_url = Column(String(512), nullable=False, comment="平台统一请求地址")
    is_enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=0, comment="路由优先级，越大越优先")
    weight = Column(Integer, nullable=False, default=1, comment="路由权重")
    health_check_endpoint = Column(String(512), nullable=True, comment="余额/状态检查接口")
    remark = Column(String(256), nullable=True)
    created_by = Column(
        BigInteger, ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False,
    )
    updated_by = Column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True,
    )

    models = relationship(
        "PoolModel", back_populates="pool", lazy="selectin", cascade="all, delete-orphan",
    )
    accounts = relationship(
        "PoolAccount", back_populates="pool", lazy="selectin", cascade="all, delete-orphan",
    )


class PoolModel(SnowflakeIdMixin, TimestampMixin, Base):
    __tablename__ = "pool_models"
    __table_args__ = (
        UniqueConstraint("pool_id", "model_slug", name="uq_pool_model"),
    )

    pool_id = Column(
        BigInteger, ForeignKey("pools.id", ondelete="CASCADE"), nullable=False,
    )
    model_slug = Column(String(120), nullable=False, comment="系统模型标识")
    upstream_model_id = Column(String(200), nullable=False, comment="上游实际模型 ID")
    input_price_per_million = Column(Integer, nullable=False, default=0, comment="每百万输入 token 价格（分）")
    output_price_per_million = Column(Integer, nullable=False, default=0, comment="每百万输出 token 价格（分）")
    cached_input_price_per_million = Column(Integer, nullable=True, comment="缓存命中输入价格（分）")
    context_length = Column(Integer, nullable=True, comment="该平台对此模型的最大上下文长度")
    is_enabled = Column(Boolean, nullable=False, default=True)

    pool = relationship("Pool", back_populates="models")


class PoolAccount(SnowflakeIdMixin, TimestampMixin, Base):
    __tablename__ = "pool_accounts"

    pool_id = Column(
        BigInteger, ForeignKey("pools.id", ondelete="CASCADE"), nullable=False,
    )
    name = Column(String(128), nullable=False, comment="备注名")
    api_key_enc = Column(JSON, nullable=False, comment="AES-256-GCM encrypted {ciphertext,iv,tag}")
    mask = Column(String(32), nullable=False, comment="脱敏显示")
    balance = Column(Integer, nullable=False, default=0, comment="余额（分）")
    status = Column(String(16), nullable=False, default="active", comment="active/disabled/exhausted/error")
    rpm_limit = Column(Integer, nullable=True, comment="每分钟请求上限")
    tpm_limit = Column(Integer, nullable=True, comment="每分钟 token 上限")
    weight = Column(Integer, nullable=False, default=1, comment="轮转权重")
    last_checked_at = Column(DateTime, nullable=True, comment="上次检查时间")
    last_health_check_error = Column(String(512), nullable=True, comment="上次健康检查错误信息")
    remark = Column(String(256), nullable=True)
    created_by = Column(
        BigInteger, ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False,
    )
    updated_by = Column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True,
    )

    pool = relationship("Pool", back_populates="accounts")
