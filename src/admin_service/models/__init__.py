"""Admin service ORM models."""

from admin_service.models.admin_audit_log import AdminAuditLog
from admin_service.models.admin_user import AdminUser
from admin_service.models.invitation_code import InvitationCode

SERVICE_MODELS = [AdminAuditLog, AdminUser, InvitationCode]

__all__ = ["AdminAuditLog", "AdminUser", "InvitationCode", "SERVICE_MODELS"]
