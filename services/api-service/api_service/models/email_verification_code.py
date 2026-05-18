"""邮箱验证码数据模型."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String

from api_service.common.infra.db.base import Base
from api_service.common.utils.timezone import now


class EmailVerificationCode(Base):
    """邮箱验证码表 — 存储邮箱验证码的哈希值，支持频率限制和错误锁定."""

    __tablename__ = "email_verification_codes"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    email = Column(String(255), nullable=False, comment="邮箱地址")
    code_hash = Column(String(255), nullable=False, comment="验证码哈希")
    purpose = Column(String(20), nullable=False, default="register", comment="用途")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    used_at = Column(DateTime, nullable=True, comment="使用时间")
    error_count = Column(Integer, nullable=False, default=0, comment="错误次数")
    locked_until = Column(DateTime, nullable=True, comment="锁定截止时间")
    created_at = Column(DateTime, nullable=False, default=now, comment="创建时间")

    __table_args__ = (
        Index("idx_codes_email", "email"),
        Index("idx_codes_email_purpose", "email", "purpose"),
        Index("idx_codes_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<EmailVerificationCode(email={self.email}, purpose={self.purpose})>"
