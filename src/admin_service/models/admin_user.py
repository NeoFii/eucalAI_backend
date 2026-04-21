"""Admin user models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import relationship

from admin_service.db import Base
from common.db.base import SnowflakeIdMixin, TimestampMixin

if TYPE_CHECKING:
    pass


class AdminUser(Base, SnowflakeIdMixin, TimestampMixin):
    """Admin account."""

    __tablename__ = "admin_users"

    uid = Column(BigInteger, unique=True, nullable=False, index=True, comment="Public admin UID")
    email = Column(String(255), unique=True, nullable=False, index=True, comment="Login email")
    password_hash = Column(String(255), nullable=False, comment="Password hash")
    name = Column(String(100), nullable=False, comment="Admin display name")
    status = Column(SmallInteger, default=1, nullable=False, comment="0=disabled 1=active")
    role = Column(String(20), default="admin", nullable=False, comment="admin/super_admin")
    created_by_admin_id = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Creator admin id",
    )
    updated_by_admin_id = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Last updater admin id",
    )
    password_changed_at = Column(DateTime, nullable=True, comment="Last password change time")
    password_changed_by_admin_id = Column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Last password changer admin id",
    )
    last_login_at = Column(DateTime, nullable=True, comment="Last login time")
    last_login_ip = Column(String(45), nullable=True, comment="Last login IP")
    login_fail_count = Column(Integer, default=0, nullable=False, comment="Failed login count")
    login_locked_until = Column(DateTime, nullable=True, comment="Login lock expiry")

    created_by_admin = relationship(
        "AdminUser",
        foreign_keys=[created_by_admin_id],
        remote_side="AdminUser.id",
        lazy="selectin",
    )
    updated_by_admin = relationship(
        "AdminUser",
        foreign_keys=[updated_by_admin_id],
        remote_side="AdminUser.id",
        lazy="selectin",
    )
    password_changed_by_admin = relationship(
        "AdminUser",
        foreign_keys=[password_changed_by_admin_id],
        remote_side="AdminUser.id",
        lazy="selectin",
    )

    created_invitation_codes = relationship(
        "InvitationCode",
        foreign_keys="InvitationCode.created_by",
        back_populates="creator",
        lazy="noload",
    )
    audit_logs = relationship(
        "AdminAuditLog",
        foreign_keys="AdminAuditLog.actor_admin_id",
        back_populates="actor_admin",
        lazy="noload",
    )
    targeted_audit_logs = relationship(
        "AdminAuditLog",
        foreign_keys="AdminAuditLog.target_admin_id",
        back_populates="target_admin",
        lazy="noload",
    )

    def __init__(self, **kwargs):
        if kwargs.get("role") == "super":
            kwargs["role"] = "super_admin"
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<AdminUser(uid={self.uid}, email={self.email}, role={self.role})>"

    @property
    def is_active(self) -> bool:
        return self.status == 1

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    @property
    def is_login_locked(self) -> bool:
        if self.login_locked_until is None:
            return False
        from common.utils.timezone import now

        return now() < self.login_locked_until
