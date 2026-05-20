"""Audit action definition model."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String

from app.common.infra.db.base import Base
from app.common.utils.timezone import now


class AuditActionDefinition(Base):
    """Registry of valid audit action codes."""

    __tablename__ = "audit_action_definitions"

    code = Column(String(100), primary_key=True, comment="Action code (e.g. create_admin)")
    label = Column(String(120), nullable=False, comment="Display label (Chinese)")
    category = Column(String(32), nullable=False, comment="Category grouping")
    resource_type = Column(String(50), nullable=False, comment="Associated resource type")
    description = Column(String(255), nullable=True, comment="Optional description")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether new logs can use this code")
    sort_order = Column(Integer, nullable=False, default=0, comment="Display sort order")
    created_at = Column(DateTime, default=now, nullable=False, comment="Created at")
    updated_at = Column(DateTime, default=now, onupdate=now, nullable=False, comment="Updated at")
    updated_by = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Last updater admin id",
    )
