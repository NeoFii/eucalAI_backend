"""Admin service ORM models."""

from admin_service.models.admin_audit_log import AdminAuditLog
from admin_service.models.admin_user import AdminUser
from admin_service.models.model_catalog import (
    ModelCategory,
    ModelVendor,
    SupportedModel,
    SupportedModelCategoryMap,
)
from admin_service.models.routing_config import ProviderCredential, RoutingConfig

SERVICE_MODELS = [
    AdminAuditLog,
    AdminUser,
    ModelCategory,
    ModelVendor,
    ProviderCredential,
    RoutingConfig,
    SupportedModel,
    SupportedModelCategoryMap,
]

__all__ = [
    "AdminAuditLog",
    "AdminUser",
    "ModelCategory",
    "ModelVendor",
    "ProviderCredential",
    "RoutingConfig",
    "SERVICE_MODELS",
    "SupportedModel",
    "SupportedModelCategoryMap",
]
