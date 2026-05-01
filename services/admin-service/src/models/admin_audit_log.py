"""Admin audit log model."""

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from core.db import Base
from common.utils.timezone import now


class AdminAuditLog(Base):
    """Audit trail for admin operations."""

    __tablename__ = "admin_audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Internal primary key")
    actor_admin_id = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Actor admin id",
    )
    target_admin_id = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Target admin id",
    )
    action = Column(String(100), nullable=False, index=True, comment="Operation code")
    resource_type = Column(String(50), nullable=False, index=True, comment="Resource type")
    resource_id = Column(String(100), nullable=True, comment="Resource identifier")
    status = Column(String(20), nullable=False, comment="success/failed")
    before_data = Column(JSON, nullable=True, comment="Data before change")
    after_data = Column(JSON, nullable=True, comment="Data after change")
    reason = Column(String(255), nullable=True, comment="Reason or failure summary")
    ip_address = Column(String(45), nullable=True, comment="Source IP")
    user_agent = Column(String(512), nullable=True, comment="Source user agent")
    created_at = Column(DateTime, default=now, nullable=False, comment="Event time")

    actor_admin = relationship(
        "AdminUser",
        foreign_keys=[actor_admin_id],
        back_populates="audit_logs",
        lazy="selectin",
    )
    target_admin = relationship(
        "AdminUser",
        foreign_keys=[target_admin_id],
        back_populates="targeted_audit_logs",
        lazy="selectin",
    )
