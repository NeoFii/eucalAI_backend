"""Admin service ORM models."""

from admin_service.models.admin_audit_log import AdminAuditLog
from admin_service.models.admin_user import AdminUser
from admin_service.models.model_catalog import (
    ModelCategory,
    ModelVendor,
    SupportedModel,
    SupportedModelCategoryMap,
)
from admin_service.models.pool import Pool, PoolAccount, PoolModel
from admin_service.models.routing_config import ProviderCredential, RoutingConfig
from admin_service.models.routing_setting import RoutingSetting

SERVICE_MODELS = [
    AdminAuditLog,
    AdminUser,
    ModelCategory,
    ModelVendor,
    Pool,
    PoolAccount,
    PoolModel,
    ProviderCredential,
    RoutingConfig,
    RoutingSetting,
    SupportedModel,
    SupportedModelCategoryMap,
]

__all__ = [
    "AdminAuditLog",
    "AdminUser",
    "ModelCategory",
    "ModelVendor",
    "Pool",
    "PoolAccount",
    "PoolModel",
    "ProviderCredential",
    "RoutingConfig",
    "RoutingSetting",
    "SERVICE_MODELS",
    "SupportedModel",
    "SupportedModelCategoryMap",
]
