"""Routing settings key-value model."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text

from api_service.common.infra.db.base import Base
from api_service.common.utils.timezone import now


class RoutingSetting(Base):
    """Individual routing policy setting (key-value)."""

    __tablename__ = "routing_settings"

    key = Column(String(64), primary_key=True, comment="配置键")
    value = Column(Text, nullable=False, comment="配置值")
    value_type = Column(String(16), nullable=False, default="string", comment="string/float/int")
    group_name = Column(String(32), nullable=False, comment="general/weights/score_bands/tier_model_map")
    label = Column(String(128), nullable=False, comment="管理端显示名")
    description = Column(String(512), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    updated_by = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at = Column(DateTime, default=now, onupdate=now, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)
