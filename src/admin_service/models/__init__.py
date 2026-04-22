"""Admin service ORM models."""

from admin_service.models.admin_audit_log import AdminAuditLog
from admin_service.models.admin_user import AdminUser
from admin_service.models.invitation_code import InvitationCode
from admin_service.models.model_catalog import (
    ModelCategory,
    ModelVendor,
    SupportedModel,
    SupportedModelCategoryMap,
)

SERVICE_MODELS = [
    AdminAuditLog,
    AdminUser,
    InvitationCode,
    ModelCategory,
    ModelVendor,
    SupportedModel,
    SupportedModelCategoryMap,
]

__all__ = [
    "AdminAuditLog",
    "AdminUser",
    "InvitationCode",
    "ModelCategory",
    "ModelVendor",
    "SERVICE_MODELS",
    "SupportedModel",
    "SupportedModelCategoryMap",
]
